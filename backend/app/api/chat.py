import copy
import json
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from ..ai.flow_events_chat import flow_failed_event
from ..ai.gateway import ProviderError, TaskUnassigned
from ..ai.mentions import registry_from_json
from ..ai.proposals import GENERATE_ACTIONS
from ..ai.tokenizers import embedding_accounting, token_count
from ..core.errors import sanitize_error_detail
from ..core.events import EventBus
from ..core.jsonpatch import apply_patch
from ..core.vocab import ChatProposalStatus, WsTopic
from ..domain.models import (
    AiInteraction,
    ChatMessage,
    ChatProposal,
    ChatSession,
    Note,
    QuizmeAnswer,
    TreeNode,
    utcnow,
)
from ..domain.payloads import ChatTrace, ProposalPayload, ProposalResult, TurnFailure
from ..domain.proposal_contract import ProposalPayloadError, validate_proposal_payload
from ..jobs.runner import JobError, JobHandler, JobRunner
from ..services.knowledge.tree import TreeError, TreeService
from ..services.platform.chat.errors import ChatError
from ..services.platform.chat.service import ChatService, proposal_out
from ..services.platform.profiles import ensure_default_profile
from ..services.platform.proposal_actions import (
    POSTPROCESS_ACTIONS,
    ProposalActionError,
    ProposalContext,
    execute_proposal,
    mark_stale,
    proposal_full_payload,
)
from ..services.platform.quizme import (
    clear_pending,
    pending_state,
    quiz_public_state,
    store_pending,
)
from .deps import get_session

router = APIRouter(prefix="/chat", tags=["chat"])


class SessionCreate(BaseModel):
    course_id: str | None = None
    node_id: str | None = None
    title: str = "New chat"
    use_embeddings: bool | None = None


class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    use_embeddings: bool | None = None
    quizme: bool | None = None


class QuizPendingOut(BaseModel):
    question: str | None = None
    choices: list[str] | None = None
    answered: bool = False
    verdict: str | None = None
    verdict_detail: str | None = None
    student_answer: str | None = None
    expected_display: str | None = None


class SessionOut(BaseModel):
    id: str
    public_id: str
    course_id: str | None
    node_id: str | None
    title: str
    use_embeddings: bool | None
    quizme: bool = False
    quiz_pending: QuizPendingOut | None = None
    created_at: datetime


class CitationOut(BaseModel):
    index: int
    chunk_id: str
    material_id: str
    title: str
    quote: str


class MentionOut(BaseModel):
    ref: str
    kind: str
    id: str
    title: str
    course_id: str | None = None
    summary: str | None = None


class ReadOut(BaseModel):
    ref: str
    kind: str
    id: str
    title: str
    course_id: str | None = None
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
    quiz: dict[str, Any] | None = None


class ProposalOut(BaseModel):
    id: str
    action: str
    payload: dict[str, Any]
    status: str
    result: ProposalResult | None
    message_id: str | None = None
    session_id: str | None = None


class ProposalListOut(BaseModel):
    proposals: list[ProposalOut]
    next_cursor: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    markdown: str
    blocks: list[dict[str, Any]]
    citations: list[CitationOut]
    mentions: list[MentionOut]
    reads: list[ReadOut]
    tool_calls: list[ToolCallOut]
    proposals: list[ProposalOut]
    grounded: bool | None
    trace: ChatTrace | None = None
    warnings: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    state: dict[str, Any] | None = None
    variant_index: int = 1
    variant_count: int = 1
    sibling_ids: list[str] = Field(default_factory=list)


AttachKind = Literal["material", "note", "quiz", "exercise", "node", "course"]


class AttachmentIn(BaseModel):
    kind: AttachKind
    id: str


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    attachments: list[AttachmentIn] | None = Field(default=None, max_length=10)


class TurnQueued(BaseModel):
    user_message: MessageOut
    job_id: str


class SessionDeletedOut(BaseModel):
    deleted_item_id: str


def _chat_service(request: Request, session: Session) -> ChatService:
    return ChatService(
        session,
        request.app.state.gateway,
        request.app.state.embedder,
        search_transport=getattr(request.app.state, "search_transport", None),
    )


def _session_out(chat_session: Any) -> SessionOut:
    return SessionOut(
        id=chat_session.id,
        public_id=chat_session.public_id,
        course_id=chat_session.course_id,
        node_id=chat_session.node_id,
        title=chat_session.title,
        use_embeddings=chat_session.use_embeddings,
        quizme=bool(chat_session.quizme),
        quiz_pending=_quiz_pending_out(chat_session),
        created_at=chat_session.created_at,
    )


def _quiz_pending_out(chat_session: Any) -> QuizPendingOut | None:
    public = quiz_public_state(pending_state(chat_session.quiz_pending_row))
    return QuizPendingOut(**public) if public else None


def _proposal_row_out(proposal: Any) -> ProposalOut:
    """One shared card serializer (plan 78-E): the WS path (`proposal_out`
    in the chat service) and this REST path produce the same shape."""
    return ProposalOut(**proposal_out(proposal))


@router.get("/proposals", response_model=ProposalListOut)
def list_proposals(
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Cross-session pending/inbox surface (plan 78-E): profile-scoped
    proposal cards, newest first, for resolution from outside the chat."""
    profile = ensure_default_profile(session)
    filters = [ChatSession.profile_id == profile.id]
    if status is not None:
        try:
            status_value = ChatProposalStatus(status).value
        except ValueError as error:
            raise HTTPException(
                status_code=422, detail=f"unknown proposal status {status!r}"
            ) from error
        filters.append(ChatProposal.status == status_value)
    if cursor is not None:
        created_raw, _sep, before_id = cursor.partition("|")
        try:
            before_created = datetime.fromisoformat(created_raw)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="invalid cursor") from error
        filters.append(
            or_(
                ChatProposal.created_at < before_created,
                and_(
                    ChatProposal.created_at == before_created,
                    ChatProposal.id < before_id,
                ),
            )
        )
    rows = session.execute(
        select(ChatProposal, ChatMessage.session_id)
        .join(ChatMessage, ChatProposal.message_id == ChatMessage.id)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(*filters)
        .order_by(ChatProposal.created_at.desc(), ChatProposal.id.desc())
        .limit(limit + 1)
    ).all()
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1][0]
        next_cursor = f"{last.created_at.isoformat()}|{last.id}"
    proposals = [
        ProposalOut(
            **proposal_out(proposal),
            message_id=proposal.message_id,
            session_id=chat_session_id,
        )
        for proposal, chat_session_id in rows
    ]
    return {"proposals": proposals, "next_cursor": next_cursor}


def _load_proposals(session: Session, message_ids: list[str]) -> dict[str, list[Any]]:
    from ..domain.models import ChatProposal

    if not message_ids:
        return {}
    rows = session.scalars(select(ChatProposal).where(ChatProposal.message_id.in_(message_ids)))
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        grouped.setdefault(row.message_id, []).append(row)
    return grouped


def _message_out(
    message: Any,
    proposals: list[Any] | None = None,
    variant_index: int = 1,
    variant_count: int = 1,
    sibling_ids: list[str] | None = None,
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
            quiz=tc.get("quiz"),
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
        state=message.state,
        variant_index=variant_index,
        variant_count=variant_count,
        sibling_ids=sibling_ids or [],
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    request: Request,
    node_id: str | None = None,
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
    session_id: str,
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
    if body.quizme is not None:
        chat_session.quizme = body.quizme
        if not body.quizme:
            clear_pending(session, chat_session)
    session.commit()
    return _session_out(chat_session)


@router.delete("/sessions/{session_id}", response_model=SessionDeletedOut)
def delete_session(
    session_id: str, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    chat_session = _chat_service(request, session).get_session(session_id, profile.id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    from ..services.platform import trash

    deleted_item_id = trash.snapshot(
        session, "chat", chat_session.id, chat_session.title, profile.id
    )
    message_ids = list(
        session.scalars(select(ChatMessage.id).where(ChatMessage.session_id == chat_session.id))
    )
    if message_ids:
        session.execute(delete(ChatProposal).where(ChatProposal.message_id.in_(message_ids)))
        session.execute(delete(ChatMessage).where(ChatMessage.id.in_(message_ids)))
    session.delete(chat_session)
    session.commit()
    return {"deleted_item_id": deleted_item_id}


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(
    session_id: str, request: Request, session: Session = Depends(get_session)
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
        index = next((i for i, mid in enumerate(group) if mid == message.id), 0)
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


class MessageStateOut(BaseModel):
    state: dict[str, Any]


@router.patch("/messages/{message_id}/state", response_model=MessageStateOut)
def patch_message_state(
    message_id: str,
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
    accounting = embedding_accounting(session)
    session.add(
        AiInteraction(
            context_type="widget_state",
            context_id=message_id,
            direction="patch",
            model=None,
            input_tokens=token_count(json.dumps(body.delta), accounting),
            output_tokens=0,
            cost_usd=None,
            latency_ms=0,
            metadata_json=accounting.metadata(),
        )
    )
    session.commit()
    return {"state": state}


def _load_proposal_for_profile(
    session: Session, proposal_id: str, profile_id: str
) -> tuple[ChatProposal, ChatSession]:
    proposal = session.get(ChatProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    message = session.get(ChatMessage, proposal.message_id)
    chat_session = session.get(ChatSession, message.session_id) if message is not None else None
    if chat_session is None or chat_session.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="proposal not found")
    return proposal, chat_session


def _conflict_refresh(
    session: Session,
    proposal: ChatProposal,
    chat_session: ChatSession,
) -> bool:
    """Re-diff an edit-in-place card whose target moved (plan 78-D).

    Refreshes the snapshot, re-resolves anchored text edits against the
    current content and flips the card to ``conflict`` so the user reviews
    the recomputed change and approves again. Returns False when the card
    is unaffected; raises ``ProposalActionError`` when the anchors no
    longer match the moved content (an honest stale).
    """
    from ..ai.proposals import (
        PROPOSAL_ACTIONS,
        TextEditOp,
        resolve_text_edits,
    )

    spec = PROPOSAL_ACTIONS.get(proposal.action)
    if spec is None or spec.snapshot is None:
        return False
    payload = dict(proposal.payload or {})
    from ..services.platform.proposal_actions import capture_proposal_snapshot

    current = capture_proposal_snapshot(
        session,
        action=proposal.action,
        payload=payload,
        course_id=chat_session.course_id or "",
    )
    if current is None:
        return False
    if current == str(proposal.original_md or ""):
        return False
    if proposal.anchors:
        resolved = resolve_text_edits(
            current,
            [
                TextEditOp.model_validate(
                    {"op": anchor.op, "find": anchor.find_text, "text": anchor.text}
                )
                for anchor in proposal.anchors
            ],
        )
        payload[("new_body_md" if proposal.action == "edit_note" else "new_markdown")] = resolved
    proposal.payload = cast(ProposalPayload, payload)
    proposal.original_md = current
    proposal.status = ChatProposalStatus.CONFLICT.value
    proposal.result = cast(
        ProposalResult,
        {
            "conflict": (
                "target changed since this proposal was made — "
                "the diff was refreshed; review and approve again"
            )
        },
    )
    return True


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalOut)
def approve_proposal(
    proposal_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> ProposalOut:
    profile = ensure_default_profile(session)
    proposal, chat_session = _load_proposal_for_profile(session, proposal_id, profile.id)
    try:
        validate_proposal_payload(proposal.action, proposal.payload or {})
    except ProposalPayloadError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if proposal.status not in ChatProposalStatus.resolvable():
        raise HTTPException(status_code=409, detail=f"proposal already {proposal.status}")
    if proposal.action in GENERATE_ACTIONS:
        proposal.status = ChatProposalStatus.APPROVED.value
        proposal.result = {"open_dialog": proposal.payload}
        session.commit()
        return _proposal_row_out(proposal)
    if chat_session.course_id is None:
        raise HTTPException(status_code=422, detail="chat session has no course to act on")
    try:
        if _conflict_refresh(session, proposal, chat_session):
            session.commit()
            return _proposal_row_out(proposal)
    except ProposalActionError:
        mark_stale(proposal, "the quoted text no longer appears in the content")
        session.commit()
        return _proposal_row_out(proposal)
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
                payload=proposal_full_payload(proposal),
                course_id=chat_session.course_id,
                context=ProposalContext(
                    blobs=request.app.state.blobs,
                    jobs=request.app.state.jobs,
                    profile_id=profile.id,
                ),
            )
        except ProposalActionError as error:
            mark_stale(proposal, str(error))
            session.commit()
            return _proposal_row_out(proposal)
        if status != "executed":
            raise HTTPException(status_code=422, detail=f"unexpected execution status {status}")
        if proposal.action in POSTPROCESS_ACTIONS:
            request.app.state.jobs.wake()
    proposal.status = ChatProposalStatus.EXECUTED.value
    proposal.result = cast(ProposalResult, result)
    proposal.executed_at = utcnow()
    accounting = embedding_accounting(session)
    session.add(
        AiInteraction(
            context_type="proposal",
            context_id=proposal.id,
            direction=f"execute {proposal.action}",
            model=None,
            input_tokens=token_count(str(proposal.payload), accounting),
            output_tokens=0,
            cost_usd=None,
            latency_ms=0,
            metadata_json=accounting.metadata(),
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
    from ..services.content.materials import MaterialsService
    from ..services.knowledge.context import (
        ContextError,
        ContextResolver,
        ContextScope,
        ContextSpec,
    )

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
    session: Session, profile_id: str, chat_session: ChatSession, proposal: ChatProposal
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
def dismiss_proposal(proposal_id: str, session: Session = Depends(get_session)) -> ProposalOut:
    profile = ensure_default_profile(session)
    proposal, _chat_session = _load_proposal_for_profile(session, proposal_id, profile.id)
    if proposal.status != "proposed":
        raise HTTPException(status_code=409, detail=f"proposal already {proposal.status}")
    proposal.status = ChatProposalStatus.DISMISSED.value
    session.commit()
    return _proposal_row_out(proposal)


class ContextNodeOut(BaseModel):
    id: str
    title: str


class MentionRefOut(BaseModel):
    ref: str
    kind: str
    id: str
    title: str
    course_id: str | None = None
    summary: str | None = None


class NotePreviewOut(BaseModel):
    id: str
    title: str


class SessionContextOut(BaseModel):
    session_id: str
    course_id: str | None
    node: ContextNodeOut | None
    registry: list[MentionRefOut]
    latest_notes: list[NotePreviewOut]


@router.get("/sessions/{session_id}/context", response_model=SessionContextOut)
def session_context(
    session_id: str, request: Request, session: Session = Depends(get_session)
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
        "registry": [entry.as_dict() for entry in registry.entries()],
        "latest_notes": [
            {"id": note.id, "title": note.title}
            for note in service.latest_notes_preview(chat_session)
        ],
    }


class BranchNodeOut(BaseModel):
    id: str
    role: str
    excerpt: str
    parent_id: str | None
    children: list[str]
    active_child_id: str | None


class BranchTreeOut(BaseModel):
    active_root_id: str | None
    nodes: list[BranchNodeOut]


@router.get("/sessions/{session_id}/tree", response_model=BranchTreeOut)
def session_branch_tree(
    session_id: str, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    chat_session = service.get_session(session_id, profile.id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    rows = service.all_messages(session_id)
    children: dict[str | None, list[str]] = {}
    for row in rows:
        children.setdefault(row.parent_id, []).append(row.id)

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
        "nodes": nodes,
    }


@router.post("/sessions/{session_id}/messages", response_model=TurnQueued)
def send_message(
    session_id: str,
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
    with request.app.state.turn_locks.get(session_id):
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
    session: Session, message_id: str, profile_id: str
) -> tuple[ChatMessage, ChatSession]:
    message = session.get(ChatMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="chat message not found")
    chat_session = session.get(ChatSession, message.session_id)
    if chat_session is None or chat_session.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="chat message not found")
    return message, chat_session


class QuizAnswerIn(BaseModel):
    answer: str | int


class QuizAnswerOut(BaseModel):
    correct: bool
    verdict_detail: str
    expected_display: str | None = None
    user_message_id: str
    job_id: str | None


@router.post("/sessions/{session_id}/quiz-answer", response_model=QuizAnswerOut)
def answer_quiz_question(
    session_id: str,
    body: QuizAnswerIn,
    request: Request,
    session: Session = Depends(get_session),
) -> QuizAnswerOut:
    from ..services.platform.quizme import grade_answer

    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    chat_session = service.get_session(session_id, profile.id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    pending = pending_state(chat_session.quiz_pending_row)
    if not isinstance(pending, dict) or not pending.get("question"):
        raise HTTPException(status_code=409, detail="no quiz question is pending")
    if pending.get("verdict") is not None:
        raise HTTPException(status_code=409, detail="this question was already answered")
    correct, detail = grade_answer(pending, body.answer)
    pending["verdict"] = "correct" if correct else "incorrect"
    pending["verdict_detail"] = detail
    pending["student_answer"] = str(body.answer)
    pending["awaiting_answer"] = False
    store_pending(session, chat_session, pending)
    session.add(QuizmeAnswer(profile_id=profile.id, session_id=session_id, correct=correct))

    expected_display: str | None = None
    if pending.get("choices") is not None and isinstance(pending.get("expected_index"), int):
        choices = pending["choices"]
        expected_display = str(choices[pending["expected_index"]])
    else:
        expected_display = pending.get("expected_latex") or pending.get("expected_text")

    _mark_quiz_entry_answered(session, session_id, pending, correct, expected_display)

    user_message = service.add_message(
        session_id,
        "user",
        str(body.answer),
        parent_id=service.active_tip(session_id),
    )
    job = JobRunner.enqueue(
        session,
        "chat_turn",
        {"chat_session_id": session_id, "user_message_id": user_message.id},
    )
    session.commit()
    request.app.state.jobs.wake()
    return QuizAnswerOut(
        correct=correct,
        verdict_detail=detail,
        expected_display=expected_display,
        user_message_id=user_message.id,
        job_id=job.id,
    )


def _mark_quiz_entry_answered(
    session: Session,
    session_id: str,
    pending: dict[str, Any],
    correct: bool,
    expected_display: str | None,
) -> None:
    messages: list[ChatMessage] = list(
        session.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(10)
        )
    )
    question = str(pending.get("question", ""))
    for message in messages:
        for entry in message.tool_calls or []:
            if entry.get("name") != "QUIZ":
                continue
            quiz = entry.get("quiz") or {}
            if quiz.get("question") != question or quiz.get("answered"):
                continue
            quiz["answered"] = True
            quiz["verdict"] = "correct" if correct else "incorrect"
            quiz["student_answer"] = str(pending.get("student_answer"))
            quiz["expected_display"] = expected_display
            message.tool_calls = list(message.tool_calls or [])
            return


class EditIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


@router.post("/messages/{message_id}/edit", response_model=TurnQueued)
def edit_message(
    message_id: str,
    body: EditIn,
    request: Request,
    session: Session = Depends(get_session),
) -> TurnQueued:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    message, chat_session = _load_message_for_profile(session, message_id, profile.id)
    if message.role != "user":
        raise HTTPException(status_code=422, detail="only user messages can be edited")
    with request.app.state.turn_locks.get(chat_session.id):
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
    message_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> TurnQueued:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    message, chat_session = _load_message_for_profile(session, message_id, profile.id)
    if message.role != "user":
        raise HTTPException(status_code=422, detail="only assistant answers can be regenerated")
    with request.app.state.turn_locks.get(chat_session.id):
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
    message_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> list[MessageOut]:
    profile = ensure_default_profile(session)
    service = _chat_service(request, session)
    message, chat_session = _load_message_for_profile(session, message_id, profile.id)
    service.select_message(message)
    session.commit()
    return list_messages(session_id=chat_session.id, request=request, session=session)


class SessionTurnLocks:
    """Per-app serialization of chat turns.

    Locks are keyed by chat session id, so the map must live on the app
    instance: a module-global would let a leaked handler thread from one app
    instance block the same-numbered session in a different app (fresh DB,
    reused ids — exactly what the test suite does).
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def get(self, session_id: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[session_id] = lock
            return lock


_STOP_EVENTS: dict[str, threading.Event] = {}
_TURN_LOCKS_GUARD = threading.Lock()


def _register_stop_event(session_id: str) -> threading.Event:
    with _TURN_LOCKS_GUARD:
        event = threading.Event()
        _STOP_EVENTS[session_id] = event
        return event


def _release_stop_event(session_id: str, event: threading.Event) -> None:
    with _TURN_LOCKS_GUARD:
        if _STOP_EVENTS.get(session_id) is event:
            del _STOP_EVENTS[session_id]


class StopOut(BaseModel):
    stopped: bool


@router.post("/sessions/{session_id}/stop", response_model=StopOut)
def stop_session_turn(
    session_id: str,
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


def make_chat_turn_handler(
    gateway: Any,
    embedder: Any,
    bus: EventBus,
    turn_engine_provider: Callable[[], Any] | None = None,
    search_transport_provider: Callable[[], Any] | None = None,
    turn_locks: SessionTurnLocks | None = None,
) -> JobHandler:
    locks = turn_locks if turn_locks is not None else SessionTurnLocks()

    def handler(session: Session, job: Any, report: Any) -> None:
        payload: dict[str, Any] = job.payload or {}
        chat_session = session.get(ChatSession, payload.get("chat_session_id"))
        if chat_session is None:
            raise JobError("chat session not found")
        turn_lock = locks.get(chat_session.id)
        turn_lock.acquire()
        try:
            service = ChatService(
                session,
                gateway,
                embedder,
                search_transport=(
                    search_transport_provider() if search_transport_provider else None
                ),
            )
            messages = service.messages(chat_session.id)
            target_id = payload.get("user_message_id")
            if target_id is not None:
                pending = session.get(ChatMessage, str(target_id))
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
            session.commit()

            def emit(event: dict[str, Any]) -> None:
                bus.publish_threadsafe(WsTopic.chat(chat_session.id), event)

            stop_event = _register_stop_event(chat_session.id)
            try:
                turn_engine = turn_engine_provider() if turn_engine_provider is not None else None
                if turn_engine is None:
                    raise JobError("chat turn engine is not available")
                turn_engine.run(session, service, gateway, chat_session, pending, emit, stop_event)
            except Exception as error:
                detail = sanitize_error_detail(str(error)) or error.__class__.__name__
                code = "ai_not_configured" if isinstance(error, TaskUnassigned) else "turn_error"
                emit(flow_failed_event(code, detail))
                # Persist the failure on the turn (uniform chat error
                # display): the transcript keeps rendering it after a
                # refresh, with Retry through the regenerate endpoint.
                failure = service.add_message(
                    chat_session.id, "assistant", "", parent_id=pending.id
                )
                failure.state = {"turn_failed": TurnFailure(code=code, detail=detail)}
                session.commit()
                raise
            finally:
                _release_stop_event(chat_session.id, stop_event)
            session.commit()
        finally:
            turn_lock.release()

    return handler
