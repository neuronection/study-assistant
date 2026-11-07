"""The chat tool seam: FIND/READ, DISCOVER, SEARCH/FETCH, QUIZ and the
resource tools (family plan 40 W1).
"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....ai.flow_events_chat import tool_call_event
from ....ai.mcp_resources import RESOURCE_TOOL_BY_KEYWORD, ResourceError
from ....ai.mentions import MentionRegistry
from ....ai.parsing import blocks_to_md as _blocks_to_md
from ....domain.models import (
    Activity,
    ChatSession,
    Concept,
    Course,
    Exercise,
    Extraction,
    Material,
    MaterialLink,
    NodeConcept,
    Note,
    Question,
    TreeNode,
)
from ....extensions.search.provider import SearchError, perform_fetch, search_with_fallback
from ...search import hybrid_search
from ..profiles import ensure_default_profile
from ..quizme import store_pending, validate_quiz_args
from .turn_context import STRUCTURE_SUMMARY_CHARS, TurnContextMixin

READ_CHARS = 4000
FIND_RESULT_LIMIT = 5
DISCOVER_RESULT_CAP = 5
NODE_MATERIALS_REG_CAP = 10
READ_NODE_CHILDREN_CAP = 8


def _quiz_answer_text(question: Question) -> str:
    answer = question.answer or {}
    if "index" in answer and question.options:
        try:
            return chr(ord("A") + int(answer["index"]))
        except (TypeError, ValueError):
            pass
    if "indices" in answer and question.options:
        try:
            return ", ".join(chr(ord("A") + int(item)) for item in answer["indices"])
        except (TypeError, ValueError):
            pass
    value = answer.get("value")
    return str(value) if value is not None else str(answer)


class ToolsMixin(TurnContextMixin):
    """The tool-execution half of `ChatService` (no turn orchestration)."""

    _session: Session
    _embedder: Any
    _search_transport: Any

    def _find_local(self, query: str, chat_session: ChatSession, registry: MentionRegistry) -> str:
        query = query.strip()
        if not query:
            return "error: expected 'FIND <query>'"
        course_id = chat_session.course_id
        if course_id is None:
            return "error: FIND needs a course-scoped chat session"
        lines: list[str] = []
        try:
            hits = hybrid_search(
                self._session,
                query,
                FIND_RESULT_LIMIT,
                self._embedder.embed,
                course_id=course_id,
            )
        except Exception:
            hits = []
        for hit in hits[:FIND_RESULT_LIMIT]:
            material = self._session.get(Material, str(hit["material_id"]))
            if material is None or material.course_id != course_id:
                continue
            entry = registry.add("material", material.id, material.title, material.course_id)
            lines.append(f"{entry.ref} — {material.title} (material)")
        words = [w for w in query.split() if len(w) >= 3] or [query]
        notes = self._session.scalars(
            select(Note).where(
                Note.course_id == course_id,
                *[Note.search_text.like(f"%{word}%") for word in words],
            )
        ).all()
        for note in notes[:FIND_RESULT_LIMIT]:
            entry = registry.add("note", note.id, note.title, note.course_id)
            lines.append(f"{entry.ref} — {note.title} (note)")
        if not lines:
            return (
                "no matching materials or notes in this course — try different "
                "words or answer from the offered manifest"
            )
        return "\n".join(lines[: FIND_RESULT_LIMIT * 2])

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
            parts = [str(block.get("md", "")) for block in note.body if block.get("md")] + [
                d.ocr_markdown for d in note.drawings if d.ocr_markdown
            ]
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
            children = self._child_nodes(node.id)
            if children:
                rendered = []
                for child in children[:READ_NODE_CHILDREN_CAP]:
                    child_summary = " ".join((child.summary or "").split())[
                        :STRUCTURE_SUMMARY_CHARS
                    ]
                    registry.add(
                        "node",
                        child.id,
                        child.title,
                        child.course_id,
                        child_summary or None,
                    )
                    rendered.append(self._structure_entry(child))
                if len(children) > READ_NODE_CHILDREN_CAP:
                    rendered.append(f"… +{len(children) - READ_NODE_CHILDREN_CAP} more")
                lines.append(f"Children: {' | '.join(rendered)}")
            links = self._session.execute(
                select(MaterialLink, Material)
                .join(Material, MaterialLink.material_id == Material.id)
                .where(MaterialLink.node_id == node.id)
                .order_by(MaterialLink.created_at)
            ).all()
            if links:
                rendered = []
                for _link, material in links[:NODE_MATERIALS_REG_CAP]:
                    registry.add("material", material.id, material.title, material.course_id)
                    rendered.append(f"[M{material.id}] {material.title}")
                if len(links) > NODE_MATERIALS_REG_CAP:
                    rendered.append(f"… +{len(links) - NODE_MATERIALS_REG_CAP} more")
                lines.append(f"Materials: {' | '.join(rendered)}")
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
                f"{exercise.title} — {exercise.kind} exercise with {len(exercise.steps)} steps"
            ]
            for index, step in enumerate(exercise.steps, start=1):
                lines.append(f"Step {index}: {_blocks_to_md(step.prompt)}")
                if step.expected is not None:
                    compact = json.dumps(step.expected, ensure_ascii=False, default=str)
                    lines.append(f"   expected: {compact}")
            return "\n".join(lines)[:READ_CHARS]
        return f"error: {entry.kind} items cannot be READ"

    def _here_query(self, chat_session: ChatSession) -> str | None:
        """Deterministic `DISCOVER here` query from the session context."""
        if chat_session.node_id is not None and chat_session.course_id is not None:
            node = self._session.get(TreeNode, chat_session.node_id)
            if node is not None and node.course_id == chat_session.course_id:
                parts = [node.title]
                if node.summary:
                    parts.append(str(node.summary)[:200])
                if node.ai_hint:
                    parts.append(str(node.ai_hint)[:150])
                concept_names = list(
                    self._session.scalars(
                        select(Concept.name)
                        .join(NodeConcept, NodeConcept.concept_id == Concept.id)
                        .where(NodeConcept.node_id == node.id)
                        .limit(4)
                    )
                )
                parts.extend(concept_names)
                return " ".join(part for part in parts if part)[:300]
        if chat_session.course_id is not None:
            course = self._session.get(Course, chat_session.course_id)
            if course is not None:
                parts = [course.title]
                if course.description:
                    parts.append(str(course.description)[:200])
                return " ".join(part for part in parts if part)[:300]
        return None

    def _discover(self, argument: str, chat_session: ChatSession) -> tuple[str, list[str]]:
        from ....extensions.registry import extension_registry
        from ....extensions.search.discovery import DiscoveryError, resolve_providers

        if not extension_registry.has_capability("discovery", "chat-tools"):
            return "error: the discovery bundle does not declare chat-tools", []
        query = argument.strip()
        if query.lower() == "here":
            built = self._here_query(chat_session)
            if built is None:
                return (
                    "error: this session has no course context — pass an "
                    "explicit discovery query instead of `here`",
                    [],
                )
            query = built
        profile = ensure_default_profile(self._session)
        try:
            providers = resolve_providers(self._session, profile.id)
        except DiscoveryError as error:
            return f"error: {error}", []
        if not providers:
            return (
                "error: no discovery providers configured — the student can "
                "enable them in Settings → Integrations",
                [],
            )
        lines: list[str] = []
        urls: list[str] = []
        errors: list[str] = []
        for provider in providers:
            try:
                found = provider.search(
                    query, cap=DISCOVER_RESULT_CAP, transport=self._search_transport
                )
            except Exception as error:
                errors.append(f"{provider.label}: {error}")
                continue
            for row in found:
                if row.url in urls:
                    continue
                lines.append(f"[{len(lines) + 1}] {row.title} — {row.url} ({provider.label})")
                urls.append(row.url)
        if not lines:
            if errors:
                return f"error: discovery failed — {errors[0]}", []
            return "no results found", []
        return "\n".join(lines[:DISCOVER_RESULT_CAP]), urls[:DISCOVER_RESULT_CAP]

    def _search_web(self, query: str) -> tuple[str, list[str]]:
        profile = ensure_default_profile(self._session)
        try:
            hits = search_with_fallback(
                self._session, profile.id, query, transport=self._search_transport
            )
        except SearchError as error:
            return f"error: {error}", []
        if hits is None:
            return (
                "error: no search provider configured — the student can add one "
                "in Settings → Tools → Web search",
                [],
            )
        if not hits:
            return "no results found", []
        lines: list[str] = []
        urls: list[str] = []
        for index, hit in enumerate(hits, start=1):
            lines.append(f"[{index}] {hit['title']} — {hit['url']}")
            if hit["content"]:
                lines.append(hit["content"])
            urls.append(hit["url"])
        return "\n".join(lines), urls

    def _fetch_url(self, url: str) -> str:
        try:
            return str(perform_fetch(url, transport=self._search_transport))
        except SearchError as error:
            return f"error: {error}"

    def _handle_quiz_tool(
        self,
        chat_session: ChatSession,
        argument: str,
        phase: str,
        tool_start_ms: float,
        duration_ms: int,
        emit: Any,
    ) -> tuple[str, dict[str, Any]]:
        entry: dict[str, Any] = {
            "name": "QUIZ",
            "argument": argument,
            "phase": phase,
            "status": "done",
            "start_ms": tool_start_ms,
            "duration_ms": duration_ms,
        }
        if not chat_session.quizme:
            # the schema is always bound, but grading cards only exist in
            # quiz-me sessions — otherwise answer in prose
            result = (
                "error: quiz-me is off for this conversation — the student "
                "has not enabled it; do not attempt to quiz them"
            )
            entry["result"] = result
            emit(tool_call_event(entry))
            return result, entry
        try:
            args = (
                json.loads(argument) if argument.strip().startswith("{") else {"question": argument}
            )
        except ValueError:
            args = {"question": argument}
        if not isinstance(args, dict):
            args = {"question": str(argument)}
        try:
            pending = validate_quiz_args(args)
        except ValueError as error:
            result = f"error: {error}"
            entry["result"] = result
            emit(tool_call_event(entry))
            return result, entry
        pending["awaiting_answer"] = True
        store_pending(self._session, chat_session, pending)
        self._session.flush()
        result = (
            "question presented to the student as an interactive card — end "
            "your turn; their graded answer arrives with the next message"
        )
        entry["result"] = "question presented — awaiting the student's answer"
        entry["quiz"] = {
            "question": pending["question"],
            "choices": pending.get("choices"),
        }
        emit(tool_call_event(entry))
        return result, entry

    def _resolve_node_arg(
        self,
        argument: str,
        chat_session: ChatSession,
        registry: MentionRegistry,
    ) -> str | None:
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
        kwargs: dict[str, Any] = dict(spec.get("kwargs") or {})
        if spec["arg"] == "node":
            node_id = self._resolve_node_arg(argument, chat_session, registry)
            if node_id is None:
                return (
                    "error: need a node handle (T#) from the referenceable-items "
                    "manifest, or 'here' for the current node"
                )
            kwargs["node_id"] = node_id
        elif spec["arg"] == "course":
            if chat_session.course_id is None:
                return "error: this tool needs a course-scoped chat session"
            kwargs["course_id"] = chat_session.course_id
        try:
            result = spec["call"](self._session, **kwargs)
        except ResourceError as error:
            return f"error: {error}"
        if keyword == "NODE_MATERIALS" and isinstance(result, dict):
            for entry in (result.get("direct") or [])[:NODE_MATERIALS_REG_CAP]:
                registry.add(
                    "material",
                    str(entry["material_id"]),
                    str(entry["title"]),
                    chat_session.course_id,
                )
        return json.dumps(result, ensure_ascii=False, default=str)[:2000]
