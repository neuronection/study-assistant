"""`ChatService`: session/message/branch CRUD, turn orchestration, thin
proposal glue over `platform/proposal_actions.py` (family plan 40 W1).
"""

import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....ai.contracts.contracts import (
    CHAT_ANSWER_CONTRACT,
    CITATION_RE,
    Constraint,
    ValidationResult,
)
from ....ai.flow_events_chat import flow_finished_event, flow_interrupted_event
from ....ai.gateway import LLMGateway, Message
from ....ai.mcp_resources import build_resource_tool_doc
from ....ai.mentions import MentionRegistry
from ....ai.parsing import blocks_to_md as _blocks_to_md
from ....ai.parsing import parse_answer_blocks
from ....ai.proposals import (
    DISMISSAL_NOTE,
    MAX_PROPOSALS_PER_TURN,
    PROPOSAL_DOC,
    ProposalError,
    TextEditOp,
    drop_code,
    extract_proposals_with_drops,
    filter_ungrounded,
    resolve_text_edits,
    strip_proposal_fences,
)
from ....ai.skills import CHAT_ANSWER_SYSTEM
from ....ai.tokenizers import (
    TokenAccounting,
    embedding_accounting,
)
from ....ai.tokenizers import (
    token_count as _token_count,
)
from ....ai.tools import CHAT_TOOL_DOC, QUIZ_TOOL_DOC
from ....ai.widgets import CHAT_WIDGET_DOC
from ....core.vocab import ChatProposalStatus
from ....domain.models import (
    AiInteraction,
    ChatMessage,
    ChatProposal,
    ChatSession,
    TreeNode,
)
from ....domain.payloads import ChatSessionContext
from ..proposal_actions import (
    capture_proposal_snapshot,
    proposal_full_payload,
    resolve_proposal_target,
    store_proposal_state,
)
from ..quizme import QUIZME_SYSTEM, pending_state
from ..skills import SkillService
from .tools import ToolsMixin
from .turn_context import EXERCISE_GUARD_RULE, QUIZ_GUARD_RULE, TurnContextMixin

logger = structlog.get_logger(__name__)

CHAT_TASK = "chat"
CHAT_SKILL = "chat.answer"
STOP_MESSAGE = "generation stopped by user"
MAX_REPAIR_ROUNDS = 1
MAX_TOOL_ROUNDS = 2
MAX_READ_ROUNDS = 3
MAX_STATE_ROUNDS = 3
MAX_RESOURCE_ROUNDS = 5
MAX_SEARCH_ROUNDS = 2
MAX_DISCOVER_ROUNDS = 2
DISCOVER_RESULT_CAP = 5
MAX_FETCH_ROUNDS = 1
MAX_FIND_ROUNDS = 2
MAX_QUIZ_ROUNDS = 2
READ_CHARS = 4000
FIND_RESULT_LIMIT = 5
HISTORY_TURNS = 8
RETRIEVE_LIMIT = 6
REGISTRY_MATERIALS_CAP = 30
STRUCTURE_GROUP_CAP = 8
STRUCTURE_SUMMARY_CHARS = 80
NODE_MATERIALS_REG_CAP = 10
READ_NODE_CHILDREN_CAP = 8

Emitter = Callable[[dict[str, Any]], None]


@dataclass
class TurnPrep:
    """Everything a chat turn needs before the first model call.

    Built once per turn by `ChatService.prepare_turn_context` +
    `prepare_turn_contract` and consumed by the LangGraph chat-turn engine's
    nodes, so context assembly, contract selection, and persistence stay in
    one place.
    """

    history: list[ChatMessage]
    chunks: list[dict[str, Any]]
    sources_block: str
    registry: MentionRegistry
    guard_rule_text: str | None
    proposals_enabled: bool
    dismissal_note: bool
    context: dict[str, Any]
    question: str
    system_base: str = ""
    contract: list[Constraint] = field(default_factory=list)
    skill_version_id: str | None = None
    turn_warning: str | None = None
    proposal_feedback: str | None = None


def _count_tokens(text: str, accounting: TokenAccounting) -> int:
    return _token_count(text, accounting)


class ChatService(ToolsMixin, TurnContextMixin):
    def __init__(
        self,
        session: Session,
        gateway: LLMGateway,
        embedder: Any,
        search_transport: Any = None,
    ) -> None:
        self._session = session
        self._gateway = gateway
        self._embedder = embedder
        self._search_transport = search_transport

    def create_session(
        self,
        profile_id: str,
        course_id: str | None = None,
        node_id: str | None = None,
        title: str = "New chat",
        context: dict[str, Any] | None = None,
        use_embeddings: bool | None = None,
    ) -> ChatSession:
        chat_session = ChatSession(
            profile_id=profile_id,
            course_id=course_id,
            node_id=node_id,
            title=title.strip() or "New chat",
            context=context,
            use_embeddings=use_embeddings,
        )
        self._session.add(chat_session)
        self._session.flush()
        return chat_session

    def list_sessions(self, profile_id: str, node_id: str | None = None) -> list[ChatSession]:
        statement = select(ChatSession).where(ChatSession.profile_id == profile_id)
        if node_id is not None:
            statement = statement.where(ChatSession.node_id == node_id)
        return list(
            self._session.scalars(
                statement.order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
            )
        )

    def get_session(self, session_id: str, profile_id: str) -> ChatSession | None:
        chat_session = self._session.get(ChatSession, session_id)
        if chat_session is None or chat_session.profile_id != profile_id:
            return None
        return chat_session

    def all_messages(self, chat_session_id: str) -> list[ChatMessage]:
        return list(
            self._session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == chat_session_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
        )

    def messages(self, chat_session_id: str) -> list[ChatMessage]:
        rows = self.all_messages(chat_session_id)
        if not rows:
            return []
        by_id = {row.id: row for row in rows}
        children: dict[str | None, list[ChatMessage]] = {}
        for row in rows:
            children.setdefault(row.parent_id, []).append(row)
        chat_session = self._session.get(ChatSession, chat_session_id)
        current: ChatMessage | None = None
        if (
            chat_session is not None
            and chat_session.active_root_id is not None
            and chat_session.active_root_id in by_id
            and by_id[chat_session.active_root_id].parent_id is None
        ):
            current = by_id[chat_session.active_root_id]
        elif children.get(None):
            current = max(children[None], key=lambda row: (row.created_at, row.id))
        path: list[ChatMessage] = []
        while current is not None:
            path.append(current)
            nxt: ChatMessage | None = None
            if current.active_child_id is not None and current.active_child_id in by_id:
                nxt = by_id[current.active_child_id]
            else:
                siblings = [row for row in rows if row.parent_id == current.id]
                if siblings:
                    nxt = max(siblings, key=lambda row: (row.created_at, row.id))
            current = nxt
        return path

    def child_index(self, chat_session_id: str) -> dict[str | None, list[str]]:
        groups: dict[str | None, list[str]] = {}
        for row in self.all_messages(chat_session_id):
            groups.setdefault(row.parent_id, []).append(row.id)
        return groups

    def active_tip(self, chat_session_id: str) -> str | None:
        path = self.messages(chat_session_id)
        return path[-1].id if path else None

    def add_message(
        self,
        chat_session_id: str,
        role: str,
        markdown: str,
        citations: list[dict[str, Any]] | None = None,
        grounded: bool | None = None,
        mentions: list[dict[str, Any]] | None = None,
        reads: list[dict[str, Any]] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        blocks: list[dict[str, Any]] | None = None,
        trace: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        parent_id: str | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=chat_session_id,
            role=role,
            blocks=blocks if blocks is not None else [{"type": "text", "md": markdown}],
            citations=citations,
            mentions=mentions,
            reads=reads,
            tool_calls=tool_calls,
            grounded=grounded,
            trace=trace,
            warnings=warnings,
            parent_id=parent_id,
        )
        self._session.add(message)
        self._session.flush()
        return message

    def branch_message(self, source: ChatMessage, markdown: str) -> ChatMessage:
        branched = ChatMessage(
            session_id=source.session_id,
            role=source.role,
            blocks=[{"type": "text", "md": markdown}],
            mentions=source.mentions,
            parent_id=source.parent_id,
        )
        self._session.add(branched)
        self._session.flush()
        if source.parent_id is None:
            chat_session = self._session.get(ChatSession, source.session_id)
            if chat_session is not None:
                chat_session.active_root_id = branched.id
        else:
            parent = self._session.get(ChatMessage, source.parent_id)
            if parent is not None:
                parent.active_child_id = branched.id
        return branched

    def select_message(self, target: ChatMessage) -> None:
        if target.parent_id is None:
            chat_session = self._session.get(ChatSession, target.session_id)
            if chat_session is not None:
                chat_session.active_root_id = target.id
            return
        parent = self._session.get(ChatMessage, target.parent_id)
        if parent is not None:
            parent.active_child_id = target.id

    def chain_under_later_reply(self, pending: ChatMessage) -> None:
        if pending.parent_id is None:
            return
        parent = self._session.get(ChatMessage, pending.parent_id)
        if parent is None or parent.active_child_id is None:
            return
        active = self._session.get(ChatMessage, parent.active_child_id)
        if (
            active is not None
            and active.role == "assistant"
            and active.created_at > pending.created_at
        ):
            pending.parent_id = active.id

    def _read_widget_state(self, chat_session: ChatSession, widget_id: str) -> str:
        target = widget_id.strip()
        for message in reversed(self.messages(chat_session.id)):
            if message.role != "assistant" or not message.state:
                continue
            if target in message.state:
                return json.dumps(message.state[target], ensure_ascii=False, default=str)
        return f"error: widget {target!r} has no state recorded in this conversation"

    def _log_interaction(
        self,
        chat_session_id: str,
        model: str | None,
        prompt: str,
        output: str,
        latency_ms: int,
        skill_version_id: str | None = None,
    ) -> None:
        accounting = embedding_accounting(self._session)
        input_tokens = _count_tokens(prompt, accounting)
        output_tokens = _count_tokens(output, accounting)
        self._session.add(
            AiInteraction(
                context_type="chat",
                context_id=chat_session_id,
                direction="rag answer",
                model=model,
                skill_version_id=skill_version_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=None,
                latency_ms=latency_ms,
                metadata_json=accounting.metadata(),
            )
        )

    def _dismissal_count(self, chat_session: ChatSession) -> int:
        dismissed = self._session.query(ChatProposal).filter(
            ChatProposal.status == ChatProposalStatus.DISMISSED.value,
            ChatProposal.message_id.in_(
                select(ChatMessage.id).where(ChatMessage.session_id == chat_session.id)
            ),
        )
        return dismissed.count()

    #: Feedback block caps: at most this many outcome rows and tracked ids.
    PROPOSAL_FEEDBACK_CAP = 10
    PROPOSAL_FEEDBACK_TRACK_CAP = 100

    def _proposal_feedback(self, chat_session: ChatSession) -> str | None:
        """Structured outcome block for cards resolved since the model's
        last turn (plan 78-D): the model must learn what happened to its
        proposals and not re-propose the same change unprompted."""
        context = cast(ChatSessionContext, dict(chat_session.context or {}))
        reported: list[str] = [
            str(value)
            for value in (context.get("proposal_feedback_ids") or [])
            if isinstance(value, str)
        ]
        rows = (
            self._session.execute(
                select(ChatProposal)
                .join(ChatMessage, ChatProposal.message_id == ChatMessage.id)
                .where(
                    ChatMessage.session_id == chat_session.id,
                    ChatProposal.status != ChatProposalStatus.PROPOSED.value,
                )
                .order_by(ChatProposal.created_at.desc(), ChatProposal.id.desc())
                .limit(self.PROPOSAL_FEEDBACK_TRACK_CAP)
            )
            .scalars()
            .all()
        )
        fresh = [row for row in rows if row.id not in reported][: self.PROPOSAL_FEEDBACK_CAP]
        if not fresh:
            return None
        lines = []
        for row in fresh:
            target = str(row.target_name or "").strip()
            label = f"{row.action} → {row.status}"
            if target:
                label = f"{label} ({target})"
            lines.append(label)
            reported.append(row.id)
        context["proposal_feedback_ids"] = reported[-self.PROPOSAL_FEEDBACK_TRACK_CAP :]
        chat_session.context = context
        self._session.flush()
        return (
            "PROPOSAL OUTCOMES — cards you proposed earlier were resolved:\n"
            + "\n".join(f"- {line}" for line in lines)
            + "\nDo not re-propose the same change unprompted."
        )

    def _build_messages(
        self,
        history: list[ChatMessage],
        user_message: ChatMessage,
        sources_block: str,
        tool_log: str,
        feedback: str | None,
        system_base: str,
        guard_rule_text: str | None = None,
        proposals_enabled: bool = False,
        dismissal_note: bool = False,
        native_tools: bool = False,
        chat_session: ChatSession | None = None,
        proposal_feedback: str | None = None,
    ) -> list[Message]:
        if native_tools:
            system = f"{system_base}\n\n{CHAT_WIDGET_DOC}"
            if chat_session is not None and chat_session.quizme:
                system = f"{system}\n\n{QUIZ_TOOL_DOC}"
        else:
            resource_doc = build_resource_tool_doc()
            system = f"{system_base}\n\n{CHAT_TOOL_DOC}\n\n{CHAT_WIDGET_DOC}\n\n{resource_doc}"
        if chat_session is not None and chat_session.quizme:
            system = f"{system}\n\n{QUIZME_SYSTEM}"
            pending = pending_state(chat_session.quiz_pending_row)
            if isinstance(pending, dict):
                if pending.get("verdict") is not None:
                    system = (
                        f"{system}\n\nQUIZ RESULT (server-graded; the expected "
                        f"answer is withheld from you): the student answered "
                        f"{pending.get('student_answer')!r} — verdict: "
                        f"{pending.get('verdict')} ({pending.get('verdict_detail')}). "
                        "Respond to their answer, then continue quiz-me."
                    )
                elif pending.get("verdict") is None and pending.get("awaiting_answer"):
                    system = (
                        f"{system}\n\nA quiz question is pending — the student has "
                        "not answered yet. Do not ask another question."
                    )
        if proposals_enabled:
            system = f"{system}\n\n{PROPOSAL_DOC}"
            if proposal_feedback:
                system = f"{system}\n\n{proposal_feedback}"
            if dismissal_note:
                system = f"{system}\n\n{DISMISSAL_NOTE}"
        if guard_rule_text is not None:
            system = f"{system}\n\n{guard_rule_text}"
        messages = [Message(role="system", content=system)]
        if feedback:
            messages.append(
                Message(
                    role="system",
                    content=f"Your previous answer violated the rules: {feedback}. "
                    "Rewrite it obeying every rule.",
                )
            )
        if tool_log:
            messages.append(Message(role="system", content=f"Verified tool results:\n{tool_log}"))
        for entry in history:
            if entry.state and entry.state.get("turn_failed"):
                # Failed-turn markers are display-only — never feed the
                # error placeholder into the model context.
                continue
            messages.append(
                Message(
                    role="assistant" if entry.role == "assistant" else "user",
                    content=_blocks_to_md(entry.blocks),
                )
            )
        current = f"Question: {user_message.blocks[0]['md']}"
        attached = [f"[{entry['ref']}] {entry['title']}" for entry in (user_message.mentions or [])]
        if attached:
            current += (
                "\n\nThe student attached these items to the message "
                f"(handles from the referenceable-items manifest): {', '.join(attached)}."
            )
        current = f"{current}\n\n{sources_block}".strip()
        messages.append(Message(role="user", content=current))
        return messages

    def native_tools_enabled(self, course_id: str | None = None) -> bool:
        try:
            from ....ai.chat_models import use_native_tools

            return use_native_tools(self._gateway.resolve(CHAT_TASK, course_id))
        except Exception:
            return False

    def prepare_turn_context(
        self, chat_session: ChatSession, user_message: ChatMessage
    ) -> TurnPrep:
        path = self.messages(chat_session.id)
        target_index = next(
            (index for index, row in enumerate(path) if row.id == user_message.id),
            None,
        )
        if target_index is None:
            raise ValueError("target message is not on the session's active path")
        history = list(path[:target_index])[-HISTORY_TURNS:]
        chunks, manifest_materials, turn_warning = self._turn_context(
            chat_session, user_message.blocks[0]["md"]
        )
        sources_block = ""
        if chunks:
            lines = []
            for index, chunk in enumerate(chunks, start=1):
                excerpt = chunk["text"][:1200]
                lines.append(f"[{index}] ({chunk['title']}) {excerpt}")
            sources_block = "Sources from the user's material:\n" + "\n\n".join(lines)
        notes = self._latest_notes(chat_session)
        notes_block = self._latest_notes_block(chat_session)
        if notes_block:
            sources_block = f"{sources_block}\n\n{notes_block}".strip()
        registry = self._turn_registry(chat_session, manifest_materials, notes)
        structure_block = self._structure_block(chat_session, registry)
        registry_block = registry.prompt_section()
        sources_parts = [part for part in (structure_block, registry_block) if part]
        sources_parts.append(sources_block)
        sources_block = "\n\n".join(part for part in sources_parts if part)

        exercise_binding = self._exercise_binding(chat_session)
        if exercise_binding is not None:
            exercise_session, exercise_step = exercise_binding
            pending = (chat_session.context or {}).get("pending_answer")
            exercise_block = self._exercise_context_block(exercise_session, exercise_step, pending)
            sources_block = f"{sources_block}\n\n{exercise_block}".strip()

        guard = self._quiz_guard(chat_session)
        exercise_guard = (
            self._exercise_guard(exercise_session, exercise_step)
            if exercise_binding is not None
            else None
        )
        guard_rule_text: str | None = None
        if guard is not None or exercise_guard is not None:
            guard_rule_text = QUIZ_GUARD_RULE if guard is not None else EXERCISE_GUARD_RULE
        proposals_enabled = chat_session.course_id is not None
        dismissal_note = proposals_enabled and self._dismissal_count(chat_session) >= 2
        proposal_feedback = self._proposal_feedback(chat_session) if proposals_enabled else None
        context: dict[str, Any] = {
            "chunks": chunks,
            "mention_refs": registry.refs(),
            "proposals_enabled": proposals_enabled,
        }
        if chat_session.course_id is not None:
            context["course_node_ids"] = set(
                self._session.scalars(
                    select(TreeNode.id).where(TreeNode.course_id == chat_session.course_id)
                )
            )
        if guard is not None:
            context.update(guard)
        if exercise_guard is not None:
            context.update(exercise_guard)
        return TurnPrep(
            history=history,
            chunks=chunks,
            sources_block=sources_block,
            registry=registry,
            guard_rule_text=guard_rule_text,
            proposals_enabled=proposals_enabled,
            dismissal_note=dismissal_note,
            proposal_feedback=proposal_feedback,
            context=context,
            question=user_message.blocks[0]["md"],
            turn_warning=turn_warning,
        )

    def prepare_turn_contract(self, chat_session: ChatSession, prep: TurnPrep) -> None:
        skill_version_id: str | None = None
        skills = SkillService(self._session)
        version = skills.resolve(CHAT_SKILL, course_id=chat_session.course_id)
        if version is not None:
            system_base, _user = skills.render(version, {"user_question": prep.question})
            contract = skills.constraints(version, {})
            skill_version_id = version.id
        else:
            system_base = CHAT_ANSWER_SYSTEM
            contract = list(CHAT_ANSWER_CONTRACT)
        if prep.guard_rule_text is not None:
            contract.append(Constraint("no_answer_reveal"))
        prep.system_base = system_base
        prep.contract = contract
        prep.skill_version_id = skill_version_id
        self._session.commit()

    def finalize_turn(
        self,
        chat_session: ChatSession,
        user_message: ChatMessage,
        prep: TurnPrep,
        *,
        started: float,
        run_id: str,
        model_name: str | None,
        prompt_snapshot: str,
        final_output: str,
        final_tool_calls: list[dict[str, Any]],
        reads: list[dict[str, Any]],
        grounded_refs: list[str] | None = None,
        repair_rounds: int,
        trace_rounds: list[dict[str, Any]],
        reasoning_parts: list[str],
        stream_interruption: str | None,
        validation: ValidationResult | None,
        emit: Emitter,
    ) -> ChatMessage:
        chunks = prep.chunks
        registry = prep.registry
        proposals_enabled = prep.proposals_enabled
        finalize_started = time.monotonic()
        if validation is not None and validation.advisories:
            logger.info(
                "mentions_advisory",
                session_id=chat_session.id,
                violations=[v.detail for v in validation.advisories],
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        accounting = embedding_accounting(self._session)
        trace: dict[str, Any] = {
            "run_id": run_id,
            "model": model_name,
            "latency_ms": latency_ms,
            "input_tokens": _count_tokens(prompt_snapshot, accounting),
            "output_tokens": _count_tokens(final_output, accounting),
            "token_accounting": accounting.metadata(),
            "repair_rounds": repair_rounds,
            "rounds": trace_rounds,
        }
        if reasoning_parts:
            trace["thinking"] = "".join(reasoning_parts)
        if stream_interruption is not None:
            trace["interruption"] = stream_interruption
            emit(
                flow_interrupted_event(
                    "user" if stream_interruption == STOP_MESSAGE else "server",
                    partial=bool(final_output.strip()),
                )
            )
        self._log_interaction(
            chat_session.id,
            model_name,
            prompt_snapshot,
            final_output,
            latency_ms,
            skill_version_id=prep.skill_version_id,
        )

        citations = _extract_citations(final_output, chunks)
        grounded = bool(citations) if chunks else None
        proposals, proposal_drops = (
            extract_proposals_with_drops(final_output) if proposals_enabled else ([], [])
        )
        if proposals_enabled and proposals:
            proposals, ungrounded = filter_ungrounded(proposals, grounded_refs or [])
            proposal_drops.extend(ungrounded)
        if proposals or "```proposal" in final_output:
            final_output = strip_proposal_fences(final_output)
        used_mentions = registry.parse(final_output)
        prepared_proposals: list[tuple[str, dict[str, Any]]] = []
        for action, payload in proposals[:MAX_PROPOSALS_PER_TURN]:
            stored_payload = dict(payload)
            original_md = capture_proposal_snapshot(
                self._session,
                action=action,
                payload=stored_payload,
                course_id=chat_session.course_id or "",
            )
            if original_md is not None:
                stored_payload["original_md"] = original_md
            if stored_payload.get("text_edits"):
                base = stored_payload.get("original_md")
                drop: str | None = None
                if not base:
                    drop = "anchor_mismatch"
                else:
                    try:
                        resolved = resolve_text_edits(
                            str(base),
                            [TextEditOp.model_validate(op) for op in stored_payload["text_edits"]],
                        )
                    except ProposalError as error:
                        drop = drop_code(str(error))
                    else:
                        body_field = "new_body_md" if action == "edit_note" else "new_markdown"
                        stored_payload[body_field] = resolved
                if drop is not None:
                    proposal_drops.append(drop)
                    continue
            prepared_proposals.append((action, stored_payload))
        turn_warnings = [prep.turn_warning] if prep.turn_warning is not None else []
        if proposal_drops:
            counts = Counter(proposal_drops)
            summary = ", ".join(f"{code}: {count}" for code, count in sorted(counts.items()))
            turn_warnings.append(
                f"{sum(counts.values())} suggested action(s) dropped "
                f"({summary}) — ask again to retry them."
            )
            trace["proposals_dropped"] = proposal_drops
        message = self.add_message(
            chat_session.id,
            "assistant",
            final_output,
            citations=citations,
            grounded=grounded,
            mentions=[entry.as_dict() for entry in used_mentions],
            reads=reads or None,
            tool_calls=final_tool_calls or None,
            blocks=parse_answer_blocks(final_output),
            trace=trace,
            warnings=turn_warnings or None,
        )
        message.parent_id = user_message.id
        user_message.active_child_id = message.id
        self._session.flush()
        for action, stored_payload in prepared_proposals:
            target = resolve_proposal_target(
                self._session,
                action=action,
                payload=stored_payload,
                course_id=chat_session.course_id or "",
            )
            proposal = ChatProposal(
                message_id=message.id,
                action=action,
                status="proposed",
            )
            store_proposal_state(
                proposal,
                payload=stored_payload,
                original_md=original_md,
                target=target,
            )
            self._session.add(proposal)
        self._session.flush()
        self._session.commit()
        logger.info(
            "chat_turn_timing",
            session_id=chat_session.id,
            phase="finalize",
            duration_ms=int((time.monotonic() - finalize_started) * 1000),
        )
        emit(
            flow_finished_event(
                run_id,
                message.id,
                model=model_name,
                total_ms=latency_ms,
                tool_count=len(final_tool_calls),
            )
        )
        return message


def proposal_out(proposal: ChatProposal | None) -> dict[str, Any]:
    if proposal is None:
        return {}
    return {
        "id": proposal.id,
        "action": proposal.action,
        "payload": proposal_full_payload(proposal),
        "status": proposal.status,
        "result": proposal.result,
    }


def _extract_citations(output: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cited: list[dict[str, Any]] = []
    seen: set[int] = set()
    for match in CITATION_RE.finditer(output):
        index = int(match.group(1))
        if not 1 <= index <= len(chunks):
            continue
        if index in seen:
            continue
        seen.add(index)
        chunk = chunks[index - 1]
        cited.append(
            {
                "index": index,
                "chunk_id": chunk["chunk_id"],
                "material_id": chunk["material_id"],
                "title": chunk["title"],
                "quote": chunk["text"][:280],
            }
        )
    return cited
