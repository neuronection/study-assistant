import base64
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..ai.contracts.contracts import Constraint, validate
from ..ai.gateway import LLMGateway, Message, ProviderError, TaskUnassigned
from ..ai.skills import NOTE_ACTION_SYSTEM, NOTE_COMPOSE_SYSTEM
from ..domain.models import (
    AiInteraction,
    Note,
    NoteDrawing,
    NoteVersion,
    utcnow,
)
from ..services.drawings import (
    blocks_md,
    enqueue_drawing_ocr,
    md_to_blocks,
    note_search_text,
    pending_ocr_job_id,
)
from ..services.profiles import ensure_default_profile
from ..services.search import fuzzy_text_match
from ..services.skills import SkillService
from ..services.tree import TreeError, TreeService
from .deps import get_session
from .schemas import ViewBox

router = APIRouter(prefix="/notes", tags=["notes"])

OWNER_TYPES = ("standalone", "material", "exercise_session", "chat_message")

NOTE_VERSION_CAP = 50
NOTE_VERSION_COALESCE_SECONDS = 600
NOTE_CAUSES = ("autosave-coalesced", "manual", "restore")

NOTE_ACTIONS: dict[str, str] = {
    "summarize": (
        "Summarize the note into a compact revision sheet. Preserve formulas, "
        "definitions, and notation."
    ),
    "cleanup": "Rewrite the note cleanly: fix grammar and keep notation and formulas consistent.",
    "explain": "Explain the note's content step by step for someone learning it.",
    "expand": "Expand the note with one worked example and one common pitfall.",
}


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body_md: str = ""
    course_id: int
    node_id: int | None = None
    owner_type: str = "standalone"
    owner_id: int | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body_md: str | None = None
    pinned: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    base_updated_at: str | None = Field(default=None, max_length=64)
    force_version: bool = False


class NoteOut(BaseModel):
    id: int
    title: str
    course_id: int | None
    node_id: int | None
    owner_type: str
    owner_id: int | None
    tags: list[str]
    pinned: bool
    updated_at: str


class NotesPage(BaseModel):
    items: list[NoteOut]
    next_cursor: str | None


def _normalize_tags(tags: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in tags or []:
        tag = raw.strip().lower()[:60]
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


class NoteDetail(NoteOut):
    body: list[dict[str, Any]]
    drawings: list[dict[str, Any]]


class DrawingIn(BaseModel):
    strokes: list[dict[str, Any]] = Field(min_length=1)
    png_base64: str = Field(min_length=1)
    view: ViewBox | None = None
    ocr: bool = True


class DrawingUpdate(DrawingIn):
    pass


class ActionIn(BaseModel):
    action: str


class ActionOut(BaseModel):
    action: str
    markdown: str
    violations: str | None


class NoteComposeIn(BaseModel):
    course_id: int
    node_id: int | None = None
    scope: str = "subtree"
    title: str | None = Field(default=None, max_length=300)
    instructions: str | None = Field(default=None, max_length=2000)
    include_material_ids: list[int] = Field(default_factory=list)
    exclude_material_ids: list[int] = Field(default_factory=list)
    note_ids: list[int] = Field(default_factory=list)
    concept_ids: list[int] = Field(default_factory=list)
    context_hint: str | None = Field(default=None, max_length=2000)


def _validate_drawing_blocks(session: Session, note: Note) -> None:
    ids = {
        int(block["drawing_id"])
        for block in note.body or []
        if block.get("type") == "drawing"
    }
    if not ids:
        return
    valid = set(
        session.scalars(
            select(NoteDrawing.id).where(
                NoteDrawing.note_id == note.id, NoteDrawing.id.in_(ids)
            )
        )
    )
    unknown = ids - valid
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"unknown drawing reference(s): {sorted(unknown)}"
        )


def _note_out(note: Note) -> NoteOut:
    return NoteOut(
        id=note.id,
        title=note.title,
        course_id=note.course_id,
        node_id=note.node_id,
        owner_type=note.owner_type,
        owner_id=note.owner_id,
        tags=note.tags or [],
        pinned=note.pinned,
        updated_at=note.updated_at.isoformat(),
    )


def _note_detail(session: Session, note: Note) -> NoteDetail:
    return NoteDetail(
        **_note_out(note).model_dump(),
        body=note.body,
        drawings=[
            {
                "id": drawing.id,
                "png_sha": drawing.png_sha,
                "strokes": drawing.strokes,
                "view": drawing.view,
                "ocr_version": drawing.ocr_version,
                "ocr_markdown": drawing.ocr_markdown,
                "ocr_job_id": pending_ocr_job_id(session, drawing),
                "created_at": drawing.created_at.isoformat(),
            }
            for drawing in note.drawings
        ],
    )


def _load_note(db: Session, note_id: int, profile_id: int) -> Note:
    note = db.get(Note, note_id)
    if note is None or note.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="note not found")
    return note


@router.post("", response_model=NoteDetail, status_code=201)
def create_note(
    body: NoteCreate, session: Session = Depends(get_session)
) -> NoteDetail:
    profile = ensure_default_profile(session)
    if body.owner_type not in OWNER_TYPES:
        raise HTTPException(status_code=422, detail="unknown owner_type")
    try:
        node_id = TreeService(session).placement_node(body.course_id, body.node_id)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    note = Note(
        profile_id=profile.id,
        course_id=body.course_id,
        node_id=node_id,
        owner_type=body.owner_type,
        owner_id=body.owner_id,
        title=body.title.strip(),
        body=md_to_blocks(body.body_md),
        tags=_normalize_tags(body.tags),
    )
    note.search_text = note_search_text(note)
    session.add(note)
    session.flush()
    session.commit()
    return _note_detail(session, note)


@router.post("/compose", response_model=NoteDetail, status_code=201)
def compose_note(
    body: NoteComposeIn,
    request: Request,
    session: Session = Depends(get_session),
) -> NoteDetail:
    profile = ensure_default_profile(session)
    from ..services.context import ContextError, ContextResolver, ContextScope, ContextSpec

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
            )
        )
    except ContextError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        node_id = TreeService(session).placement_node(body.course_id, body.node_id)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    focus = (body.instructions or "").strip()
    prompt_parts: list[str] = []
    if focus:
        prompt_parts.append(f"Focus: {focus}")
    context_text = bundle.render_prompt()
    if context_text:
        prompt_parts.append(context_text)
    prompt = "\n\n".join(prompt_parts) or "Write a study note for this material."

    gateway: LLMGateway = request.app.state.gateway
    skill_version_id: int | None = None
    skills = SkillService(session)
    version = skills.resolve("notes.compose", course_id=body.course_id)
    if version is not None:
        system_prompt, _user = skills.render(version, {})
        constraints = skills.constraints(version, {})
        skill_version_id = version.id
    else:
        system_prompt = NOTE_COMPOSE_SYSTEM
        constraints = [Constraint("max_words", {"n": 400})]
    output = ""
    feedback = ""
    for _attempt in range(3):
        messages = [Message(role="system", content=system_prompt)]
        if feedback:
            messages.append(
                Message(
                    role="system",
                    content=f"Your previous answer broke a rule ({feedback}). Rewrite it.",
                )
            )
        messages.append(Message(role="user", content=prompt))
        try:
            output = gateway.generate("description", messages, course_id=body.course_id)
        except (TaskUnassigned, ProviderError) as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        validation = validate(output, constraints, {})
        if validation.ok:
            feedback = ""
            break
        feedback = validation.feedback()

    title = (body.title or "").strip() or "Study note"
    note = Note(
        profile_id=profile.id,
        course_id=body.course_id,
        node_id=node_id,
        owner_type="standalone",
        owner_id=None,
        title=title,
        body=md_to_blocks(output),
        tags=[],
    )
    note.search_text = note_search_text(note)
    session.add(note)
    session.flush()
    session.add(
        AiInteraction(
            context_type="note_compose",
            context_id=note.id,
            direction="compose",
            model=None,
            skill_version_id=skill_version_id,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(output) // 4),
            latency_ms=None,
        )
    )
    session.commit()
    return _note_detail(session, note)


def _apply_cursor(
    statement: Any, cursor: str | None
) -> tuple[Any, datetime | None]:
    if not cursor:
        return statement, None
    try:
        moment = datetime.fromisoformat(cursor)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    return statement.where(Note.updated_at < moment), moment


def _search_filter(
    session: Session, statement: Any, q: str, cursor: str | None
) -> Any:
    like = statement.where(Note.search_text.like(f"%{q}%"))
    like, _ = _apply_cursor(like, cursor)
    if session.scalar(select(func.count()).select_from(like.subquery())):
        return statement.where(Note.search_text.like(f"%{q}%"))
    ids = [
        note.id
        for note in session.scalars(statement)
        if fuzzy_text_match(q, note.search_text)
    ]
    if not ids:
        return like
    return statement.where(Note.id.in_(ids))


@router.get("", response_model=NotesPage)
def list_notes(
    q: str | None = None,
    course_id: int | None = None,
    node_id: int | None = None,
    include_children: bool = True,
    tag: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> NotesPage:
    profile = ensure_default_profile(session)
    limit = max(1, min(limit, 100))
    statement = select(Note).where(Note.profile_id == profile.id)
    if node_id is not None:
        scope_ids = TreeService(session).scoped_node_ids(node_id, include_children)
        statement = statement.where(Note.node_id.in_(scope_ids))
    elif course_id is not None:
        statement = statement.where(Note.course_id == course_id)
    if q:
        statement = _search_filter(session, statement, q, cursor)
    if tag:
        statement = statement.where(Note.tags.like(f'%"{tag.strip().lower()}"%'))
    statement, _moment = _apply_cursor(statement, cursor)
    statement = statement.order_by(Note.pinned.desc(), Note.updated_at.desc()).limit(
        limit + 1
    )
    rows = list(session.scalars(statement))
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        rows[-1].updated_at.isoformat() if has_more and rows else None
    )
    return NotesPage(items=[_note_out(note) for note in rows], next_cursor=next_cursor)


@router.get("/tags/list")
def list_note_tags(
    course_id: int | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    statement = select(Note).where(Note.profile_id == profile.id)
    if course_id is not None:
        statement = statement.where(Note.course_id == course_id)
    counts: dict[str, int] = {}
    for note in session.scalars(statement):
        for tag in note.tags or []:
            counts[tag] = counts.get(tag, 0) + 1
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda entry: (-entry[1], entry[0]))
    ]


@router.get("/{note_id}", response_model=NoteDetail)
def get_note(note_id: int, session: Session = Depends(get_session)) -> NoteDetail:
    profile = ensure_default_profile(session)
    return _note_detail(session, _load_note(session, note_id, profile.id))


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _snapshot_note(
    session: Session, note: Note, cause: str, force: bool = False
) -> None:
    latest = (
        session.execute(
            select(NoteVersion)
            .where(NoteVersion.note_id == note.id)
            .order_by(NoteVersion.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if not force and latest is not None:
        latest_at = _utc_naive(latest.created_at)
        if (utcnow().replace(tzinfo=None) - latest_at).total_seconds() < (
            NOTE_VERSION_COALESCE_SECONDS
        ):
            return
    session.add(
        NoteVersion(
            note_id=note.id,
            profile_id=note.profile_id,
            title=note.title,
            tags=note.tags,
            body=note.body,
            cause=cause,
        )
    )
    session.flush()
    stale = (
        session.execute(
            select(NoteVersion.id)
            .where(NoteVersion.note_id == note.id)
            .order_by(NoteVersion.id.desc())
            .offset(NOTE_VERSION_CAP)
        )
        .scalars()
        .all()
    )
    if stale:
        session.execute(delete(NoteVersion).where(NoteVersion.id.in_(stale)))


@router.patch("/{note_id}", response_model=NoteDetail)
def update_note(
    note_id: int, body: NoteUpdate, session: Session = Depends(get_session)
) -> NoteDetail:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    if body.base_updated_at is not None:
        try:
            base = datetime.fromisoformat(body.base_updated_at)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid base_updated_at") from None
        if _utc_naive(base) != _utc_naive(note.updated_at):
            raise HTTPException(status_code=409, detail="note was modified elsewhere")
    if body.body_md is not None:
        _snapshot_note(
            session,
            note,
            "manual" if body.force_version else "autosave-coalesced",
            force=body.force_version,
        )
    if body.title is not None:
        note.title = body.title.strip()
    if body.body_md is not None:
        parsed = md_to_blocks(body.body_md)
        note.body = parsed
        _validate_drawing_blocks(session, note)
    if body.pinned is not None:
        note.pinned = body.pinned
    if body.tags is not None:
        note.tags = _normalize_tags(body.tags)
    note.search_text = note_search_text(note)
    session.commit()
    return _note_detail(session, note)


class NoteMove(BaseModel):
    node_id: int | None = None


@router.patch("/{note_id}/move", response_model=NoteDetail)
def move_note(
    note_id: int, body: NoteMove, session: Session = Depends(get_session)
) -> NoteDetail:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    try:
        note.node_id = TreeService(session).placement_node(
            note.course_id, body.node_id
        )
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _note_detail(session, note)


class NoteVersionOut(BaseModel):
    version_id: int
    cause: str
    title: str
    chars: int
    created_at: str


class NoteVersionDetail(NoteVersionOut):
    body_md: str


def _version_out(version: NoteVersion) -> NoteVersionOut:
    return NoteVersionOut(
        version_id=version.id,
        cause=version.cause,
        title=version.title,
        chars=len(blocks_md(version.body)),
        created_at=version.created_at.isoformat(),
    )


@router.get("/{note_id}/versions", response_model=list[NoteVersionOut])
def list_note_versions(
    note_id: int, session: Session = Depends(get_session)
) -> list[NoteVersionOut]:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    versions = (
        session.execute(
            select(NoteVersion)
            .where(NoteVersion.note_id == note.id)
            .order_by(NoteVersion.id.desc())
            .limit(NOTE_VERSION_CAP)
        )
        .scalars()
        .all()
    )
    return [_version_out(version) for version in versions]


@router.get("/{note_id}/versions/{version_id}", response_model=NoteVersionDetail)
def get_note_version(
    note_id: int, version_id: int, session: Session = Depends(get_session)
) -> NoteVersionDetail:
    profile = ensure_default_profile(session)
    _load_note(session, note_id, profile.id)
    version = session.get(NoteVersion, version_id)
    if version is None or version.note_id != note_id:
        raise HTTPException(status_code=404, detail="version not found")
    return NoteVersionDetail(**_version_out(version).model_dump(), body_md=blocks_md(version.body))


class NoteRestoreIn(BaseModel):
    version_id: int


@router.post("/{note_id}/restore", response_model=NoteDetail)
def restore_note_version(
    note_id: int, body: NoteRestoreIn, session: Session = Depends(get_session)
) -> NoteDetail:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    version = session.get(NoteVersion, body.version_id)
    if version is None or version.note_id != note_id:
        raise HTTPException(status_code=404, detail="version not found")
    _snapshot_note(session, note, "restore", force=True)
    note.body = version.body
    note.search_text = note_search_text(note)
    note.updated_at = utcnow()
    session.commit()
    return _note_detail(session, note)


@router.delete("/{note_id}")
def delete_note(
    note_id: int, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    from ..jobs.cancellation import cancel_jobs_for
    from ..services import trash

    cancel_jobs_for(session, note_ids=[note.id])
    deleted_item_id = trash.snapshot(
        session,
        "note",
        note.id,
        note.title,
        profile.id,
        blobs_store=request.app.state.blobs,
    )
    session.delete(note)
    session.commit()
    return {"deleted_item_id": deleted_item_id}


def _store_drawing(
    request: Request, session: Session, note: Note, body: DrawingIn, run_ocr: bool
) -> NoteDrawing:
    try:
        png = base64.b64decode(body.png_base64, validate=True)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="invalid png_base64") from error
    stored = request.app.state.blobs.put(png, mime="image/png", session=session)
    drawing = NoteDrawing(
        note_id=note.id,
        strokes=body.strokes,
        png_sha=stored.sha256,
        view=body.view.model_dump() if body.view is not None else None,
    )
    session.add(drawing)
    session.flush()
    if run_ocr:
        drawing.ocr_job_id = enqueue_drawing_ocr(
            session, kind="note", owner_id=note.id, drawing_id=drawing.id
        )
        session.flush()
    note.search_text = note_search_text(note)
    session.flush()
    return drawing


@router.post("/{note_id}/drawings", response_model=NoteDetail, status_code=201)
def add_drawing(
    note_id: int,
    body: DrawingIn,
    request: Request,
    session: Session = Depends(get_session),
) -> NoteDetail:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    _store_drawing(request, session, note, body, run_ocr=body.ocr)
    session.commit()
    return _note_detail(session, note)


@router.put("/{note_id}/drawings/{drawing_id}", response_model=NoteDetail)
def update_drawing(
    note_id: int,
    drawing_id: int,
    body: DrawingUpdate,
    request: Request,
    session: Session = Depends(get_session),
) -> NoteDetail:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    drawing = session.get(NoteDrawing, drawing_id)
    if drawing is None or drawing.note_id != note.id:
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
            session, kind="note", owner_id=note.id, drawing_id=drawing.id
        )
    else:
        drawing.ocr_version = 0
        drawing.ocr_blocks = None
        drawing.ocr_markdown = None
        drawing.ocr_job_id = None
    note.search_text = note_search_text(note)
    note.updated_at = utcnow()
    session.commit()
    return _note_detail(session, note)


@router.post("/{note_id}/drawings/{drawing_id}/reocr", response_model=NoteDetail)
def reocr_drawing(
    note_id: int,
    drawing_id: int,
    session: Session = Depends(get_session),
) -> NoteDetail:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    drawing = session.get(NoteDrawing, drawing_id)
    if drawing is None or drawing.note_id != note.id:
        raise HTTPException(status_code=404, detail="drawing not found")
    if drawing.png_sha is None:
        raise HTTPException(status_code=422, detail="drawing has no stored image")
    if pending_ocr_job_id(session, drawing) is not None:
        raise HTTPException(status_code=409, detail="drawing OCR already in progress")
    drawing.ocr_job_id = enqueue_drawing_ocr(
        session, kind="note", owner_id=note.id, drawing_id=drawing.id
    )
    note.updated_at = utcnow()
    session.commit()
    return _note_detail(session, note)


@router.delete("/{note_id}/drawings/{drawing_id}", response_model=NoteDetail)
def delete_drawing(
    note_id: int,
    drawing_id: int,
    session: Session = Depends(get_session),
) -> NoteDetail:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    drawing = session.get(NoteDrawing, drawing_id)
    if drawing is None or drawing.note_id != note.id:
        raise HTTPException(status_code=404, detail="drawing not found")
    note.body = [
        block
        for block in (note.body or [])
        if not (
            block.get("type") == "drawing"
            and int(block.get("drawing_id", 0)) == drawing.id
        )
    ]
    session.delete(drawing)
    session.flush()
    note.search_text = note_search_text(note)
    note.updated_at = utcnow()
    session.commit()
    return _note_detail(session, note)


@router.post("/{note_id}/actions", response_model=ActionOut)
def run_note_action(
    note_id: int,
    body: ActionIn,
    request: Request,
    session: Session = Depends(get_session),
) -> ActionOut:
    profile = ensure_default_profile(session)
    note = _load_note(session, note_id, profile.id)
    instruction = NOTE_ACTIONS.get(body.action)
    if instruction is None:
        raise HTTPException(status_code=422, detail="unknown action")
    content_parts = [blocks_md(note.body)]
    for drawing in note.drawings:
        if drawing.ocr_markdown:
            content_parts.append(drawing.ocr_markdown)
    content = "\n\n".join(part for part in content_parts if part)
    if not content.strip():
        raise HTTPException(status_code=422, detail="note is empty")
    prompt = f"{instruction}\n\nNote title: {note.title}\n\n{content}"
    gateway: LLMGateway = request.app.state.gateway
    skill_version_id: int | None = None
    skills = SkillService(session)
    version = skills.resolve("notes.action", course_id=note.course_id)
    if version is not None:
        system_prompt, _user = skills.render(
            version, {"note_title": note.title, "note_body": content}
        )
        constraints = skills.constraints(version, {})
        skill_version_id = version.id
    else:
        system_prompt = NOTE_ACTION_SYSTEM
        constraints = [Constraint("max_words", {"n": 400})]
    output = ""
    feedback = ""
    for _attempt in range(3):
        messages = [Message(role="system", content=system_prompt)]
        if feedback:
            messages.append(
                Message(
                    role="system",
                    content=f"Your previous answer broke a rule ({feedback}). Rewrite it.",
                )
            )
        messages.append(Message(role="user", content=prompt))
        try:
            output = gateway.generate(
                "description", messages, course_id=note.course_id
            )
        except (TaskUnassigned, ProviderError) as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        validation = validate(output, constraints, {})
        if validation.ok:
            feedback = ""
            break
        feedback = validation.feedback()
    session.add(
        AiInteraction(
            context_type="note_action",
            context_id=note.id,
            direction=body.action,
            model=None,
            skill_version_id=skill_version_id,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(output) // 4),
            latency_ms=None,
        )
    )
    session.commit()
    return ActionOut(action=body.action, markdown=output, violations=feedback or None)
