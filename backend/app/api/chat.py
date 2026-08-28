import copy
import json
import threading
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..agui.state import apply_patch
from ..ai.gateway import ProviderError
from ..ai.mentions import registry_from_json
from ..ai.proposals import GENERATE_ACTIONS
from ..core.events import EventBus
from ..domain.models import (
    AiInteraction,
    ChatMessage,
    ChatProposal,
    ChatSession,
    Note,
    TreeNode,
    utcnow,
)
from ..jobs.runner import JobError, JobHandler, JobRunner
from ..services.chat import ChatError, ChatService
from ..services.profiles import ensure_default_profile
from ..services.proposal_actions import (
    ProposalActionError,
    execute_proposal,
    mark_stale,
)
from ..services.tree import TreeError, TreeService
from .deps import get_session

router = APIRouter(prefix="/chat", tags=["chat"])


class SessionCreate(BaseModel):
    course_id: int | None = None
    node_id: int | None = None
    title: str = "New chat"
    use_embeddings: bool | None = None


class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    use_embeddings: bool | None = None


class SessionOut(BaseModel):
    id: int
    public_id: str
    course_id: int | None
    node_id: int | None
    title: str
    use_embeddings: bool | None
    created_at: datetime


class CitationOut(BaseModel):
    index: int
    chunk_id: int
    material_id: int
    title: str
    quote: str


class MentionOut(BaseModel):
    ref: str
    kind: str
    id: int
    title: str
    course_id: int | None = None
    summary: str | None = None


class ReadOut(BaseModel):
    ref: str
    kind: str
    id: int
    title: str
    course_id: int | None = None
    chars: int


class ToolCallOut(BaseModel):
    name: str
    argument: str
    phase: str | None = None
    result: str | None = None
    title: str | None = None
    status: str | None = None
    start_ms: int | None = None
    duration_ms: int | None = None


class ProposalOut(BaseModel):
    id: int
    action: str
    payload: dict[str, Any]
    status: str
    result: dict[str, Any] | None


class MessageOut(BaseModel):
    id: int
    role: str
    markdown: str
    blocks: list[dict[str, Any]]
    citations: list[CitationOut]
    mentions: list[MentionOut]
    reads: list[ReadOut]
    tool_calls: list[ToolCallOut]
    proposals: list[ProposalOut]
    grounded: bool | None
    trace: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    parent_id: int | None = None
    variant_index: int = 1
    variant_count: int = 1
    sibling_ids: list[int] = Field(default_factory=list)


AttachKind = Literal["material", "note", "quiz", "exercise", "node", "course"]


class AttachmentIn(BaseModel):
    kind: AttachKind
    id: int


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    attachments: list[AttachmentIn] | None = Field(default=None, max_length=10)


class TurnQueued(BaseModel):
    user_message: MessageOut
    job_id: int


def _chat_service(request: Request, session: Session) -> ChatService:
    return ChatService(session, request.app.state.gateway, request.app.state.embedder)


def _session_out(chat_session: Any) -> SessionOut:
    return SessionOut(
        id=chat_session.id,
        public_id=chat_session.public_id,
        course_id=chat_session.course_id,
        node_id=chat_session.node_id,
        title=chat_session.title,
        use_embeddings=chat_session.use_embeddings,
        created_at=chat_session.created_at,
    )


def _proposal_row_out(proposal: Any) -> ProposalOut:
    return ProposalOut(
        id=proposal.id,
        action=proposal.action,
        payload=proposal.payload,
        status=proposal.status,
        result=proposal.result,
    )


def _load_proposals(session: Session, message_ids: list[int]) -> dict[int, list[Any]]:
    from ..domain.models import ChatProposal

    if not message_ids:
        return {}
    rows = session.scalars(
        select(ChatProposal).where(ChatProposal.message_id.in_(message_ids))
    )
    grouped: dict[int, list[Any]] = {}
    for row in rows:
        grouped.setdefault(row.message_id, []).append(row)
    return grouped


def _message_out(
    message: Any,
    proposals: list[Any] | None = None,
    variant_index: int = 1,
    variant_count: int = 1,
    sibling_ids: list[int] | None = None,
) -> MessageOut:
    blocks: list[dict[str, Any]] = []
    for block in message.blocks or []:
        entry = dict(block)
        if entry.get("type") == "text" and message.mentions:
            entry["mentions"] = message.mentions
        blocks.append(entry)
    markdown = "\n\n".join(
        str(block.get("md", "")) for block in blocks if block.get("type") == "text"
    )
    citations = [
        CitationOut(
            index=c["index"],
            chunk_id=c["chunk_id"],
            material_id=c["material_id"],
            title=c["title"],
            quote=c["quote"],
        )
        for c in (message.citations or [])
    ]
    mentions = [
        MentionOut(
            ref=m["ref"],
            kind=m["kind"],
            id=m["id"],
            title=m["title"],
            course_id=m.get("course_id"),
            summary=m.get("summary"),
        )
        for m in (message.mentions or [])
    ]
    reads = [
        ReadOut(
            ref=r["ref"],
            kind=r["kind"],
            id=r["id"],
            title=r["title"],
            course_id=r.get("course_id"),
            chars=int(r.get("chars", 0)),
        )
        for r in (message.reads or [])
    ]
    tool_calls = [
        ToolCallOut(
            name=tc.get("name", ""),
            argument=tc.get("argument", ""),
            phase=tc.get("phase"),
            result=tc.get("result"),
            title=tc.get("title"),
            status=tc.get("status"),
            start_ms=tc.get("start_ms"),
            duration_ms=tc.get("duration_ms"),
        )
        for tc in (message.tool_calls or [])
    ]
    return MessageOut(
        id=message.id,
        role=message.role,
        markdown=markdown,
        blocks=blocks,
        citations=citations,
        mentions=mentions,
        reads=reads,
        tool_calls=tool_calls,
        proposals=[_proposal_row_out(row) for row in (proposals or [])],
        grounded=message.grounded,
        trace=message.trace,
        warnings=list(message.warnings or []),
        parent_id=message.parent_id,
        variant_index=variant_index,
        variant_count=variant_count,
        sibling_ids=sibling_ids or [],
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    request: Request,
    node_id: int | None = None,
    session: Session = Depends(get_session),
) -> list[SessionOut]:
    profile = ensure_default_profile(session)
    return [
        _session_out(entry)
        for entry in _chat_service(request, session).list_sessions(profile.id, node_id=node_id)
    ]


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(
    body: SessionCreate, request: Request, session: Session = Depends(get_session)
) -> SessionOut:
    profile = ensure_default_profile(session)
    try:
        node_id = TreeService(session).placement_node(body.course_id, body.node_id)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    chat_session = _chat_service(request, session).create_session(
        profile.id,
        course_id=body.course_id,
        node_id=node_id,
        title=body.title,
        use_embeddings=body.use_embeddings,
    )
    session.commit()
    return _session_out(chat_session)


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int,
    body: SessionUpdate,
    request: Request,
    session: Session = Depends(get_session),
) -> SessionOut:
    profile = ensure_default_profile(session)
    chat_session = _chat_service(request, session).get_session(session_id, profile.id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    if body.title is not None:
        chat_session.title = body.title.strip()[:300] or "New chat"
    if body.use_embeddings is not None:
        chat_session.use_embeddings = body.use_embeddings
    session.commit()
    return _session_out(chat_session)


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    chat_session = _chat_service(request, session).get_session(session_id, profile.id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    from ..services import trash

    deleted_item_id = trash.snapshot(
        session, "chat", chat_session.id, chat_session.title, profile.id
    )
    message_ids = list(
        session.scalars(
            select(ChatMessage.id).where(ChatMessage.session_id == chat_session.id)
        )
    )
    if message_ids:
        session.execute(
            delete(ChatProposal).where(ChatProposal.message_id.in_(message_ids))
        )
        session.execute(delete(ChatMessage).where(ChatMessage.id.in_(message_ids)))
    session.delete(chat_session)
    session.commit()
    return {"deleted_item_id": deleted_item_id}


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(
    session_id: int, request: Request, session: Session = Depends(get_session)
) -> list[MessageOut]:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    chat_session = service.get_session(session_id, profile.id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    messages = service.messages(session_id)
    proposals = _load_proposals(session, [message.id for message in messages])
    siblings = service.child_index(session_id)
    outputs: list[MessageOut] = []
    for message in messages:
        group = siblings.get(message.parent_id, [message.id])
        index = next(
            (i for i, mid in enumerate(group) if mid == message.id), 0
        )
        outputs.append(
            _message_out(
                message,
                proposals.get(message.id),
                variant_index=index + 1,
                variant_count=len(group),
                sibling_ids=group,
            )
        )
    return outputs


MAX_STATE_BYTES = 100_000


class StatePatchIn(BaseModel):
    delta: list[dict[str, Any]] = Field(min_length=1, max_length=200)


@router.patch("/messages/{message_id}/state")
def patch_message_state(
    message_id: int,
    body: StatePatchIn,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    message = session.get(ChatMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="message not found")
    chat_session = session.get(ChatSession, message.session_id)
    if chat_session is None or chat_session.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="message not found")
    state = copy.deepcopy(message.state) if message.state else {}
    try:
        apply_patch(state, body.delta)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        raise HTTPException(status_code=422, detail=f"invalid state patch: {error}") from error
    if len(json.dumps(state, ensure_ascii=False, default=str)) > MAX_STATE_BYTES:
        raise HTTPException(status_code=422, detail="widget state too large")
    message.state = state
    session.add(
        AiInteraction(
            context_type="widget_state",
            context_id=message_id,
            direction="patch",
            model=None,
            input_tokens=max(1, len(json.dumps(body.delta)) // 4),
            output_tokens=0,
            cost_usd=None,
            latency_ms=0,
        )
    )
    session.commit()
    return {"state": state}


def _load_proposal_for_profile(
    session: Session, proposal_id: int, profile_id: int
) -> tuple[ChatProposal, ChatSession]:
    proposal = session.get(ChatProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    message = session.get(ChatMessage, proposal.message_id)
    chat_session = (
        session.get(ChatSession, message.session_id) if message is not None else None
    )
    if chat_session is None or chat_session.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="proposal not found")
    return proposal, chat_session


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalOut)
def approve_proposal(
    proposal_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> ProposalOut:
    profile = ensure_default_profile(session)
    proposal, chat_session = _load_proposal_for_profile(session, proposal_id, profile.id)
    if proposal.status != "proposed":
        raise HTTPException(
            status_code=409, detail=f"proposal already {proposal.status}"
        )
    if proposal.action in GENERATE_ACTIONS:
        proposal.status = "approved"
        proposal.result = {"open_dialog": proposal.payload}
        session.commit()
        return _proposal_row_out(proposal)
    if chat_session.course_id is None:
        raise HTTPException(
            status_code=422, detail="chat session has no course to act on"
        )
    if proposal.action == "compose_material":
        result = _execute_compose_material(request, session, chat_session, proposal)
        if result is None:
            return _proposal_row_out(proposal)
    elif proposal.action == "create_note":
        try:
            result = _execute_create_note(session, profile.id, chat_session, proposal)
        except ProposalActionError as error:
            mark_stale(proposal, str(error))
            session.commit()
            return _proposal_row_out(proposal)
    else:
        try:
            status, result = execute_proposal(
                session,
                action=proposal.action,
                payload=proposal.payload or {},
                course_id=chat_session.course_id,
            )
        except ProposalActionError as error:
            mark_stale(proposal, str(error))
            session.commit()
            return _proposal_row_out(proposal)
        if status != "executed":
            raise HTTPException(
                status_code=422, detail=f"unexpected execution status {status}"
            )
    proposal.status = "executed"
    proposal.result = result
    proposal.executed_at = utcnow()
    session.add(
        AiInteraction(
            context_type="proposal",
            context_id=proposal.id,
            direction=f"execute {proposal.action}",
            model=None,
            input_tokens=max(1, len(str(proposal.payload)) // 4),
            output_tokens=0,
            cost_usd=None,
            latency_ms=0,
        )
    )
    session.commit()
    return _proposal_row_out(proposal)


def _execute_compose_material(
    request: Request,
    session: Session,
    chat_session: ChatSession,
    proposal: ChatProposal,
) -> dict[str, Any] | None:
    from ..pipelines.compose import ComposeError, ComposeService
    from ..services.context import ContextError, ContextResolver, ContextScope, ContextSpec
    from ..services.materials import MaterialsService

    payload = proposal.payload or {}
    course_id = chat_session.course_id
    if course_id is None:
        mark_stale(proposal, "chat session has no course")
        session.commit()
        return None
    try:
        bundle = ContextResolver(session, request.app.state.embedder.embed).resolve(
            ContextSpec(
                course_id=course_id,
                node_id=chat_session.node_id,
                scope=ContextScope.subtree,
                query=str(payload.get("title", "study material")),
                exclude_ai_composed=True,
            )
        )
        material = ComposeService(session, request.app.state.gateway).compose(
            profile_id=chat_session.profile_id,
            course_id=course_id,
            node_id=chat_session.node_id,
            kind=str(payload.get("kind", "study_guide")),
            title=payload.get("title"),
            instructions=payload.get("instructions"),
            context_bundle=bundle,
            blobs=request.app.state.blobs,
        )
    except (ComposeError, ContextError, ProviderError) as error:
        mark_stale(proposal, str(error))
        session.commit()
        return None
    job_id = MaterialsService(session, request.app.state.blobs).queue_ingest(
        material, request.app.state.jobs
    )
    return {"material_id": material.id, "job_id": job_id}


def _execute_create_note(
    session: Session, profile_id: int, chat_session: ChatSession, proposal: ChatProposal
) -> dict[str, Any]:
    payload = proposal.payload or {}
    try:
        node_id = TreeService(session).placement_node(
            chat_session.course_id, payload.get("node_id")
        )
    except TreeError as error:
        raise ProposalActionError(str(error)) from error
    title = str(payload.get("title", "")).strip()[:300] or "AI proposal"
    body_md = str(payload.get("body_md", ""))
    note = Note(
        profile_id=profile_id,
        course_id=chat_session.course_id,
        node_id=node_id,
        title=title,
        body=[{"type": "text", "md": body_md}],
        tags=["ai-proposal"],
    )
    note.search_text = f"{note.title}\n{body_md}"
    session.add(note)
    session.flush()
    return {"note_id": note.id}


@router.post("/proposals/{proposal_id}/dismiss", response_model=ProposalOut)
def dismiss_proposal(
    proposal_id: int, session: Session = Depends(get_session)
) -> ProposalOut:
    profile = ensure_default_profile(session)
    proposal, _chat_session = _load_proposal_for_profile(session, proposal_id, profile.id)
    if proposal.status != "proposed":
        raise HTTPException(
            status_code=409, detail=f"proposal already {proposal.status}"
        )
    proposal.status = "dismissed"
    session.commit()
    return _proposal_row_out(proposal)


@router.get("/sessions/{session_id}/context")
def session_context(
    session_id: int, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    chat_session = service.get_session(session_id, profile.id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    registry = registry_from_json(chat_session.mention_registry)
    node = None
    if chat_session.node_id is not None:
        tree_node = session.get(TreeNode, chat_session.node_id)
        if tree_node is not None:
            node = {"id": tree_node.id, "title": tree_node.title}
    return {
        "session_id": chat_session.id,
        "course_id": chat_session.course_id,
        "node": node,
        "registry": [
            entry.as_dict() for entry in registry.entries()
        ],
        "latest_notes": [
            {"id": note.id, "title": note.title}
            for note in service.latest_notes_preview(chat_session)
        ],
    }


class BranchNodeOut(BaseModel):
    id: int
    role: str
    excerpt: str
    parent_id: int | None
    children: list[int]
    active_child_id: int | None


@router.get("/sessions/{session_id}/tree")
def session_branch_tree(
    session_id: int, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    chat_session = service.get_session(session_id, profile.id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    rows = service.all_messages(session_id)
    children: dict[int | None, list[int]] = {}
    for row in rows:
        children.setdefault(row.parent_id, []).append(row.id)
    for ids in children.values():
        ids.sort()

    def excerpt(row: ChatMessage) -> str:
        for block in row.blocks or []:
            if block.get("type") == "text":
                text = str(block.get("md", "")).strip().replace("\n", " ")
                return text[:100]
        return ""

    nodes = [
        BranchNodeOut(
            id=row.id,
            role=row.role,
            excerpt=excerpt(row),
            parent_id=row.parent_id,
            children=children.get(row.id, []),
            active_child_id=row.active_child_id,
        )
        for row in rows
    ]
    return {
        "active_root_id": chat_session.active_root_id,
        "nodes": [node.model_dump() for node in nodes],
    }


@router.post("/sessions/{session_id}/messages", response_model=TurnQueued)
def send_message(
    session_id: int,
    body: MessageIn,
    request: Request,
    session: Session = Depends(get_session),
) -> TurnQueued:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    chat_session = service.get_session(session_id, profile.id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    try:
        stored_mentions = service.attach(
            chat_session,
            [item.model_dump() for item in body.attachments or []],
        )
    except ChatError as error:
        status = 404 if "not found" in str(error) else 422
        raise HTTPException(status_code=status, detail=str(error)) from error
    with _session_turn_lock(session_id):
        user_message = service.add_message(
            session_id,
            "user",
            body.content.strip(),
            mentions=stored_mentions or None,
            parent_id=service.active_tip(session_id),
        )
        job = JobRunner.enqueue(
            session,
            "chat_turn",
            {"chat_session_id": session_id, "user_message_id": user_message.id},
        )
    session.commit()
    request.app.state.jobs.wake()
    return TurnQueued(user_message=_message_out(user_message), job_id=job.id)


def _load_message_for_profile(
    session: Session, message_id: int, profile_id: int
) -> tuple[ChatMessage, ChatSession]:
    message = session.get(ChatMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="chat message not found")
    chat_session = session.get(ChatSession, message.session_id)
    if chat_session is None or chat_session.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="chat message not found")
    return message, chat_session


class EditIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


@router.post("/messages/{message_id}/edit", response_model=TurnQueued)
def edit_message(
    message_id: int,
    body: EditIn,
    request: Request,
    session: Session = Depends(get_session),
) -> TurnQueued:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    message, chat_session = _load_message_for_profile(session, message_id, profile.id)
    if message.role != "user":
        raise HTTPException(
            status_code=422, detail="only user messages can be edited"
        )
    with _session_turn_lock(chat_session.id):
        branched = service.branch_message(message, body.content.strip())
        job = JobRunner.enqueue(
            session,
            "chat_turn",
            {"chat_session_id": chat_session.id, "user_message_id": branched.id},
        )
    session.commit()
    request.app.state.jobs.wake()
    return TurnQueued(user_message=_message_out(branched), job_id=job.id)


@router.post("/messages/{message_id}/regenerate", response_model=TurnQueued)
def regenerate_message(
    message_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> TurnQueued:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    message, chat_session = _load_message_for_profile(session, message_id, profile.id)
    if message.role != "user":
        raise HTTPException(
            status_code=422, detail="only assistant answers can be regenerated"
        )
    with _session_turn_lock(chat_session.id):
        service.select_message(message)
        job = JobRunner.enqueue(
            session,
            "chat_turn",
            {"chat_session_id": chat_session.id, "user_message_id": message.id},
        )
    session.commit()
    request.app.state.jobs.wake()
    return TurnQueued(user_message=_message_out(message), job_id=job.id)


@router.post("/messages/{message_id}/select", response_model=list[MessageOut])
def select_message(
    message_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> list[MessageOut]:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    message, chat_session = _load_message_for_profile(session, message_id, profile.id)
    service.select_message(message)
    session.commit()
    return list_messages(session_id=chat_session.id, request=request, session=session)


_TURN_LOCKS: dict[int, threading.Lock] = {}
_TURN_LOCKS_GUARD = threading.Lock()
_STOP_EVENTS: dict[int, threading.Event] = {}


def _session_turn_lock(session_id: int) -> threading.Lock:
    with _TURN_LOCKS_GUARD:
        lock = _TURN_LOCKS.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _TURN_LOCKS[session_id] = lock
        return lock


def _register_stop_event(session_id: int) -> threading.Event:
    with _TURN_LOCKS_GUARD:
        event = threading.Event()
        _STOP_EVENTS[session_id] = event
        return event


def _release_stop_event(session_id: int, event: threading.Event) -> None:
    with _TURN_LOCKS_GUARD:
        if _STOP_EVENTS.get(session_id) is event:
            del _STOP_EVENTS[session_id]


@router.post("/sessions/{session_id}/stop")
def stop_session_turn(
    session_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    if service.get_session(session_id, profile.id) is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    with _TURN_LOCKS_GUARD:
        event = _STOP_EVENTS.get(session_id)
    if event is not None:
        event.set()
    return {"stopped": event is not None}


def make_chat_turn_handler(gateway: Any, embedder: Any, bus: EventBus) -> JobHandler:
    def handler(session: Session, job: Any, report: Any) -> None:
        payload: dict[str, Any] = job.payload or {}
        chat_session = session.get(ChatSession, payload.get("chat_session_id"))
        if chat_session is None:
            raise JobError("chat session not found")
        turn_lock = _session_turn_lock(chat_session.id)
        turn_lock.acquire()
        try:
            service = ChatService(session, gateway, embedder)
            messages = service.messages(chat_session.id)
            target_id = payload.get("user_message_id")
            if target_id is not None:
                pending = session.get(ChatMessage, int(target_id))
                if (
                    pending is None
                    or pending.session_id != chat_session.id
                    or pending.role != "user"
                ):
                    raise JobError("pending user message not found")
            else:
                if not messages or messages[-1].role != "user":
                    raise JobError("no pending user message")
                pending = messages[-1]
            service.chain_under_later_reply(pending)

            def emit(event: dict[str, Any]) -> None:
                bus.publish_threadsafe(f"chat:{chat_session.id}", event)

            stop_event = _register_stop_event(chat_session.id)
            try:
                service.answer_streaming(chat_session, pending, emit, stop=stop_event)
            except Exception as error:
                emit(
                    {
                        "type": "turn_error",
                        "detail": str(error)[:300] or error.__class__.__name__,
                    }
                )
                raise
            finally:
                _release_stop_event(chat_session.id, stop_event)
            session.commit()
        finally:
            turn_lock.release()

    return handler
