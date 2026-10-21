from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import ProviderError
from ..domain.models import (
    Concept,
    Material,
    MaterialIndexCard,
    MaterialLink,
    NodeConcept,
    Note,
)
from ..services.knowledge.concepts import (
    ConceptsError,
    commit_concepts,
    concept_graph,
    extract_concepts,
)
from ..services.knowledge.courses import (
    CourseError,
    OutlineService,
)
from ..services.knowledge.placement import (
    suggest_placements,
    unassigned_payload,
)
from ..services.knowledge.tree import TreeError
from ..services.platform.profiles import ensure_default_profile
from ..services.study.organizer import (
    OrganizerError,
    missing_note_markdown,
    node_context,
    review_node,
    review_report_markdown,
)
from .courses import _load_course, _load_node, _structure, _tree
from .courses_schemas import (
    ConceptDraftOut,
    ConceptGraphOut,
    ConceptsCommitOut,
    CourseMaterialsEntryOut,
    DraftNoteOut,
    FolderAssignedOut,
    MaterialAssignedOut,
    NodeArtifactsOut,
    NodeConceptLinkedOut,
    NodeCreatedOut,
    NodeDeletedOut,
    NodeDetailOut,
    NodeMovedOut,
    NodeRestoredOut,
    NodeReviewOut,
    NodeUpdatedOut,
    NodeWorkspaceOut,
    OutlineCommitOut,
    OutlineDraftOut,
    TreeNodeOut,
)
from .deps import get_session

router = APIRouter(tags=["courses"])


class NodeCreate(BaseModel):
    course_id: str
    parent_id: str
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = None
    objectives: list[str] | None = None


class NodeUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    objectives: list[str] | None = None
    ai_hint: str | None = Field(default=None, max_length=4000)


class NodeMove(BaseModel):
    parent_id: str
    position: int


class NodeRestore(BaseModel):
    undo_token: str


class AllocationIn(BaseModel):
    material_id: str
    rationale: str | None = None


class FolderAllocationIn(BaseModel):
    folder_id: str
    rationale: str | None = None


class MirrorFolderIn(BaseModel):
    folder_id: str
    recursive: bool = True
    rationale: str | None = None


class MirrorFolderOut(BaseModel):
    created_nodes: int
    reused_nodes: int
    folder_links: int
    skipped_folders: list[str] = Field(default_factory=list)


class OutlineCommit(BaseModel):
    chapters: list[dict[str, Any]]


class NodeConceptIn(BaseModel):
    concept_id: str


class ConceptsCommit(BaseModel):
    concepts: list[dict[str, Any]]
    links: list[dict[str, Any]]
    nodes: list[dict[str, Any]]


@router.get("/courses/{course_id}/tree", response_model=list[TreeNodeOut])
def course_tree(course_id: str, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    _load_course(session, course_id)
    profile = ensure_default_profile(session)
    return _tree(session).tree(course_id, profile.id)


@router.post("/courses/{course_id}/nodes", status_code=201, response_model=NodeCreatedOut)
def add_node(
    course_id: str, body: NodeCreate, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    try:
        node = _tree(session).create_node(
            course_id,
            body.parent_id,
            body.title,
            summary=body.summary,
            objectives=body.objectives,
        )
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"id": node.id, "title": node.title, "order_idx": node.order_idx, "depth": node.depth}


@router.get("/nodes/{node_id}", response_model=NodeDetailOut)
def get_node(node_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    node = _load_node(session, node_id)
    return {
        "id": node.id,
        "course_id": node.course_id,
        "parent_id": node.parent_id,
        "title": node.title,
        "summary": node.summary,
        "objectives": node.objectives or [],
        "ai_hint": node.ai_hint,
        "depth": node.depth,
        "is_root": node.is_root,
        "order_idx": node.order_idx,
    }


@router.patch("/nodes/{node_id}", response_model=NodeUpdatedOut)
def patch_node(
    node_id: str, body: NodeUpdate, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    try:
        node = _tree(session).update_node(
            node_id,
            title=body.title,
            summary=body.summary,
            objectives=body.objectives,
            ai_hint=body.ai_hint,
        )
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"id": node.id, "title": node.title, "ai_hint": node.ai_hint}


@router.patch("/nodes/{node_id}/move", response_model=NodeMovedOut)
def move_node(
    node_id: str, body: NodeMove, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    try:
        node = _tree(session).move_node(node_id, body.parent_id, body.position)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"id": node.id, "parent_id": node.parent_id, "order_idx": node.order_idx}


@router.delete("/nodes/{node_id}", response_model=NodeDeletedOut)
def delete_node(node_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _load_node(session, node_id)
    profile = ensure_default_profile(session)
    try:
        deleted_item_id = _tree(session).delete_node_to_trash(node_id, profile.id)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"deleted_item_id": deleted_item_id}


@router.post("/nodes/restore", status_code=200, response_model=NodeRestoredOut)
def restore_node(body: NodeRestore, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        node_id = _tree(session).restore_node(body.undo_token)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"id": node_id}


@router.post("/nodes/{node_id}/concepts", status_code=201, response_model=NodeConceptLinkedOut)
def add_node_concept(
    node_id: str, body: NodeConceptIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    node = _load_node(session, node_id)
    concept = session.get(Concept, body.concept_id)
    if concept is None or concept.course_id != node.course_id:
        raise HTTPException(status_code=422, detail="concept not in this course")
    existing = session.scalars(
        select(NodeConcept).where(
            NodeConcept.node_id == node_id,
            NodeConcept.concept_id == concept.id,
        )
    ).first()
    if existing is None:
        session.add(NodeConcept(node_id=node_id, concept_id=concept.id))
        session.commit()
    return {"node_id": node_id, "concept_id": concept.id}


@router.delete("/nodes/{node_id}/concepts/{concept_id}", status_code=204)
def remove_node_concept(
    node_id: str, concept_id: str, session: Session = Depends(get_session)
) -> None:
    _load_node(session, node_id)
    existing = session.scalars(
        select(NodeConcept).where(
            NodeConcept.node_id == node_id,
            NodeConcept.concept_id == concept_id,
        )
    ).first()
    if existing is not None:
        session.delete(existing)
        session.commit()


@router.get("/nodes/{node_id}/workspace", response_model=NodeWorkspaceOut)
def node_workspace(node_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    _load_node(session, node_id)
    return _tree(session).workspace(node_id, profile.id)


def _assign(session: Session, node_id: str, body: AllocationIn) -> dict[str, Any]:
    try:
        link = _structure(session).assign(
            node_id,
            body.material_id,
            rationale=body.rationale,
            auto_assigned=False,
        )
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "node_id": link.node_id,
        "material_id": link.material_id,
    }


@router.post("/nodes/{node_id}/materials", status_code=201, response_model=MaterialAssignedOut)
def assign_material(
    node_id: str, body: AllocationIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    result = _assign(session, node_id, body)
    session.commit()
    return result


@router.delete("/nodes/{node_id}/materials/{material_id}", status_code=204)
def unassign_material(
    node_id: str, material_id: str, session: Session = Depends(get_session)
) -> None:
    _load_node(session, node_id)
    try:
        _structure(session).unassign(node_id, material_id)
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()


@router.post("/nodes/{node_id}/folder-materials", status_code=201, response_model=FolderAssignedOut)
def assign_folder_materials(
    node_id: str, body: FolderAllocationIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    try:
        link = _structure(session).assign_folder(node_id, body.folder_id, rationale=body.rationale)
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"node_id": link.node_id, "folder_id": link.folder_id}


@router.delete("/nodes/{node_id}/folder-materials/{folder_id}", status_code=204)
def unassign_folder_materials(
    node_id: str, folder_id: str, session: Session = Depends(get_session)
) -> None:
    _load_node(session, node_id)
    _structure(session).unassign_folder(node_id, folder_id)
    session.commit()


@router.post(
    "/nodes/{node_id}/mirror-folder",
    status_code=201,
    response_model=MirrorFolderOut,
)
def mirror_folder(
    node_id: str, body: MirrorFolderIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    try:
        result = _structure(session).mirror_folder(
            node_id, body.folder_id, recursive=body.recursive, rationale=body.rationale
        )
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return result


@router.get("/courses/{course_id}/materials", response_model=list[CourseMaterialsEntryOut])
def course_materials(
    course_id: str, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    _load_course(session, course_id)
    return _structure(session).course_materials(course_id)


class UnassignedMaterialOut(BaseModel):
    id: str
    title: str


class UnassignedOut(BaseModel):
    count: int
    materials: list[UnassignedMaterialOut]


class PlacementSuggestionsIn(BaseModel):
    material_ids: list[str] = Field(max_length=40)


class PlacementCandidateOut(BaseModel):
    node_id: str
    node_title: str
    breadcrumb: list[dict[str, Any]]
    score: float
    matched_on: list[str]


class PlacementSuggestionsOut(BaseModel):
    suggestions: list["PlacementSuggestionOut"]


class PlacementSuggestionOut(BaseModel):
    material_id: str
    candidates: list[PlacementCandidateOut]


PlacementSuggestionsOut.model_rebuild()


@router.get("/courses/{course_id}/materials/unassigned", response_model=UnassignedOut)
def unassigned_course_materials(
    course_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    return unassigned_payload(session, course_id)


@router.post(
    "/courses/{course_id}/placement-suggestions",
    response_model=PlacementSuggestionsOut,
)
def placement_suggestions(
    course_id: str, body: PlacementSuggestionsIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    return {"suggestions": suggest_placements(session, course_id, body.material_ids)}


@router.post(
    "/courses/{course_id}/materials",
    status_code=201,
    response_model=MaterialAssignedOut,
)
def assign_course_material(
    course_id: str, body: AllocationIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    root = _tree(session).ensure_root(course_id)
    result = _assign(session, root.id, body)
    session.commit()
    return result


@router.delete("/courses/{course_id}/materials/{material_id}", status_code=204)
def unassign_course_material(
    course_id: str, material_id: str, session: Session = Depends(get_session)
) -> None:
    _load_course(session, course_id)
    root = _tree(session).ensure_root(course_id)
    try:
        _structure(session).unassign(root.id, material_id)
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()


@router.post(
    "/courses/{course_id}/folder-materials",
    status_code=201,
    response_model=FolderAssignedOut,
)
def assign_course_folder_materials(
    course_id: str, body: FolderAllocationIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    root = _tree(session).ensure_root(course_id)
    try:
        link = _structure(session).assign_folder(root.id, body.folder_id, rationale=body.rationale)
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"node_id": link.node_id, "folder_id": link.folder_id}


@router.delete("/courses/{course_id}/folder-materials/{folder_id}", status_code=204)
def unassign_course_folder_materials(
    course_id: str, folder_id: str, session: Session = Depends(get_session)
) -> None:
    _load_course(session, course_id)
    root = _tree(session).ensure_root(course_id)
    _structure(session).unassign_folder(root.id, folder_id)
    session.commit()


@router.post("/courses/{course_id}/outline/draft", response_model=OutlineDraftOut)
def outline_draft(
    course_id: str, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    course = _load_course(session, course_id)
    materials = list(
        session.scalars(
            select(Material).where(Material.course_id == course_id, Material.status == "ready")
        )
    )
    cards = {
        card.material_id: card
        for card in session.scalars(
            select(MaterialIndexCard).where(
                MaterialIndexCard.material_id.in_([material.id for material in materials])
            )
        )
    }
    try:
        return OutlineService(request.app.state.gateway).draft(course, materials, cards)
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/courses/{course_id}/outline/commit", response_model=OutlineCommitOut)
def outline_commit(
    course_id: str, body: OutlineCommit, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    try:
        result = _structure(session).commit_outline(course_id, {"chapters": body.chapters})
    except (CourseError, TreeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return result


@router.post("/courses/{course_id}/concepts/extract", response_model=ConceptDraftOut)
def extract_course_concepts(
    course_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    course = _load_course(session, course_id)
    materials = list(
        session.scalars(
            select(Material).where(Material.course_id == course_id, Material.status == "ready")
        )
    )
    if not materials:
        raise HTTPException(status_code=422, detail="course has no ready materials")
    cards = {
        card.material_id: card
        for card in session.scalars(
            select(MaterialIndexCard).where(
                MaterialIndexCard.material_id.in_([m.id for m in materials])
            )
        )
    }
    tree = _tree(session).tree(course_id)
    node_by_material: dict[str, str] = {}

    def walk(entry: dict[str, Any]) -> None:
        for allocation in entry["materials"]:
            if allocation["material_id"] not in node_by_material:
                node_by_material[allocation["material_id"]] = entry["title"]
        for child in entry["children"]:
            walk(child)

    for root in tree:
        walk(root)
    known_nodes: set[str] = set()

    def collect(entry: dict[str, Any]) -> None:
        known_nodes.add(entry["title"])
        for child in entry["children"]:
            collect(child)

    for root in tree:
        collect(root)
    payload = [
        {
            "title": material.title,
            "topics": (cards[material.id].topics if material.id in cards else None),
            "summary": (cards[material.id].summary if material.id in cards else None),
            "node_title": node_by_material.get(material.id),
        }
        for material in materials
    ]
    try:
        draft = extract_concepts(request.app.state.gateway, course, payload)
    except ConceptsError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    draft["nodes"] = [
        entry for entry in draft["nodes"] if not known_nodes or entry["node_title"] in known_nodes
    ]
    return draft


@router.post("/courses/{course_id}/concepts/commit", response_model=ConceptsCommitOut)
def commit_course_concepts(
    course_id: str,
    body: ConceptsCommit,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    _load_course(session, course_id)
    result = commit_concepts(
        session,
        course_id,
        {
            "concepts": body.concepts,
            "links": body.links,
            "nodes": body.nodes,
        },
    )
    session.commit()
    return result


@router.get("/courses/{course_id}/concepts", response_model=ConceptGraphOut)
def course_concept_graph(course_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _load_course(session, course_id)
    profile = ensure_default_profile(session)
    return concept_graph(session, course_id, profile.id)


@router.post("/nodes/{node_id}/review", response_model=NodeReviewOut)
def review_node_endpoint(
    node_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    node = _load_node(session, node_id)
    try:
        node, children, unassigned, concepts = node_context(session, node_id)
    except OrganizerError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    try:
        findings = review_node(request.app.state.gateway, node, children, unassigned, concepts)
    except OrganizerError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    from datetime import UTC
    from datetime import datetime as dt

    from ..pipelines.compose import ComposeService, find_live_artifact
    from ..services.content.materials import MaterialsService

    report = review_report_markdown(node.title, findings)
    dated = dt.now(UTC).date().isoformat()
    title = f"{node.title} — Review {dated}"
    existing_same_day = find_live_artifact(session, node.course_id, node.id, "node_review")
    if existing_same_day is not None and existing_same_day.title == title:
        MaterialsService(session, request.app.state.blobs).edit_extraction(
            existing_same_day, report
        )
        material = existing_same_day
    else:
        material = ComposeService(session, request.app.state.gateway).compose_organizer_artifact(
            profile_id=profile.id,
            course_id=node.course_id,
            node_id=node.id,
            kind="node_review",
            title=title,
            markdown=report,
            model_label=None,
            blobs=request.app.state.blobs,
        )
        MaterialsService(session, request.app.state.blobs).queue_ingest(
            material, request.app.state.jobs
        )
    session.commit()
    return {
        "node_id": node_id,
        "node_title": node.title,
        "findings": findings,
        "material_id": material.id,
    }


@router.post("/nodes/{node_id}/draft-note", response_model=DraftNoteOut)
def draft_node_note(
    node_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    node = _load_node(session, node_id)
    existing = session.scalars(
        select(Note)
        .where(
            Note.node_id == node_id,
            Note.course_id == node.course_id,
            Note.tags.like('%"ai-draft"%'),
        )
        .order_by(Note.created_at.desc(), Note.id.desc())
        .limit(1)
    ).first()
    if existing is not None:
        markdown = "\n\n".join(
            str(block.get("md") or "") for block in existing.body or [] if block.get("md")
        )
        return {
            "note_id": existing.id,
            "markdown": markdown,
            "existing": True,
        }
    materials = [
        {"title": material.title, "summary": None}
        for material in session.scalars(
            select(Material)
            .join(MaterialLink, MaterialLink.material_id == Material.id)
            .where(
                MaterialLink.course_id == node.course_id,
                MaterialLink.node_id.in_(_tree(session).subtree_ids(node)),
            )
        )
    ]
    if not materials:
        raise HTTPException(status_code=422, detail="node has no material assigned")
    try:
        markdown = missing_note_markdown(request.app.state.gateway, node, materials)
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    note = Note(
        profile_id=profile.id,
        course_id=node.course_id,
        node_id=node.id,
        title=f"{node.title} — AI draft",
        body=[{"type": "text", "md": markdown}],
    )
    note.search_text = f"{note.title}\n{markdown}"
    note.tags = ["ai-draft"]
    session.add(note)
    session.commit()
    return {"note_id": note.id, "markdown": markdown, "existing": False}


@router.get("/nodes/{node_id}/artifacts", response_model=NodeArtifactsOut)
def node_artifacts(
    node_id: str,
    kind: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    node = _load_node(session, node_id)
    rows = session.execute(
        select(Material)
        .join(MaterialLink, MaterialLink.material_id == Material.id)
        .where(
            MaterialLink.course_id == node.course_id,
            MaterialLink.node_id == node_id,
            Material.provenance.is_not(None),
        )
        .order_by(Material.created_at.desc(), Material.id.desc())
    ).scalars()
    cheat_sheet: dict[str, Any] | None = None
    reviews: list[dict[str, Any]] = []
    artifact: dict[str, Any] | None = None
    for material in rows:
        provenance = material.provenance
        if not isinstance(provenance, dict):
            continue
        entry_kind = provenance.get("kind")
        if entry_kind == "cheat_sheet" and cheat_sheet is None:
            cheat_sheet = {"material_id": material.id, "title": material.title}
        elif entry_kind == "node_review":
            reviews.append({"material_id": material.id, "title": material.title})
        if kind is not None and entry_kind == kind and artifact is None:
            artifact = {"material_id": material.id, "title": material.title}
    result: dict[str, Any] = {"cheat_sheet": cheat_sheet, "reviews": reviews[:5]}
    if kind is not None:
        result["artifact"] = artifact
    return result
