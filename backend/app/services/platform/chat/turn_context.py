"""Per-turn chat context assembly: guards, notes, structure, registry (family plan 40 W1)."""

from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ....ai.mentions import MentionRegistry, registry_from_json
from ....ai.parsing import blocks_to_md as _blocks_to_md
from ....domain.models import (
    Activity,
    Answer,
    Attempt,
    ChatSession,
    Course,
    Exercise,
    ExerciseSession,
    ExerciseStep,
    Material,
    MaterialIndexCard,
    Note,
    Profile,
    Question,
    StepAttempt,
    TreeNode,
)
from ....domain.payloads import MentionRegistryList
from ...knowledge.context import ContextResolver, ContextScope, ContextSpec
from ...search import retrieve_chunks_hybrid
from ...study.tutor import quiz_guard_context
from .errors import ChatError

RETRIEVE_LIMIT = 6
REGISTRY_MATERIALS_CAP = 30
STRUCTURE_GROUP_CAP = 8
STRUCTURE_SUMMARY_CHARS = 80

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


class TurnContextMixin:
    """The turn-context half of `ChatService` (guards/notes/structure/registry)."""

    _session: Session
    _embedder: Any

    def _quiz_guard(self, chat_session: ChatSession) -> dict[str, Any] | None:
        binding = chat_session.context or {}
        attempt_id = binding.get("quiz_attempt_id")
        question_id = binding.get("question_id")
        if not attempt_id or not question_id:
            return None
        attempt = self._session.get(Attempt, str(attempt_id))
        if attempt is None or attempt.finished_at is not None:
            return None
        answered = (
            self._session.scalars(
                select(Answer.id).where(
                    Answer.attempt_id == attempt.id, Answer.question_id == str(question_id)
                )
            ).first()
            is not None
        )
        if answered:
            return None
        question = self._session.get(Question, str(question_id))
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
        exercise_session = self._session.get(ExerciseSession, str(exercise_session_id))
        if exercise_session is None or exercise_session.status != "active":
            return None
        step = self._session.scalars(
            select(ExerciseStep).where(
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
                .order_by(StepAttempt.created_at, StepAttempt.id)
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
            outcome = (
                "correct"
                if last.correct
                else (f"not yet correct ({last.error_class or 'no diagnosis'})")
            )
            lines.append(f"Submitted attempts on this step: {len(attempts)} (latest: {outcome})")
        else:
            lines.append("Submitted attempts on this step: none yet")
        return "The student is working on this exercise step (extra context):\n" + "\n".join(lines)

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
            body = "\n".join(str(block.get("md", "")) for block in note.body if block.get("md"))
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
                f"Semantic search is on, but {reason} — using keyword search for this answer."
            )

        if chat_session.course_id is not None:
            spec = ContextSpec(
                course_id=chat_session.course_id,
                node_id=chat_session.node_id,
                scope=ContextScope.subtree,
                query=query,
                max_chunks=RETRIEVE_LIMIT,
            )
            bundle = ContextResolver(self._session, self._embedder.embed).resolve(
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
                str(entry["id"]),
                str(entry["title"]),
                chat_session.course_id,
                str(entry["summary"]) if entry.get("summary") else None,
            )
        for note in notes:
            registry.add("note", note.id, note.title, note.course_id)
        chat_session.mention_registry = cast(MentionRegistryList, registry.to_json())
        self._session.commit()
        return registry

    def _root_node(self, course_id: str) -> TreeNode | None:
        return self._session.scalars(
            select(TreeNode).where(TreeNode.course_id == course_id, TreeNode.is_root.is_(True))
        ).first()

    def _child_nodes(self, parent_id: str) -> list[TreeNode]:
        return list(
            self._session.scalars(
                select(TreeNode).where(TreeNode.parent_id == parent_id).order_by(TreeNode.order_idx)
            )
        )

    def _structure_entry(self, node: TreeNode) -> str:
        summary = " ".join((node.summary or "").split())[:STRUCTURE_SUMMARY_CHARS]
        base = f"[T{node.id}] {node.title}"
        return f"{base} — {summary}" if summary else base

    def _structure_block(self, chat_session: ChatSession, registry: MentionRegistry) -> str:
        if chat_session.course_id is None:
            return ""
        node = (
            self._session.get(TreeNode, chat_session.node_id)
            if chat_session.node_id is not None
            else self._root_node(chat_session.course_id)
        )
        if node is None:
            return ""
        course = self._session.get(Course, chat_session.course_id)

        def register(nodes: list[TreeNode]) -> list[str]:
            rendered = []
            for entry in nodes[:STRUCTURE_GROUP_CAP]:
                summary = " ".join((entry.summary or "").split())[:STRUCTURE_SUMMARY_CHARS]
                registry.add(
                    "node",
                    entry.id,
                    entry.title,
                    entry.course_id,
                    summary or None,
                )
                rendered.append(self._structure_entry(entry))
            if len(nodes) > STRUCTURE_GROUP_CAP:
                rendered.append(f"… +{len(nodes) - STRUCTURE_GROUP_CAP} more")
            return rendered

        registry.add(
            "node",
            node.id,
            node.title,
            node.course_id,
            " ".join((node.summary or "").split())[:STRUCTURE_SUMMARY_CHARS] or None,
        )
        lines: list[str] = [
            "Course structure (the [T#] ids are referenceable — READ one for "
            "details, or target it when a task fits another node better):"
        ]
        if node.is_root:
            location = course.title if course is not None else node.title
            lines.append(f"Location: {location} (course level)")
            children = self._child_nodes(node.id)
            if children:
                lines.append(f"Chapters: {' | '.join(register(children))}")
            return "\n".join(lines)
        chain: list[str] = []
        cursor_id = node.parent_id
        while cursor_id is not None and len(chain) < 6:
            ancestor = self._session.get(TreeNode, cursor_id)
            if ancestor is None:
                break
            chain.append(ancestor.title)
            cursor_id = ancestor.parent_id
        chain.reverse()
        parent = self._session.get(TreeNode, node.parent_id) if node.parent_id is not None else None
        parts = list(chain)
        course_title = course.title if course is not None else None
        if course_title and (not parts or parts[0] != course_title):
            parts.insert(0, course_title)
        parts.append(node.title)
        lines.append("Location: " + " > ".join(part for part in parts if part))
        if parent is not None:
            parent_summary = " ".join((parent.summary or "").split())[:STRUCTURE_SUMMARY_CHARS]
            registry.add(
                "node",
                parent.id,
                parent.title,
                parent.course_id,
                parent_summary or None,
            )
            lines.append(f"Parent: {self._structure_entry(parent)}")
            siblings = [entry for entry in self._child_nodes(parent.id) if entry.id != node.id]
            if siblings:
                lines.append(f"Siblings: {' | '.join(register(siblings))}")
        children = self._child_nodes(node.id)
        if children:
            lines.append(f"Children: {' | '.join(register(children))}")
        return "\n".join(lines)

    def attach(
        self,
        chat_session: ChatSession,
        attachments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        registry = registry_from_json(chat_session.mention_registry)
        stored: list[dict[str, Any]] = []
        for attachment in attachments:
            kind = str(attachment.get("kind"))
            item_id = str(attachment.get("id", ""))
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
                entry = registry.add("node", node.id, node.title, node.course_id, node.summary)
            elif kind == "course":
                course = self._session.get(Course, item_id)
                if course is None:
                    raise ChatError(f"course {item_id} not found")
                root = self._root_node(course.id)
                if root is None:
                    raise ChatError(f"course {item_id} not found")
                entry = registry.add("node", root.id, course.title, course.id, course.description)
            else:
                raise ChatError(f"unknown attachment kind: {kind}")
            stored.append(entry.as_dict())
        if stored:
            chat_session.mention_registry = cast(MentionRegistryList, registry.to_json())
            self._session.flush()
        return stored
