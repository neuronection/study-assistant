import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...ai.contracts.contracts import (
    CHAT_ANSWER_CONTRACT,
    CITATION_RE,
    Constraint,
    ValidationResult,
    validate,
)
from ...ai.gateway import LLMGateway, Message, ProviderError, is_tool_unsupported_error
from ...ai.mentions import MentionRegistry, registry_from_json
from ...ai.parsing import blocks_to_md as _blocks_to_md
from ...ai.parsing import parse_answer_blocks
from ...ai.proposals import (
    DISMISSAL_NOTE,
    PROPOSAL_DOC,
    extract_proposal,
    strip_proposal_fences,
)
from ...ai.skills import CHAT_ANSWER_SYSTEM
from ...ai.tools import (
    CHAT_TOOL_DOC,
    TOOL_LINE_RE,
    extract_tool_calls,
    run_tool_line,
    strip_tool_lines,
)
from ...ai.widgets import CHAT_WIDGET_DOC
from ...domain.models import (
    Activity,
    AiInteraction,
    Answer,
    Attempt,
    ChatMessage,
    ChatProposal,
    ChatSession,
    Concept,
    Course,
    Exercise,
    ExerciseSession,
    ExerciseStep,
    Extraction,
    Material,
    MaterialIndexCard,
    Note,
    Profile,
    Question,
    StepAttempt,
    TreeNode,
)
from ...mcp_resources import (
    RESOURCE_TOOL_BY_KEYWORD,
    ResourceError,
    build_resource_tool_doc,
)
from ..knowledge.context import ContextResolver, ContextScope, ContextSpec
from ..search import retrieve_chunks_hybrid
from ..study.tutor import quiz_guard_context
from .skills import SkillService

logger = structlog.get_logger(__name__)

CHAT_TASK = "chat"
CHAT_SKILL = "chat.answer"
MAX_REPAIR_ROUNDS = 1
MAX_TOOL_ROUNDS = 2
MAX_READ_ROUNDS = 3
MAX_STATE_ROUNDS = 3
MAX_RESOURCE_ROUNDS = 5
READ_CHARS = 4000
HISTORY_TURNS = 8
RETRIEVE_LIMIT = 6
REGISTRY_MATERIALS_CAP = 30
STREAM_DELTA_INTERVAL = 0.03

QUIZ_GUARD_RULE = (
    "SPECIAL RULE: the student has an OPEN attempt on a quiz question discussed in "
    "this conversation. Do NOT reveal, state, or mathematically give away its correct "
    "answer, and do NOT single out the correct option. Guide with questions, concepts, "
    "and partial strategies instead."
)

EXERCISE_GUARD_RULE = (
    "SPECIAL RULE: the student is working on the exercise step shown in the context "
    "and has not solved it yet. Do NOT reveal, state, or mathematically give away "
    "its expected answer. Coach the current attempt: point out issues you can see, "
    "ask guiding questions, and suggest strategies instead."
)

Emitter = Callable[[dict[str, Any]], None]


@dataclass
class TurnPrep:
    """Everything a chat turn needs before the first model call.

    Built once per turn by `ChatService.prepare_turn_context` +
    `prepare_turn_contract` and consumed by both the legacy `answer_streaming`
    loop and the LangGraph chat-turn engine, so context assembly, contract
    selection, and persistence cannot drift between engines.
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
    skill_version_id: int | None = None
    turn_warning: str | None = None


class ChatError(ValueError):
    pass


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def flatten_prompt(messages: list[Message]) -> str:
    return "\n".join(
        f"{message.role}: {message.content}" for message in messages
    )


def _native_call_args(name: str, arguments: dict[str, Any]) -> str:
    if name == "SYMPY":
        return f"{arguments.get('action', '')} {arguments.get('expression', '')}".strip()
    if name in ("CALC", "PLOT"):
        return str(arguments.get("expression", ""))
    if name == "READ":
        return str(arguments.get("handle", ""))
    if name == "STATE":
        return str(arguments.get("widget_id", ""))
    if name in RESOURCE_TOOL_BY_KEYWORD:
        return str(arguments.get("node", ""))
    return json.dumps(arguments, ensure_ascii=False)


def _quiz_answer_text(question: Question) -> str:
    answer = question.answer or {}
    if "index" in answer and question.options:
        try:
            return chr(ord("A") + int(answer["index"]))
        except (TypeError, ValueError):
            pass
    if "indices" in answer and question.options:
        try:
            return ", ".join(
                chr(ord("A") + int(item)) for item in answer["indices"]
            )
        except (TypeError, ValueError):
            pass
    value = answer.get("value")
    return str(value) if value is not None else str(answer)


def _tool_result_summary(kind: str, raw: str) -> str | None:
    if kind == "READ":
        return f"read {len(raw)} chars"
    if kind == "PLOT":
        return "chart data"
    if kind == "STATE":
        return None
    return raw[:500]


class ChatService:
    def __init__(self, session: Session, gateway: LLMGateway, embedder: Any) -> None:
        self._session = session
        self._gateway = gateway
        self._embedder = embedder

    def create_session(
        self,
        profile_id: int,
        course_id: int | None = None,
        node_id: int | None = None,
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

    def list_sessions(
        self, profile_id: int, node_id: int | None = None
    ) -> list[ChatSession]:
        statement = select(ChatSession).where(ChatSession.profile_id == profile_id)
        if node_id is not None:
            statement = statement.where(ChatSession.node_id == node_id)
        return list(
            self._session.scalars(statement.order_by(ChatSession.id.desc()))
        )

    def get_session(self, session_id: int, profile_id: int) -> ChatSession | None:
        chat_session = self._session.get(ChatSession, session_id)
        if chat_session is None or chat_session.profile_id != profile_id:
            return None
        return chat_session

    def all_messages(self, chat_session_id: int) -> list[ChatMessage]:
        return list(
            self._session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == chat_session_id)
                .order_by(ChatMessage.id)
            )
        )

    def messages(self, chat_session_id: int) -> list[ChatMessage]:
        rows = self.all_messages(chat_session_id)
        if not rows:
            return []
        by_id = {row.id: row for row in rows}
        children: dict[int | None, list[ChatMessage]] = {}
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
            current = max(children[None], key=lambda row: row.id)
        path: list[ChatMessage] = []
        while current is not None:
            path.append(current)
            nxt: ChatMessage | None = None
            if (
                current.active_child_id is not None
                and current.active_child_id in by_id
            ):
                nxt = by_id[current.active_child_id]
            else:
                siblings = [row for row in rows if row.parent_id == current.id]
                if siblings:
                    nxt = max(siblings, key=lambda row: row.id)
            current = nxt
        return path

    def child_index(self, chat_session_id: int) -> dict[int | None, list[int]]:
        groups: dict[int | None, list[int]] = {}
        for row in self.all_messages(chat_session_id):
            groups.setdefault(row.parent_id, []).append(row.id)
        for ids in groups.values():
            ids.sort()
        return groups

    def active_tip(self, chat_session_id: int) -> int | None:
        path = self.messages(chat_session_id)
        return path[-1].id if path else None

    def add_message(
        self,
        chat_session_id: int,
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
        parent_id: int | None = None,
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

    def branch_message(
        self, source: ChatMessage, markdown: str
    ) -> ChatMessage:
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
            and active.id > pending.id
        ):
            pending.parent_id = active.id

    def _log_interaction(
        self,
        chat_session_id: int,
        model: str | None,
        prompt: str,
        output: str,
        latency_ms: int,
        skill_version_id: int | None = None,
    ) -> None:
        input_tokens = _estimate_tokens(prompt)
        output_tokens = _estimate_tokens(output)
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
            )
        )

    def _quiz_guard(self, chat_session: ChatSession) -> dict[str, Any] | None:
        binding = chat_session.context or {}
        attempt_id = binding.get("quiz_attempt_id")
        question_id = binding.get("question_id")
        if not attempt_id or not question_id:
            return None
        attempt = self._session.get(Attempt, int(attempt_id))
        if attempt is None or attempt.finished_at is not None:
            return None
        answered = (
            self._session.scalars(
                select(Answer.id).where(
                    Answer.attempt_id == attempt.id, Answer.question_id == int(question_id)
                )
            ).first()
            is not None
        )
        if answered:
            return None
        question = self._session.get(Question, int(question_id))
        if question is None:
            return None
        return quiz_guard_context(question)

    def _exercise_binding(
        self, chat_session: ChatSession
    ) -> tuple[ExerciseSession, ExerciseStep] | None:
        binding = chat_session.context or {}
        exercise_session_id = binding.get("exercise_session_id")
        if not exercise_session_id:
            return None
        exercise_session = self._session.get(ExerciseSession, int(exercise_session_id))
        if exercise_session is None or exercise_session.status != "active":
            return None
        step = self._session.scalars(
            select(ExerciseStep)
            .where(
                ExerciseStep.exercise_id == exercise_session.exercise_id,
                ExerciseStep.order_idx == exercise_session.current_step_idx,
            )
        ).first()
        if step is None:
            return None
        return exercise_session, step

    def _exercise_context_block(
        self, exercise_session: ExerciseSession, step: ExerciseStep, pending: str | None
    ) -> str:
        exercise = self._session.get(Exercise, exercise_session.exercise_id)
        total = (
            self._session.scalar(
                select(func.count(ExerciseStep.id)).where(
                    ExerciseStep.exercise_id == exercise_session.exercise_id
                )
            )
            or 0
        )
        attempts = list(
            self._session.scalars(
                select(StepAttempt)
                .where(
                    StepAttempt.session_id == exercise_session.id,
                    StepAttempt.step_idx == exercise_session.current_step_idx,
                )
                .order_by(StepAttempt.id)
            )
        )
        lines = [
            f"Exercise: {exercise.title if exercise is not None else 'exercise'} — "
            f"step {exercise_session.current_step_idx + 1} of {total}",
            f"Step prompt:\n{_blocks_to_md(step.prompt)}",
        ]
        if pending:
            shown = f"$${pending}$$" if not pending.startswith(("{", "[")) else pending
            lines.append(f"The student's current (not yet submitted) answer:\n{shown}")
        if attempts:
            last = attempts[-1]
            outcome = "correct" if last.correct else (
                f"not yet correct ({last.error_class or 'no diagnosis'})"
            )
            lines.append(
                f"Submitted attempts on this step: {len(attempts)} (latest: {outcome})"
            )
        else:
            lines.append("Submitted attempts on this step: none yet")
        return "The student is working on this exercise step (extra context):\n" + "\n".join(
            lines
        )

    def _exercise_guard(
        self, exercise_session: ExerciseSession, step: ExerciseStep
    ) -> dict[str, Any] | None:
        solved = (
            self._session.scalars(
                select(StepAttempt.id).where(
                    StepAttempt.session_id == exercise_session.id,
                    StepAttempt.step_idx == exercise_session.current_step_idx,
                    StepAttempt.correct.is_(True),
                )
            ).first()
            is not None
        )
        if solved:
            return None
        expected_spec = step.expected or {}
        value = expected_spec.get("value")
        guard: dict[str, Any] = {"expected": None, "expected_candidates": [], "forbidden_texts": []}
        if expected_spec.get("kind") == "math" and value not in (None, ""):
            guard["expected"] = str(value)
        elif value not in (None, ""):
            text = str(value)
            if len(text) >= 2:
                guard["forbidden_texts"] = [text]
        return guard

    def _latest_notes(self, chat_session: ChatSession) -> list[Note]:
        return self.latest_notes_preview(chat_session)

    def latest_notes_preview(self, chat_session: ChatSession) -> list[Note]:
        statement = (
            select(Note)
            .where(Note.profile_id == chat_session.profile_id)
            .order_by(Note.pinned.desc(), Note.updated_at.desc())
            .limit(3)
        )
        if chat_session.course_id is not None:
            statement = (
                select(Note)
                .where(
                    Note.profile_id == chat_session.profile_id,
                    Note.course_id == chat_session.course_id,
                )
                .order_by(Note.pinned.desc(), Note.updated_at.desc())
                .limit(3)
            )
        return list(self._session.scalars(statement))

    def _latest_notes_block(self, chat_session: ChatSession) -> str:
        notes = self._latest_notes(chat_session)
        if not notes:
            return ""
        lines = []
        for note in notes:
            body = "\n".join(
                str(block.get("md", ""))
                for block in note.body
                if block.get("md")
            )
            drawings = "\n".join(
                drawing.ocr_markdown for drawing in note.drawings if drawing.ocr_markdown
            )
            excerpt = "\n".join(part for part in (body, drawings) if part)[:1500]
            lines.append(f"### {note.title}\n{excerpt}")
        return (
            "The student's latest notes (extra context — do NOT cite these with [n] "
            "numbers; cite only the numbered sources above):\n\n" + "\n\n".join(lines)
        )

    def _turn_context(
        self, chat_session: ChatSession, query: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
        use_embeddings = self._effective_use_embeddings(chat_session)
        warnings: list[str] = []

        def on_embedding_warning(reason: str) -> None:
            warnings.append(
                f"Semantic search is on, but {reason} — using keyword search for "
                "this answer."
            )

        if chat_session.course_id is not None:
            spec = ContextSpec(
                course_id=chat_session.course_id,
                node_id=chat_session.node_id,
                scope=ContextScope.subtree,
                query=query,
                max_chunks=RETRIEVE_LIMIT,
            )
            bundle = ContextResolver(
                self._session, self._embedder.embed
            ).resolve(
                spec,
                use_embeddings=use_embeddings,
                embedding_warning=on_embedding_warning,
            )
            return (
                bundle.chunks,
                bundle.materials[:REGISTRY_MATERIALS_CAP],
                warnings[0] if warnings else None,
            )
        chunks = retrieve_chunks_hybrid(
            self._session,
            query,
            self._embedder.embed,
            course_id=None,
            material_ids=None,
            limit=RETRIEVE_LIMIT,
            use_embeddings=use_embeddings,
            embedding_warning=on_embedding_warning,
        )
        return chunks, [], warnings[0] if warnings else None

    def _effective_use_embeddings(self, chat_session: ChatSession) -> bool:
        if chat_session.use_embeddings is not None:
            return chat_session.use_embeddings
        profile = self._session.get(Profile, chat_session.profile_id)
        prefs = profile.preferences if profile is not None else None
        return bool((prefs or {}).get("use_embeddings", True))

    def _turn_registry(
        self,
        chat_session: ChatSession,
        materials: list[dict[str, Any]],
        notes: list[Note],
    ) -> MentionRegistry:
        registry = registry_from_json(chat_session.mention_registry)
        if chat_session.node_id is not None:
            node = self._session.get(TreeNode, chat_session.node_id)
            if node is not None and not node.is_root:
                registry.add("node", node.id, node.title, node.course_id)
        for entry in materials:
            registry.add(
                "material",
                int(entry["id"]),
                str(entry["title"]),
                chat_session.course_id,
                str(entry["summary"]) if entry.get("summary") else None,
            )
        for note in notes:
            registry.add("note", note.id, note.title, note.course_id)
        chat_session.mention_registry = registry.to_json()
        self._session.flush()
        return registry

    def _root_node(self, course_id: int) -> TreeNode | None:
        return self._session.scalars(
            select(TreeNode).where(
                TreeNode.course_id == course_id, TreeNode.is_root.is_(True)
            )
        ).first()

    def attach(
        self,
        chat_session: ChatSession,
        attachments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        registry = registry_from_json(chat_session.mention_registry)
        stored: list[dict[str, Any]] = []
        for attachment in attachments:
            kind = str(attachment.get("kind"))
            item_id = int(attachment.get("id", 0))
            if kind == "material":
                material = self._session.get(Material, item_id)
                if material is None:
                    raise ChatError(f"material {item_id} not found")
                card = self._session.get(MaterialIndexCard, item_id)
                entry = registry.add(
                    "material",
                    material.id,
                    material.title,
                    material.course_id,
                    card.summary if card is not None else None,
                )
            elif kind == "note":
                note = self._session.get(Note, item_id)
                if note is None:
                    raise ChatError(f"note {item_id} not found")
                excerpt = note.search_text.strip().replace("\n", " ")[:200]
                entry = registry.add(
                    "note",
                    note.id,
                    note.title,
                    note.course_id,
                    excerpt or None,
                )
            elif kind == "quiz":
                activity = self._session.get(Activity, item_id)
                if activity is None or activity.type != "quiz":
                    raise ChatError(f"quiz {item_id} not found")
                entry = registry.add(
                    "quiz",
                    activity.id,
                    activity.title,
                    activity.course_id,
                    f"quiz with {len(activity.questions)} questions",
                )
            elif kind == "exercise":
                exercise = self._session.get(Exercise, item_id)
                if exercise is None or exercise.kind.startswith("card_"):
                    raise ChatError(f"exercise {item_id} not found")
                entry = registry.add(
                    "exercise",
                    exercise.id,
                    exercise.title,
                    exercise.course_id,
                    f"{exercise.kind} exercise with {len(exercise.steps)} steps",
                )
            elif kind == "node":
                node = self._session.get(TreeNode, item_id)
                if node is None:
                    raise ChatError(f"node {item_id} not found")
                entry = registry.add(
                    "node", node.id, node.title, node.course_id, node.summary
                )
            elif kind == "course":
                course = self._session.get(Course, item_id)
                if course is None:
                    raise ChatError(f"course {item_id} not found")
                root = self._root_node(course.id)
                if root is None:
                    raise ChatError(f"course {item_id} not found")
                entry = registry.add(
                    "node", root.id, course.title, course.id, course.description
                )
            else:
                raise ChatError(f"unknown attachment kind: {kind}")
            stored.append(entry.as_dict())
        if stored:
            chat_session.mention_registry = registry.to_json()
            self._session.flush()
        return stored

    def _dismissal_count(self, chat_session: ChatSession) -> int:
        dismissed = self._session.query(ChatProposal).filter(
            ChatProposal.status == "dismissed",
            ChatProposal.message_id.in_(
                select(ChatMessage.id).where(
                    ChatMessage.session_id == chat_session.id
                )
            ),
        )
        return dismissed.count()

    def _read_handle(self, handle: str, registry: MentionRegistry) -> str:
        entry = registry.get(handle.strip())
        if entry is None:
            return (
                f"error: {handle.strip()} is not offered in this conversation — "
                "pick a handle from the referenceable-items manifest"
            )
        if entry.kind == "material":
            extraction = self._session.scalars(
                select(Extraction)
                .where(Extraction.material_id == entry.id)
                .order_by(Extraction.version.desc())
            ).first()
            if extraction is None or not extraction.markdown.strip():
                material = self._session.get(Material, entry.id)
                if material is not None and material.status != "ready":
                    return (
                        f"note: material {entry.ref} is still being processed "
                        f"(status: {material.status}) — tell the student it is not "
                        "readable yet and to ask again in a moment"
                    )
                return f"error: material {entry.ref} has no extracted content yet"
            return extraction.markdown[:READ_CHARS]
        if entry.kind == "note":
            note = self._session.get(Note, entry.id)
            if note is None:
                return f"error: note {entry.ref} no longer exists"
            parts = [
                str(block.get("md", ""))
                for block in note.body
                if block.get("md")
            ] + [d.ocr_markdown for d in note.drawings if d.ocr_markdown]
            return "\n".join(parts)[:READ_CHARS]
        if entry.kind == "concept":
            concept = self._session.get(Concept, entry.id)
            if concept is None:
                return f"error: concept {entry.ref} no longer exists"
            text = f"{concept.name}: {concept.description or ''}"
            return text[:READ_CHARS]
        if entry.kind == "node":
            node = self._session.get(TreeNode, entry.id)
            if node is None:
                return f"error: node {entry.ref} no longer exists"
            lines = [f"{node.title}"]
            if node.summary:
                lines.append(node.summary.strip())
            for objective in node.objectives or []:
                lines.append(f"- {objective}")
            return "\n".join(lines)[:READ_CHARS]
        if entry.kind == "quiz":
            activity = self._session.get(Activity, entry.id)
            if activity is None:
                return f"error: quiz {entry.ref} no longer exists"
            questions = list(activity.questions)
            lines = [f"{activity.title} — quiz with {len(questions)} questions"]
            for index, question in enumerate(questions, start=1):
                lines.append(f"Q{index} ({question.type}): {_blocks_to_md(question.stem)}")
                for option_index, block in enumerate(question.options or []):
                    letter = chr(ord("A") + option_index)
                    md = block.get("md") or block.get("latex") or ""
                    lines.append(f"   {letter}) {md}")
                lines.append(f"   answer: {_quiz_answer_text(question)}")
            return "\n".join(lines)[:READ_CHARS]
        if entry.kind == "exercise":
            exercise = self._session.get(Exercise, entry.id)
            if exercise is None:
                return f"error: exercise {entry.ref} no longer exists"
            lines = [
                f"{exercise.title} — {exercise.kind} exercise with "
                f"{len(exercise.steps)} steps"
            ]
            for index, step in enumerate(exercise.steps, start=1):
                lines.append(f"Step {index}: {_blocks_to_md(step.prompt)}")
                if step.expected is not None:
                    compact = json.dumps(step.expected, ensure_ascii=False, default=str)
                    lines.append(f"   expected: {compact}")
            return "\n".join(lines)[:READ_CHARS]
        return f"error: {entry.kind} items cannot be READ"

    def _read_widget_state(self, chat_session: ChatSession, widget_id: str) -> str:
        target = widget_id.strip()
        for message in reversed(self.messages(chat_session.id)):
            if message.role != "assistant" or not message.state:
                continue
            if target in message.state:
                return json.dumps(message.state[target], ensure_ascii=False, default=str)
        return f"error: widget {target!r} has no state recorded in this conversation"

    def _resolve_node_arg(
        self,
        argument: str,
        chat_session: ChatSession,
        registry: MentionRegistry,
    ) -> int | None:
        arg = (argument or "").strip()
        if arg in {"", "here", "current"}:
            return chat_session.node_id
        entry = registry.get(arg)
        if entry is not None and entry.kind == "node":
            return entry.id
        return None

    def _run_resource_tool(
        self,
        keyword: str,
        argument: str,
        chat_session: ChatSession,
        registry: MentionRegistry,
    ) -> str:
        spec = RESOURCE_TOOL_BY_KEYWORD.get(keyword)
        if spec is None:
            return f"error: unknown resource tool '{keyword}'"
        kwargs: dict[str, Any] = {}
        if spec["arg"] == "node":
            node_id = self._resolve_node_arg(argument, chat_session, registry)
            if node_id is None:
                return (
                    "error: need a node handle (T#) from the referenceable-items "
                    "manifest, or 'here' for the current node"
                )
            kwargs["node_id"] = node_id
        try:
            result = spec["call"](self._session, **kwargs)
        except ResourceError as error:
            return f"error: {error}"
        return json.dumps(result, ensure_ascii=False, default=str)[:2000]

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
    ) -> list[Message]:
        if native_tools:
            system = f"{system_base}\n\n{CHAT_WIDGET_DOC}"
        else:
            resource_doc = build_resource_tool_doc()
            system = (
                f"{system_base}\n\n{CHAT_TOOL_DOC}\n\n{CHAT_WIDGET_DOC}\n\n{resource_doc}"
            )
        if proposals_enabled:
            system = f"{system}\n\n{PROPOSAL_DOC}"
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
            messages.append(
                Message(role="system", content=f"Verified tool results:\n{tool_log}")
            )
        for entry in history:
            messages.append(
                Message(
                    role="assistant" if entry.role == "assistant" else "user",
                    content=_blocks_to_md(entry.blocks),
                )
            )
        current = f"Question: {user_message.blocks[0]['md']}"
        attached = [
            f"[{entry['ref']}] {entry['title']}"
            for entry in (user_message.mentions or [])
        ]
        if attached:
            current += (
                "\n\nThe student attached these items to the message "
                f"(handles from the referenceable-items manifest): {', '.join(attached)}."
            )
        current = f"{current}\n\n{sources_block}".strip()
        messages.append(Message(role="user", content=current))
        return messages

    def native_tools_enabled(self, course_id: int | None = None) -> bool:
        return self._use_native_tools(course_id)

    def _use_native_tools(self, course_id: int | None = None) -> bool:
        try:
            from ...ai.chat_models import use_native_tools

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
            raise ValueError(
                "target message is not on the session's active path"
            )
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
        registry_block = registry.prompt_section()
        if registry_block:
            sources_block = f"{registry_block}\n\n{sources_block}".strip()

        exercise_binding = self._exercise_binding(chat_session)
        if exercise_binding is not None:
            exercise_session, exercise_step = exercise_binding
            pending = (chat_session.context or {}).get("pending_answer")
            exercise_block = self._exercise_context_block(
                exercise_session, exercise_step, pending
            )
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
        context: dict[str, Any] = {
            "chunks": chunks,
            "mention_refs": registry.refs(),
            "proposals_enabled": proposals_enabled,
        }
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
            context=context,
            question=user_message.blocks[0]["md"],
            turn_warning=turn_warning,
        )

    def prepare_turn_contract(
        self, chat_session: ChatSession, prep: TurnPrep
    ) -> None:
        skill_version_id: int | None = None
        skills = SkillService(self._session)
        version = skills.resolve(CHAT_SKILL, course_id=chat_session.course_id)
        if version is not None:
            system_base, _user = skills.render(
                version, {"user_question": prep.question}
            )
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

    def answer_streaming(
        self,
        chat_session: ChatSession,
        user_message: ChatMessage,
        emit: Emitter,
        stop: threading.Event | None = None,
    ) -> ChatMessage:
        started = time.monotonic()
        prep = self.prepare_turn_context(chat_session, user_message)
        self.prepare_turn_contract(chat_session, prep)
        history = prep.history
        sources_block = prep.sources_block
        registry = prep.registry
        guard_rule_text = prep.guard_rule_text
        proposals_enabled = prep.proposals_enabled
        dismissal_note = prep.dismissal_note
        context = prep.context
        system_base = prep.system_base
        contract = prep.contract
        model_name: str | None = None
        prompt_snapshot = ""
        feedback_text = ""
        final_output = ""
        final_tool_calls: list[dict[str, Any]] = []
        run_id = uuid4().hex
        trace_rounds: list[dict[str, Any]] = []
        reasoning_parts: list[str] = []
        stream_interruption: str | None = None
        validation: ValidationResult | None = None

        def elapsed_ms() -> int:
            return int((time.monotonic() - started) * 1000)

        logger.info(
            "chat_turn_timing",
            session_id=chat_session.id,
            phase="context",
            duration_ms=elapsed_ms(),
        )

        def flush_deltas(text_buf: list[str], reason_buf: list[str]) -> float:
            if reason_buf:
                emit(
                    {
                        "type": "stream_delta",
                        "delta": "".join(reason_buf),
                        "kind": "reasoning",
                        "elapsed_ms": elapsed_ms(),
                    }
                )
                reason_buf.clear()
            if text_buf:
                emit(
                    {
                        "type": "stream_delta",
                        "delta": "".join(text_buf),
                        "elapsed_ms": elapsed_ms(),
                    }
                )
                text_buf.clear()
            return time.monotonic()

        for attempt in range(MAX_REPAIR_ROUNDS + 1):
            if stop is not None and stop.is_set():
                stream_interruption = "generation stopped by user"
                break
            tool_log = ""
            output = ""
            math_rounds = 0
            read_used = 0
            state_used = 0
            resource_used = 0
            reads: list[dict[str, Any]] = []
            tool_calls_seen: list[dict[str, Any]] = []
            native_tools = self._use_native_tools(chat_session.course_id)
            degraded_native = False
            native_round: list[Message] = []
            base_messages = self._build_messages(
                history,
                user_message,
                sources_block,
                "",
                feedback_text if attempt > 0 else None,
                system_base,
                guard_rule_text=guard_rule_text,
                proposals_enabled=proposals_enabled,
                dismissal_note=dismissal_note,
                native_tools=native_tools,
            )
            for _tool_round in range(MAX_TOOL_ROUNDS + MAX_READ_ROUNDS + 1):
                if stop is not None and stop.is_set():
                    stream_interruption = "generation stopped by user"
                    break
                round_start_ms = elapsed_ms()
                round_phase = "repairing" if attempt > 0 else "thinking"
                if _tool_round == 0:
                    emit(
                        {
                            "type": "stream_start",
                            "run_id": run_id,
                            "elapsed_ms": round_start_ms,
                        }
                    )
                emit(
                    {
                        "type": "phase",
                        "phase": round_phase,
                        "elapsed_ms": round_start_ms,
                    }
                )
                messages = (
                    [*base_messages, *native_round]
                    if native_tools
                    else self._build_messages(
                        history,
                        user_message,
                        sources_block,
                        tool_log,
                        feedback_text if attempt > 0 else None,
                        system_base,
                        guard_rule_text=guard_rule_text,
                        proposals_enabled=proposals_enabled,
                        dismissal_note=dismissal_note,
                    )
                )
                prompt_snapshot = flatten_prompt(messages)
                buffer: list[str] = []
                delta_buf: list[str] = []
                reasoning_buf: list[str] = []
                native_raw: list[dict[str, Any]] = []
                last_flush = time.monotonic()
                pending_line = ""
                try:
                    for part in self._gateway.stream_events(
                            CHAT_TASK, messages, course_id=chat_session.course_id
                        ):
                        if stop is not None and stop.is_set():
                            stream_interruption = "generation stopped by user"
                            break
                        if part.kind == "tool_call":
                            native_raw.append(json.loads(part.text))
                        elif part.kind == "reasoning":
                            reasoning_parts.append(part.text)
                            reasoning_buf.append(part.text)
                        else:
                            buffer.append(part.text)
                            pending_line += part.text
                            while "\n" in pending_line:
                                line, pending_line = pending_line.split("\n", 1)
                                if not TOOL_LINE_RE.match(line):
                                    delta_buf.append(line + "\n")
                        if time.monotonic() - last_flush >= STREAM_DELTA_INTERVAL:
                            last_flush = flush_deltas(delta_buf, reasoning_buf)
                except ProviderError as error:
                    if buffer:
                        stream_interruption = str(error)[:200]
                    elif native_tools and is_tool_unsupported_error(error):
                        from ...ai.chat_models import degrade_native_tools

                        degrade_native_tools(
                            self._gateway.resolve(
                                CHAT_TASK, chat_session.course_id
                            )
                        )
                        degraded_native = True
                        break
                    else:
                        raise
                if pending_line and not TOOL_LINE_RE.match(pending_line):
                    delta_buf.append(pending_line)
                flush_deltas(delta_buf, reasoning_buf)
                output = "".join(buffer)
                round_duration_ms = elapsed_ms() - round_start_ms
                logger.info(
                    "chat_turn_timing",
                    session_id=chat_session.id,
                    phase=round_phase,
                    duration_ms=round_duration_ms,
                )
                trace_rounds.append(
                    {
                        "index": len(trace_rounds),
                        "streamed": True,
                        "start_ms": round_start_ms,
                        "duration_ms": round_duration_ms,
                        "phase": round_phase,
                    }
                )
                try:
                    model_name = self._gateway.resolve(
                        CHAT_TASK, chat_session.course_id
                    ).label
                except Exception:
                    model_name = None
                if stream_interruption is not None:
                    break
                if native_tools:
                    tool_calls = [
                        (call["name"], _native_call_args(call["name"], call.get("arguments") or {}))
                        for call in native_raw
                    ]
                else:
                    tool_calls = extract_tool_calls(output)
                if not tool_calls:
                    break
                call_kinds = {kind for kind, _argument in tool_calls}
                readish = {"READ", "STATE", *RESOURCE_TOOL_BY_KEYWORD}
                if call_kinds and call_kinds <= readish:
                    phase = "read"
                elif call_kinds & readish:
                    phase = "mixed"
                else:
                    phase = "math"
                results = []
                executed_math = False
                for kind, argument in tool_calls:
                    tool_start_ms = elapsed_ms()
                    tool_phase = (
                        "reading"
                        if kind in readish
                        else "plotting"
                        if kind == "PLOT"
                        else "computing"
                    )
                    emit(
                        {
                            "type": "phase",
                            "phase": tool_phase,
                            "elapsed_ms": tool_start_ms,
                        }
                    )
                    if kind == "READ":
                        if read_used >= MAX_READ_ROUNDS:
                            results.append(
                                f"READ {argument} -> error: READ budget for this "
                                "turn is spent; answer from what you already have"
                            )
                            continue
                        read_used += 1
                        content = self._read_handle(argument, registry)
                        results.append(f"READ {argument} -> {content}")
                        entry = registry.get(argument)
                        if entry is not None and not (
                            content.startswith("error:")
                            or content.startswith("note:")
                        ):
                            reads.append(
                                {
                                    "ref": entry.ref,
                                    "kind": entry.kind,
                                    "id": entry.id,
                                    "title": entry.title,
                                    "course_id": entry.course_id,
                                    "chars": len(content),
                                }
                            )
                        tool_entry: dict[str, Any] = {
                            "name": "READ",
                            "argument": argument,
                            "phase": phase,
                            "status": "done",
                            "start_ms": tool_start_ms,
                            "duration_ms": elapsed_ms() - tool_start_ms,
                        }
                        summary = _tool_result_summary("READ", content)
                        if summary:
                            tool_entry["result"] = summary
                        if entry is not None:
                            tool_entry["title"] = entry.title
                        tool_calls_seen.append(tool_entry)
                        emit({"type": "tool_call", **tool_entry})
                    elif kind == "STATE":
                        if state_used >= MAX_STATE_ROUNDS:
                            results.append(
                                f"STATE {argument} -> error: STATE budget for this "
                                "turn is spent; answer from what you already have"
                            )
                            continue
                        state_used += 1
                        content = self._read_widget_state(chat_session, argument)
                        results.append(f"STATE {argument} -> {content}")
                        tool_entry = {
                            "name": "STATE",
                            "argument": argument,
                            "phase": phase,
                            "status": "done",
                            "start_ms": tool_start_ms,
                            "duration_ms": elapsed_ms() - tool_start_ms,
                        }
                        tool_calls_seen.append(tool_entry)
                        emit({"type": "tool_call", **tool_entry})
                    elif kind in RESOURCE_TOOL_BY_KEYWORD:
                        if resource_used >= MAX_RESOURCE_ROUNDS:
                            results.append(
                                f"{kind} {argument} -> error: resource tool budget "
                                "for this turn is spent; answer from what you already have"
                            )
                            continue
                        resource_used += 1
                        content = self._run_resource_tool(
                            kind, argument, chat_session, registry
                        )
                        results.append(f"{kind} {argument} -> {content}")
                        tool_entry = {
                            "name": kind,
                            "argument": argument,
                            "phase": phase,
                            "status": "done",
                            "start_ms": tool_start_ms,
                            "duration_ms": elapsed_ms() - tool_start_ms,
                        }
                        summary = _tool_result_summary(kind, content)
                        if summary:
                            tool_entry["result"] = summary
                        tool_calls_seen.append(tool_entry)
                        emit({"type": "tool_call", **tool_entry})
                    else:
                        if math_rounds >= MAX_TOOL_ROUNDS:
                            results.append(
                                f"{kind} {argument} -> error: math tool budget "
                                "for this turn is spent"
                            )
                            continue
                        executed_math = True
                        result = run_tool_line(kind, argument)
                        results.append(f"{kind} {argument} -> {result}")
                        tool_entry = {
                            "name": kind,
                            "argument": argument,
                            "phase": phase,
                            "status": "done",
                            "start_ms": tool_start_ms,
                            "duration_ms": elapsed_ms() - tool_start_ms,
                        }
                        summary = _tool_result_summary(kind, result)
                        if summary:
                            tool_entry["result"] = summary
                        tool_calls_seen.append(tool_entry)
                        emit({"type": "tool_call", **tool_entry})
                results_text = "\n".join(results)
                if executed_math:
                    math_rounds += 1
                if native_tools:
                    native_round.append(
                        Message(
                            role="assistant",
                            content="",
                            tool_calls=tuple(
                                {
                                    "id": call.get("id"),
                                    "name": call["name"],
                                    "args": call.get("arguments") or {},
                                }
                                for call in native_raw
                            ),
                        )
                    )
                    for index, call in enumerate(native_raw):
                        content = results[index].partition(" -> ")[2]
                        native_round.append(
                            Message(
                                role="tool",
                                content=content,
                                tool_call_id=call.get("id") or "",
                            )
                        )
                    continue
                tool_log = f"{tool_log}\n{results_text}" if tool_log else results_text
            if degraded_native:
                native_tools = False
                continue
            output = strip_tool_lines(output)
            if stream_interruption is not None:
                final_output = output
                emit(
                    {
                        "type": "stream_interrupted",
                        "detail": stream_interruption,
                        "elapsed_ms": elapsed_ms(),
                    }
                )
                break
            validation = validate(output, contract, context)
            if validation.ok:
                final_output = output
                final_tool_calls = tool_calls_seen
                break
            feedback_text = validation.feedback()
            final_output = output
        return self.finalize_turn(
            chat_session,
            user_message,
            prep,
            started=started,
            run_id=run_id,
            model_name=model_name,
            prompt_snapshot=prompt_snapshot,
            final_output=final_output,
            final_tool_calls=final_tool_calls,
            reads=reads,
            repair_rounds=attempt,
            trace_rounds=trace_rounds,
            reasoning_parts=reasoning_parts,
            stream_interruption=stream_interruption,
            validation=validation,
            emit=emit,
        )

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
        trace: dict[str, Any] = {
            "run_id": run_id,
            "model": model_name,
            "latency_ms": latency_ms,
            "input_tokens": _estimate_tokens(prompt_snapshot),
            "output_tokens": _estimate_tokens(final_output),
            "repair_rounds": repair_rounds,
            "rounds": trace_rounds,
        }
        if reasoning_parts:
            trace["thinking"] = "".join(reasoning_parts)
        if stream_interruption is not None:
            trace["stream_interrupted"] = True
            trace["interruption"] = stream_interruption
            emit(
                {
                    "type": "stream_interrupted",
                    "detail": stream_interruption,
                    "elapsed_ms": latency_ms,
                }
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
        proposal = (
            extract_proposal(final_output)
            if proposals_enabled
            else None
        )
        if proposal is not None or "```proposal" in final_output:
            final_output = strip_proposal_fences(final_output)
        used_mentions = registry.parse(final_output)
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
            warnings=[prep.turn_warning] if prep.turn_warning is not None else None,
        )
        message.parent_id = user_message.id
        user_message.active_child_id = message.id
        self._session.flush()
        proposal_row: ChatProposal | None = None
        if proposal is not None:
            action, payload = proposal
            proposal_row = ChatProposal(
                message_id=message.id,
                action=action,
                payload=payload,
                status="proposed",
            )
            self._session.add(proposal_row)
            self._session.flush()
        self._session.commit()
        logger.info(
            "chat_turn_timing",
            session_id=chat_session.id,
            phase="finalize",
            duration_ms=int((time.monotonic() - finalize_started) * 1000),
        )
        emit(
            {
                "type": "assistant_message",
                "elapsed_ms": latency_ms,
                "trace": trace,
                "message": {
                    "id": message.id,
                    "role": "assistant",
                    "markdown": final_output,
                    "citations": citations,
                    "mentions": [entry.as_dict() for entry in used_mentions],
                    "reads": reads,
                    "tool_calls": final_tool_calls,
                    "proposals": [_proposal_out(proposal_row)]
                    if proposal_row is not None
                    else [],
                    "grounded": grounded,
                },
            }
        )
        return message

    def answer(self, chat_session: ChatSession, user_message: ChatMessage) -> ChatMessage:
        return self.answer_streaming(chat_session, user_message, lambda _event: None)


def _proposal_out(proposal: ChatProposal | None) -> dict[str, Any]:
    if proposal is None:
        return {}
    return {
        "id": proposal.id,
        "action": proposal.action,
        "payload": proposal.payload,
        "status": proposal.status,
        "result": proposal.result,
    }


def _extract_citations(
    output: str, chunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
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
