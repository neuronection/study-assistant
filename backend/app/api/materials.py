import base64
import mimetypes
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import ProviderError, TaskUnassigned
from ..core.vocab import MaterialKind, MaterialStatus
from ..domain.models import Extraction, Material, MaterialDrawing
from ..jobs.runner import JobRunner
from ..services.content.drawings import (
    enqueue_drawing_ocr,
    pending_ocr_job_id,
    strip_drawing_refs,
)
from ..services.content.materials import MaterialsService, purge_material
from ..services.knowledge.courses import StructureService
from ..services.platform.profiles import ensure_default_profile
from .courses_schemas import ViaFolderOut
from .deps import content_disposition, get_session
from .schemas import (
    DrawingIn,
    DrawingOut,
    ExtractionEdit,
    ExtractionOut,
    IndexCardOut,
    MaterialDetailOut,
    MaterialOut,
    MaterialUploadOut,
    ViewBox,
)

router = APIRouter(prefix="/materials", tags=["materials"])
blobs_router = APIRouter(prefix="/blobs", tags=["blobs"])

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TextFileIn(BaseModel):
    course_id: int
    folder_id: int | None = None
    filename: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=2_000_000)


class MaterialPatch(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class MaterialMove(BaseModel):
    folder_id: int | None = None


class MaterialCopyIn(BaseModel):
    folder_id: int | None = None


class MaterialDeriveIn(BaseModel):
    folder_id: int | None = None
    node_id: int | None = None


REINGESTABLE_KINDS = frozenset({"pdf", "md", "txt", "image"})


def _service(request: Request, session: Session) -> MaterialsService:
    return MaterialsService(session, request.app.state.blobs)


def _to_out(material: Material) -> MaterialOut:
    return MaterialOut(
        id=material.id,
        title=material.title,
        kind=MaterialKind(material.kind),
        status=MaterialStatus(material.status),
        filename=material.filename,
        mime=material.mime,
        pages=material.pages,
        course_id=material.course_id,
        group_id=material.group_id,
        folder_id=material.folder_id,
        blob_sha=material.blob_sha,
        provenance=material.provenance,
        created_at=material.created_at,
    )


def _drawings_out(session: Session, material: Material) -> list[DrawingOut]:
    return [
        DrawingOut(
            id=drawing.id,
            png_sha=drawing.png_sha,
            strokes=drawing.strokes,
            view=ViewBox(**drawing.view) if drawing.view else None,
            ocr_version=drawing.ocr_version,
            ocr_markdown=drawing.ocr_markdown,
            ocr_job_id=pending_ocr_job_id(session, drawing),
            created_at=drawing.created_at,
        )
        for drawing in material.drawings
    ]


def _material_detail(
    session: Session, service: MaterialsService, material: Material
) -> MaterialDetailOut:
    extraction = service.latest_extraction(material.id)
    card = service.index_card(material.id)
    return MaterialDetailOut(
        material=_to_out(material),
        extraction=(
            ExtractionOut(
                id=extraction.id,
                material_id=extraction.material_id,
                version=extraction.version,
                extractor=extraction.extractor,
                markdown=extraction.markdown,
                blocks=extraction.blocks,
            )
            if extraction is not None
            else None
        ),
        index_card=(
            IndexCardOut(
                reading_minutes=card.reading_minutes,
                summary=card.summary,
                topics=card.topics or [],
                key_terms=card.key_terms or [],
                difficulty=card.difficulty,
            )
            if card is not None
            else None
        ),
        drawings=_drawings_out(session, material),
    )


@router.post("", response_model=MaterialUploadOut)
async def upload_material(
    request: Request,
    file: UploadFile,
    course_id: int,
    folder_id: int | None = None,
    session: Session = Depends(get_session),
) -> MaterialUploadOut:
    data = await file.read()
    service = _service(request, session)
    profile = ensure_default_profile(session)
    try:
        material, deduped = service.upload(
            profile_id=profile.id,
            filename=file.filename or "upload",
            data=data,
            mime=file.content_type,
            course_id=course_id,
            folder_id=folder_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    job_id: int | None = None
    if not deduped:
        job_id = service.queue_ingest(material, request.app.state.jobs)
    session.commit()
    return MaterialUploadOut(
        material=_to_out(material), job_id=job_id, deduped=deduped
    )


class ComposeIn(BaseModel):
    course_id: int
    node_id: int | None = None
    kind: str = "study_guide"
    title: str | None = Field(default=None, max_length=300)
    instructions: str | None = Field(default=None, max_length=4000)
    extra_md: str | None = Field(default=None, max_length=20000)
    scope: str = "subtree"
    include_material_ids: list[int] = Field(default_factory=list)
    exclude_material_ids: list[int] = Field(default_factory=list)
    note_ids: list[int] = Field(default_factory=list)
    concept_ids: list[int] = Field(default_factory=list)
    context_hint: str | None = Field(default=None, max_length=2000)
    regenerate: bool = False


@router.post("/compose", response_model=MaterialUploadOut)
def compose_material(
    request: Request,
    body: ComposeIn,
    session: Session = Depends(get_session),
) -> MaterialUploadOut:
    profile = ensure_default_profile(session)
    from ..pipelines.compose import ComposeError, ComposeService
    from ..services.knowledge.context import (
        ContextError,
        ContextResolver,
        ContextScope,
        ContextSpec,
    )

    try:
        bundle = ContextResolver(session, request.app.state.embedder.embed).resolve(
            ContextSpec(
                course_id=body.course_id,
                node_id=body.node_id,
                scope=ContextScope(body.scope),
                include_material_ids=body.include_material_ids,
                exclude_material_ids=body.exclude_material_ids,
                note_ids=body.note_ids,
                concept_ids=body.concept_ids,
                hint=body.context_hint,
                query=body.title or body.instructions or "study material",
                exclude_ai_composed=True,
            )
        )
    except ContextError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    from ..pipelines.compose import find_live_artifact
    from ..services.content.materials import MaterialsService
    from ..services.knowledge.tree import TreeService

    placement_node_id = (
        bundle.node.id if bundle.node is not None else body.node_id
    )
    if placement_node_id is None:
        placement_node_id = TreeService(session).ensure_root(body.course_id).id
    live = find_live_artifact(
        session, body.course_id, placement_node_id, body.kind
    )
    existing_md: str | None = None
    if live is not None and not body.regenerate:
        raise HTTPException(
            status_code=409,
            detail=(
                f"a {body.kind.replace('_', ' ')} already exists at this node "
                f"(material {live.id}) — open it, or pass regenerate=true to "
                "replace it with a new version"
            ),
        )
    if live is not None:
        extraction = (
            session.scalars(
                select(Extraction)
                .where(Extraction.material_id == live.id)
                .order_by(Extraction.version.desc())
                .limit(1)
            ).first()
        )
        existing_md = extraction.markdown if extraction is not None else None
    try:
        material = ComposeService(session, request.app.state.gateway).compose(
            profile_id=profile.id,
            course_id=body.course_id,
            node_id=body.node_id,
            kind=body.kind,
            title=body.title,
            instructions=body.instructions,
            extra_md=body.extra_md,
            context_bundle=bundle,
            blobs=request.app.state.blobs,
            existing=live,
            existing_md=existing_md,
        )
    except ComposeError as error:
        message = str(error)
        status = 502 if "provider" in message.lower() else 422
        raise HTTPException(status_code=status, detail=message) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    services = MaterialsService(session, request.app.state.blobs)
    job_id = services.queue_ingest(material, request.app.state.jobs) if live is None else None
    session.commit()
    return MaterialUploadOut(material=_to_out(material), job_id=job_id, deduped=False)


MINDMAP_EDIT_MODES = {
    "expand": "Expand the mindmap: add more detail under each major branch.",
    "simplify": "Simplify: remove redundant or overly fine-grained nodes.",
    "reorganize": "Reorganize the mindmap: regroup nodes into a clearer hierarchy.",
    "examples": "Add concrete worked examples and pitfalls under relevant branches.",
    "custom": "",
}


class MindmapEditIn(BaseModel):
    mode: str = "custom"
    instruction: str | None = Field(default=None, max_length=4000)
    focus_node: str | None = Field(default=None, max_length=300)


class MindmapEditOut(BaseModel):
    markdown: str


class ExtractionVersionOut(BaseModel):
    version: int
    extractor: str
    created_at: datetime


@router.get("/{material_id}/extractions", response_model=list[ExtractionVersionOut])
def list_extraction_versions(
    material_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> list[ExtractionVersionOut]:
    profile = ensure_default_profile(session)
    material = _service(request, session).get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    from sqlalchemy import select as sa_select

    from ..domain.models import Extraction

    rows = session.scalars(
        sa_select(Extraction)
        .where(Extraction.material_id == material_id)
        .order_by(Extraction.version.desc())
        .limit(50)
    )
    return [
        ExtractionVersionOut(
            version=row.version, extractor=row.extractor, created_at=row.created_at
        )
        for row in rows
    ]


@router.get("/{material_id}/extractions/{version}", response_model=ExtractionOut)
def get_extraction_version(
    material_id: int,
    version: int,
    request: Request,
    session: Session = Depends(get_session),
) -> ExtractionOut:
    profile = ensure_default_profile(session)
    material = _service(request, session).get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    from sqlalchemy import select as sa_select

    from ..domain.models import Extraction

    row = session.scalars(
        sa_select(Extraction).where(
            Extraction.material_id == material_id, Extraction.version == version
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="extraction version not found")
    return _extraction_to_out(row)


@router.post("/{material_id}/mindmap-edit", response_model=MindmapEditOut)
def mindmap_edit(
    material_id: int,
    body: MindmapEditIn,
    request: Request,
    session: Session = Depends(get_session),
) -> MindmapEditOut:
    profile = ensure_default_profile(session)
    service = _service(request, session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    extraction = service.latest_extraction(material.id)
    if extraction is None or not extraction.markdown.strip():
        raise HTTPException(status_code=422, detail="material has no extraction to edit")

    from ..ai.gateway import Message
    from ..ai.skills import MINDMAP_EDIT_SYSTEM

    parts = [MINDMAP_EDIT_MODES.get(body.mode, "")]
    if body.instruction and body.instruction.strip():
        parts.append(f"Instruction: {body.instruction.strip()}")
    if body.focus_node and body.focus_node.strip():
        parts.append(f'Focus the edit on the node "{body.focus_node.strip()}" and its subtree.')
    guidance = "\n".join(part for part in parts if part)
    user_prompt = f"Current mindmap:\n\n{extraction.markdown}\n\n{guidance}".strip()

    gateway = request.app.state.gateway
    try:
        output = gateway.generate(
            "material_compose",
            [
                Message(role="system", content=MINDMAP_EDIT_SYSTEM),
                Message(role="user", content=user_prompt),
            ],
            course_id=material.course_id,
        )
    except (TaskUnassigned, ProviderError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    if not output.strip():
        raise HTTPException(status_code=422, detail="the model returned an empty mindmap")
    return MindmapEditOut(markdown=output.strip())


@router.get("", response_model=list[MaterialOut])
def list_materials(
    request: Request,
    course_id: int | None = None,
    folder_id: int | None = None,
    unfiled: bool = False,
    session: Session = Depends(get_session),
) -> list[MaterialOut]:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    materials = service.list_materials(
        profile_id=profile.id,
        course_id=course_id,
        folder_id=folder_id,
        unfiled=unfiled,
    )
    return [_to_out(material) for material in materials]


class LinkBreadcrumbOut(BaseModel):
    id: int
    title: str


class MaterialLinkInfoOut(BaseModel):
    node_id: int
    owner_title: str
    breadcrumb: list[LinkBreadcrumbOut]
    is_course_level: bool
    course_id: int
    course_title: str
    auto_assigned: bool
    rationale: str | None
    via_folder: ViaFolderOut | None


@router.get(
    "/{material_id}/links", response_model=list[MaterialLinkInfoOut]
)
def material_links(
    request: Request,
    material_id: int,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    material = _service(request, session).get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    return StructureService(session).material_links(material_id)


@router.post("/text", response_model=MaterialUploadOut)
def create_text_file(
    request: Request,
    body: TextFileIn,
    session: Session = Depends(get_session),
) -> MaterialUploadOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    try:
        material, deduped = service.create_text(
            profile_id=profile.id,
            course_id=body.course_id,
            filename=body.filename,
            content=body.content,
            folder_id=body.folder_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    job_id: int | None = None
    if not deduped:
        job_id = service.queue_ingest(material, request.app.state.jobs)
    session.commit()
    return MaterialUploadOut(material=_to_out(material), job_id=job_id, deduped=deduped)


@router.patch("/{material_id}", response_model=MaterialOut)
def rename_material(
    request: Request,
    material_id: int,
    body: MaterialPatch,
    session: Session = Depends(get_session),
) -> MaterialOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    try:
        material = service.rename(material, body.title)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _to_out(material)


@router.post("/{material_id}/reingest", response_model=MaterialUploadOut)
def reingest_material(
    request: Request,
    material_id: int,
    session: Session = Depends(get_session),
) -> MaterialUploadOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    if material.kind not in REINGESTABLE_KINDS:
        raise HTTPException(
            status_code=422, detail=f"material kind '{material.kind}' cannot be re-ingested"
        )
    if material.blob_sha is None:
        raise HTTPException(status_code=422, detail="material has no stored file to re-ingest")
    job_id = service.queue_ingest(material, request.app.state.jobs)
    session.commit()
    return MaterialUploadOut(
        material=_to_out(material), job_id=job_id, deduped=False
    )


@router.patch("/{material_id}/move", response_model=MaterialOut)
def move_material(
    request: Request,
    material_id: int,
    body: MaterialMove,
    session: Session = Depends(get_session),
) -> MaterialOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    try:
        material = service.move(material, body.folder_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _to_out(material)


@router.post("/{material_id}/copy", response_model=MaterialOut, status_code=201)
def copy_material(
    request: Request,
    material_id: int,
    body: MaterialCopyIn,
    session: Session = Depends(get_session),
) -> MaterialOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    try:
        copy = service.copy(material, body.folder_id, request.app.state.jobs)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _to_out(copy)


@router.post("/{material_id}/derive", response_model=MaterialUploadOut, status_code=201)
def derive_material(
    request: Request,
    material_id: int,
    body: MaterialDeriveIn,
    session: Session = Depends(get_session),
) -> MaterialUploadOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    try:
        derived, deduped = service.derive(material, body.folder_id, body.node_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    job_id: int | None = None
    if not deduped:
        job_id = service.queue_ingest(derived, request.app.state.jobs)
    session.commit()
    return MaterialUploadOut(material=_to_out(derived), job_id=job_id, deduped=deduped)


@router.delete("/{material_id}", status_code=204)
def delete_material(
    request: Request,
    material_id: int,
    session: Session = Depends(get_session),
) -> None:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    purge_material(session, material)
    session.commit()


@router.get("/{material_id}", response_model=MaterialDetailOut)
def get_material(
    request: Request,
    material_id: int,
    session: Session = Depends(get_session),
) -> MaterialDetailOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    return _material_detail(session, service, material)


def _extraction_to_out(extraction: Any) -> ExtractionOut:
    return ExtractionOut(
        id=extraction.id,
        material_id=extraction.material_id,
        version=extraction.version,
        extractor=extraction.extractor,
        markdown=extraction.markdown,
        blocks=extraction.blocks,
    )


@router.patch("/{material_id}/extraction", response_model=ExtractionOut)
def edit_extraction(
    request: Request,
    material_id: int,
    body: ExtractionEdit,
    session: Session = Depends(get_session),
) -> ExtractionOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    try:
        extraction, old_chunk_ids = service.edit_extraction(material, body.markdown)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    JobRunner.enqueue(
        session,
        "postprocess",
        {
            "material_id": material.id,
            "extraction_id": extraction.id,
            "old_chunk_ids": old_chunk_ids,
        },
    )
    session.commit()
    request.app.state.jobs.wake()
    return _extraction_to_out(extraction)


def _refresh_material_fts(
    session: Session, service: MaterialsService, material: Material
) -> None:
    latest = service.latest_extraction(material.id)
    markdown = latest.markdown if latest is not None else ""
    from ..storage.fts import sync_material_fts

    sync_material_fts(session, material, markdown, service.drawing_ocr_text(material))


def _store_material_drawing(
    request: Request,
    session: Session,
    service: MaterialsService,
    material: Material,
    body: DrawingIn,
    run_ocr: bool,
) -> MaterialDrawing:
    try:
        png = base64.b64decode(body.png_base64, validate=True)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="invalid png_base64") from error
    stored = request.app.state.blobs.put(png, mime="image/png", session=session)
    drawing = MaterialDrawing(
        material_id=material.id,
        strokes=body.strokes,
        png_sha=stored.sha256,
        view=body.view.model_dump() if body.view is not None else None,
    )
    session.add(drawing)
    session.flush()
    if run_ocr:
        drawing.ocr_job_id = enqueue_drawing_ocr(
            session, kind="material", owner_id=material.id, drawing_id=drawing.id
        )
        session.flush()
    _refresh_material_fts(session, service, material)
    session.flush()
    return drawing


@router.post("/{material_id}/drawings", response_model=MaterialDetailOut, status_code=201)
def add_material_drawing(
    material_id: int,
    body: DrawingIn,
    request: Request,
    session: Session = Depends(get_session),
) -> MaterialDetailOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    _store_material_drawing(request, session, service, material, body, run_ocr=body.ocr)
    session.commit()
    return _material_detail(session, service, material)


@router.put("/{material_id}/drawings/{drawing_id}", response_model=MaterialDetailOut)
def update_material_drawing(
    material_id: int,
    drawing_id: int,
    body: DrawingIn,
    request: Request,
    session: Session = Depends(get_session),
) -> MaterialDetailOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    drawing = session.get(MaterialDrawing, drawing_id)
    if drawing is None or drawing.material_id != material.id:
        raise HTTPException(status_code=404, detail="drawing not found")
    try:
        png = base64.b64decode(body.png_base64, validate=True)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="invalid png_base64") from error
    stored = request.app.state.blobs.put(png, mime="image/png", session=session)
    drawing.strokes = body.strokes
    drawing.png_sha = stored.sha256
    drawing.view = body.view.model_dump() if body.view is not None else None
    if body.ocr:
        drawing.ocr_job_id = enqueue_drawing_ocr(
            session, kind="material", owner_id=material.id, drawing_id=drawing.id
        )
    else:
        drawing.ocr_version = 0
        drawing.ocr_blocks = None
        drawing.ocr_markdown = None
        drawing.ocr_job_id = None
    _refresh_material_fts(session, service, material)
    session.commit()
    return _material_detail(session, service, material)


@router.post("/{material_id}/drawings/{drawing_id}/reocr", response_model=MaterialDetailOut)
def reocr_material_drawing(
    material_id: int,
    drawing_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> MaterialDetailOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    drawing = session.get(MaterialDrawing, drawing_id)
    if drawing is None or drawing.material_id != material.id:
        raise HTTPException(status_code=404, detail="drawing not found")
    if drawing.png_sha is None:
        raise HTTPException(status_code=422, detail="drawing has no stored image")
    if pending_ocr_job_id(session, drawing) is not None:
        raise HTTPException(status_code=409, detail="drawing OCR already in progress")
    drawing.ocr_job_id = enqueue_drawing_ocr(
        session, kind="material", owner_id=material.id, drawing_id=drawing.id
    )
    session.commit()
    return _material_detail(session, service, material)


@router.delete("/{material_id}/drawings/{drawing_id}", response_model=MaterialDetailOut)
def delete_material_drawing(
    material_id: int,
    drawing_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> MaterialDetailOut:
    service = _service(request, session)
    profile = ensure_default_profile(session)
    material = service.get(material_id, profile_id=profile.id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    drawing = session.get(MaterialDrawing, drawing_id)
    if drawing is None or drawing.material_id != material.id:
        raise HTTPException(status_code=404, detail="drawing not found")
    latest = service.latest_extraction(material.id)
    stripped = strip_drawing_refs(latest.markdown, drawing.id) if latest is not None else ""
    session.delete(drawing)
    session.flush()
    if latest is not None and stripped != latest.markdown and stripped.strip():
        service.edit_extraction(material, stripped)
    else:
        _refresh_material_fts(session, service, material)
    session.commit()
    return _material_detail(session, service, material)


@blobs_router.get("/{sha256}")
def get_blob(
    request: Request,
    sha256: str,
    session: Session = Depends(get_session),
) -> Response:
    if not _SHA256_RE.match(sha256):
        raise HTTPException(status_code=422, detail="invalid blob id")
    service = _service(request, session)
    blob_row = service.blob_row(sha256)
    if blob_row is None:
        raise HTTPException(status_code=404, detail="blob not found")
    data = request.app.state.blobs.get(sha256)
    if data is None:
        raise HTTPException(status_code=404, detail="blob content missing")
    mime = blob_row.mime
    filename: str | None = None
    if not mime or mime == "application/octet-stream":
        material = session.scalars(
            select(Material).where(Material.blob_sha == sha256)
        ).first()
        if material is not None:
            filename = material.filename
            guessed = mimetypes.guess_type(material.filename)[0]
            if guessed:
                mime = guessed
    headers = {"Content-Disposition": "inline"}
    if filename is not None:
        headers["Content-Disposition"] = content_disposition(filename, kind="inline")
    return Response(
        content=data,
        media_type=mime or "application/octet-stream",
        headers=headers,
    )
