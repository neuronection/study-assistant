from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.mentions import MentionRegistry
from ..domain.models import (
    Concept,
    Course,
    Material,
    MaterialFolder,
    MaterialIndexCard,
    MaterialLink,
    Note,
    TreeNode,
)
from .folders import folder_links_by_node, folder_member_ids
from .search import EmbedQuery, retrieve_chunks_hybrid
from .tree import subtree_material_ids

RETRIEVAL_EXCLUDED_KINDS = {"node_review"}

NOTE_CHARS = 1500
MANIFEST_MATERIALS_CAP = 30
NODES_CAP = 16


class ContextError(ValueError):
    pass


class ContextScope(StrEnum):
    node = "node"
    subtree = "subtree"
    course = "course"


class ContextSpec(BaseModel):
    course_id: int
    node_id: int | None = None
    scope: ContextScope = ContextScope.subtree
    include_material_ids: list[int] = Field(default_factory=list)
    exclude_material_ids: list[int] = Field(default_factory=list)
    note_ids: list[int] = Field(default_factory=list)
    concept_ids: list[int] = Field(default_factory=list)
    hint: str | None = Field(default=None, max_length=2000)
    query: str | None = Field(default=None, max_length=500)
    max_chunks: int = Field(default=12, ge=0, le=32)
    chunk_chars: int = Field(default=1000, ge=200, le=4000)
    exclude_ai_composed: bool = False


class ContextParams(BaseModel):
    scope: ContextScope = ContextScope.subtree
    include_material_ids: list[int] = Field(default_factory=list)
    exclude_material_ids: list[int] = Field(default_factory=list)
    note_ids: list[int] = Field(default_factory=list)
    concept_ids: list[int] = Field(default_factory=list)
    context_hint: str | None = Field(default=None, max_length=2000)

    def to_spec(
        self,
        *,
        course_id: int,
        node_id: int | None = None,
        query: str | None = None,
        max_chunks: int = 12,
        chunk_chars: int = 1000,
    ) -> ContextSpec:
        return ContextSpec(
            course_id=course_id,
            node_id=node_id,
            scope=self.scope,
            include_material_ids=self.include_material_ids,
            exclude_material_ids=self.exclude_material_ids,
            note_ids=self.note_ids,
            concept_ids=self.concept_ids,
            hint=self.context_hint,
            query=query,
            max_chunks=max_chunks,
            chunk_chars=chunk_chars,
        )


class ContextBundle:
    def __init__(
        self,
        spec: ContextSpec,
        *,
        node: TreeNode | None,
        breadcrumb: list[dict[str, Any]],
        material_ids: list[int] | None,
        materials: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        notes: list[dict[str, Any]],
        concepts: list[dict[str, Any]],
        hints: list[dict[str, Any]],
        nodes: list[dict[str, Any]] | None = None,
    ) -> None:
        self.spec = spec
        self.node = node
        self.breadcrumb = breadcrumb
        self.material_ids = material_ids
        self.materials = materials
        self.chunks = chunks
        self.notes = notes
        self.concepts = concepts
        self.hints = hints
        self.nodes = nodes or []

    def mentions(self) -> MentionRegistry:
        registry = MentionRegistry()
        for entry in self.materials:
            registry.add("material", int(entry["id"]), str(entry["title"]), self.spec.course_id)
        for entry in self.notes:
            registry.add("note", int(entry["id"]), str(entry["title"]), self.spec.course_id)
        for entry in self.concepts:
            registry.add("concept", int(entry["id"]), str(entry["name"]), self.spec.course_id)
        for entry in self.nodes:
            registry.add("node", int(entry["id"]), str(entry["title"]), self.spec.course_id)
        return registry

    @property
    def empty(self) -> bool:
        return not (
            self.chunks or self.notes or self.concepts or self.hints or self.node
        )

    def _scope_section(self) -> str:
        lines: list[str] = []
        if self.node is not None and not self.node.is_root:
            trail = " > ".join(str(entry["title"]) for entry in self.breadcrumb)
            lines.append(f"Study scope: {trail}")
            if self.node.summary:
                lines.append(f"Scope summary: {self.node.summary.strip()}")
            objectives = self.node.objectives or []
            if objectives:
                lines.append(
                    "Learning objectives:\n"
                    + "\n".join(f"- {objective}" for objective in objectives[:8])
                )
        return "\n".join(lines)

    def _hints_section(self) -> str:
        if not self.hints:
            return ""
        lines = ["Instructions for this task:"]
        for entry in self.hints:
            lines.append(f"- [{entry['source']}] {entry['text']}")
        return "\n".join(lines)

    def _materials_section(self) -> str:
        if not self.materials:
            return ""
        lines = ["Materials in scope:"]
        for entry in self.materials[:MANIFEST_MATERIALS_CAP]:
            description = entry.get("summary") or ""
            topics = entry.get("topics") or []
            if topics:
                topic_text = ", ".join(str(topic) for topic in topics[:6])
                description = f"{description} (topics: {topic_text})".strip()
            marker = f"[M{entry['id']}] {entry['title']}"
            lines.append(f"{marker} — {description}" if description else marker)
        return "\n".join(lines)

    def _concepts_section(self) -> str:
        if not self.concepts:
            return ""
        lines = ["Focus concepts:"]
        for entry in self.concepts:
            marker = f"[C{entry['id']}] {entry['name']}"
            description = entry.get("description")
            lines.append(f"{marker} — {description}" if description else marker)
        return "\n".join(lines)

    def _notes_section(self) -> str:
        if not self.notes:
            return ""
        lines = ["Attached notes (student's own material):"]
        for entry in self.notes:
            lines.append(f"### [N{entry['id']}] {entry['title']}\n{entry['text']}")
        return "\n".join(lines)

    def _nodes_section(self) -> str:
        if not self.nodes:
            return ""
        lines = ["Structure in scope (referenceable as [T<id>]):"]
        for entry in self.nodes:
            lines.append(f"[T{entry['id']}] {entry['title']}")
        return "\n".join(lines)

    def _chunks_section(self) -> str:
        if not self.chunks:
            return ""
        lines = ["Source excerpts from the course material:"]
        for index, chunk in enumerate(self.chunks, start=1):
            excerpt = str(chunk["text"])[: self.spec.chunk_chars]
            lines.append(f"[{index}] ({chunk['title']}) {excerpt}")
        return "\n".join(lines)

    def render_hints(self) -> str:
        return self._hints_section()

    def render_extras(self) -> str:
        sections = [
            self._hints_section(),
            self._concepts_section(),
            self._notes_section(),
        ]
        return "\n\n".join(section for section in sections if section)

    def render_prompt(self) -> str:
        sections = [
            self._scope_section(),
            self._hints_section(),
            self._materials_section(),
            self._nodes_section(),
            self._concepts_section(),
            self._notes_section(),
            self._chunks_section(),
        ]
        return "\n\n".join(section for section in sections if section)

    def stats(self) -> dict[str, Any]:
        return {
            "materials": [
                {"id": entry["id"], "title": entry["title"]} for entry in self.materials
            ],
            "chunks": [
                {"material_id": chunk["material_id"], "title": chunk["title"]}
                for chunk in self.chunks
            ],
            "notes": [{"id": entry["id"], "title": entry["title"]} for entry in self.notes],
            "concepts": [
                {"id": entry["id"], "name": entry["name"]} for entry in self.concepts
            ],
            "nodes": [
                {"id": entry["id"], "title": entry["title"]} for entry in self.nodes
            ],
            "hints": len(self.hints),
            "approx_chars": len(self.render_prompt()),
            "retrieval_query": self.spec.query,
        }


class ContextResolver:
    def __init__(self, session: Session, embed_query: EmbedQuery) -> None:
        self._session = session
        self._embed_query = embed_query

    def _node(self, spec: ContextSpec) -> TreeNode:
        if spec.node_id is not None:
            node = self._session.get(TreeNode, spec.node_id)
            if node is None or node.course_id != spec.course_id:
                raise ContextError("node belongs to a different course")
            return node
        root = self._session.scalars(
            select(TreeNode).where(
                TreeNode.course_id == spec.course_id, TreeNode.is_root.is_(True)
            )
        ).first()
        if root is None:
            raise ContextError("course has no root node")
        return root

    def _breadcrumb(self, node: TreeNode) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        current: TreeNode | None = node
        while current is not None:
            chain.append({"id": current.id, "title": current.title})
            current = (
                self._session.get(TreeNode, current.parent_id)
                if current.parent_id is not None
                else None
            )
        chain.reverse()
        course = self._session.get(Course, node.course_id)
        if course is not None and chain:
            chain[0] = {"id": chain[0]["id"], "title": course.title}
        return chain

    def _hints(self, spec: ContextSpec, node: TreeNode) -> list[dict[str, Any]]:
        hints: list[dict[str, Any]] = []
        chain: list[TreeNode] = []
        current: TreeNode | None = node
        while current is not None:
            chain.append(current)
            current = (
                self._session.get(TreeNode, current.parent_id)
                if current.parent_id is not None
                else None
            )
        for ancestor in reversed(chain):
            if ancestor.ai_hint and ancestor.ai_hint.strip():
                source = "Course guidance" if ancestor.is_root else f"Node '{ancestor.title}'"
                hints.append({"source": source, "text": ancestor.ai_hint.strip()})
        if spec.hint and spec.hint.strip():
            hints.append({"source": "For this request", "text": spec.hint.strip()})
        return hints

    def _scope_material_ids(self, spec: ContextSpec, node: TreeNode) -> list[int] | None:
        if spec.scope == ContextScope.course or (
            node.is_root and spec.scope == ContextScope.subtree
        ):
            return None
        if spec.scope == ContextScope.node:
            ids: set[int] = set(
                self._session.scalars(
                    select(MaterialLink.material_id).where(
                        MaterialLink.course_id == spec.course_id,
                        MaterialLink.node_id == node.id,
                    )
                )
            )
            for folder_link in folder_links_by_node(self._session, [node.id])[node.id]:
                folder = self._session.get(MaterialFolder, folder_link.folder_id)
                if folder is not None:
                    ids |= folder_member_ids(self._session, folder)
            return sorted(ids)
        return subtree_material_ids(self._session, node)

    def _validate_material_ids(self, ids: list[int], spec: ContextSpec, label: str) -> None:
        if not ids:
            return
        rows = {
            material.id: material
            for material in self._session.scalars(
                select(Material).where(Material.id.in_(ids))
            )
        }
        for material_id in ids:
            material = rows.get(material_id)
            if material is None or material.course_id != spec.course_id:
                raise ContextError(f"{label} material {material_id} is not in this course")

    def _resolve_material_ids(
        self, spec: ContextSpec, node: TreeNode
    ) -> tuple[list[int] | None, list[dict[str, Any]]]:
        self._validate_material_ids(spec.include_material_ids, spec, "included")
        self._validate_material_ids(spec.exclude_material_ids, spec, "excluded")
        excluded = self._excluded_kind_ids(spec.course_id)
        base = self._scope_material_ids(spec, node)
        if base is None:
            statement = select(Material.id).where(Material.course_id == spec.course_id)
            if spec.exclude_ai_composed:
                statement = statement.where(Material.provenance.is_(None))
            course_material_ids = [
                mid for mid in self._session.scalars(statement) if mid not in excluded
            ]
            if not spec.include_material_ids and not spec.exclude_material_ids:
                filtered = course_material_ids if spec.exclude_ai_composed else None
            else:
                filtered = sorted(
                    (set(course_material_ids) | set(spec.include_material_ids))
                    - set(spec.exclude_material_ids)
                )
            candidates = course_material_ids if filtered is None else filtered
            if filtered is None and excluded:
                filtered = course_material_ids
        else:
            merged = (set(base) | set(spec.include_material_ids)) - set(
                spec.exclude_material_ids
            )
            merged -= excluded
            if spec.exclude_ai_composed:
                composed = set(
                    self._session.scalars(
                        select(Material.id).where(
                            Material.course_id == spec.course_id,
                            Material.provenance.is_not(None),
                        )
                    )
                )
                merged -= composed
            filtered = sorted(merged)
            candidates = filtered
        materials: list[dict[str, Any]] = []
        if candidates:
            cards = {
                card.material_id: card
                for card in self._session.scalars(
                    select(MaterialIndexCard).where(
                        MaterialIndexCard.material_id.in_(candidates)
                    )
                )
            }
            rows = {
                material.id: material
                for material in self._session.scalars(
                    select(Material).where(Material.id.in_(candidates))
                )
            }
            for material_id in candidates:
                material = rows.get(material_id)
                if material is None:
                    continue
                card = cards.get(material_id)
                materials.append(
                    {
                        "id": material_id,
                        "title": material.title,
                        "summary": card.summary.strip() if card and card.summary else None,
                        "topics": card.topics if card else None,
                    }
                )
        return filtered, materials

    def _excluded_kind_ids(self, course_id: int) -> set[int]:
        rows = self._session.execute(
            select(Material.id, Material.provenance).where(
                Material.course_id == course_id,
                Material.provenance.is_not(None),
            )
        ).all()
        return {
            material_id
            for material_id, provenance in rows
            if isinstance(provenance, dict)
            and provenance.get("kind") in RETRIEVAL_EXCLUDED_KINDS
        }

    def _resolve_notes(self, spec: ContextSpec) -> list[dict[str, Any]]:
        if not spec.note_ids:
            return []
        notes = {
            note.id: note
            for note in self._session.scalars(
                select(Note).where(Note.id.in_(spec.note_ids))
            )
        }
        for note_id in spec.note_ids:
            note = notes.get(note_id)
            if note is None or note.course_id != spec.course_id:
                raise ContextError(f"note {note_id} is not in this course")
        result: list[dict[str, Any]] = []
        for note_id in spec.note_ids:
            note = notes[note_id]
            drawings = {drawing.id: drawing for drawing in note.drawings}
            referenced: set[int] = set()
            parts: list[str] = []
            for block in note.body or []:
                if block.get("type") == "drawing":
                    drawing = drawings.get(int(block.get("drawing_id", 0)))
                    if drawing is not None:
                        referenced.add(drawing.id)
                    if drawing is not None and drawing.ocr_markdown:
                        parts.append(f"```\n{drawing.ocr_markdown}\n```")
                elif block.get("md"):
                    parts.append(str(block["md"]))
            for drawing in note.drawings:
                if drawing.id not in referenced and drawing.ocr_markdown:
                    parts.append(drawing.ocr_markdown)
            text = "\n".join(parts)[:NOTE_CHARS]
            result.append({"id": note.id, "title": note.title, "text": text})
        return result

    def _resolve_concepts(self, spec: ContextSpec) -> list[dict[str, Any]]:
        if not spec.concept_ids:
            return []
        concepts = {
            concept.id: concept
            for concept in self._session.scalars(
                select(Concept).where(Concept.id.in_(spec.concept_ids))
            )
        }
        for concept_id in spec.concept_ids:
            concept = concepts.get(concept_id)
            if concept is None or concept.course_id != spec.course_id:
                raise ContextError(f"concept {concept_id} is not in this course")
        return [
            {
                "id": concept.id,
                "name": concept.name,
                "description": concept.description,
            }
            for concept in (
                concepts[concept_id] for concept_id in spec.concept_ids
            )
        ]

    def _scope_nodes(self, node: TreeNode) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        if not node.is_root:
            nodes.append({"id": node.id, "title": node.title})
        children = self._session.execute(
            select(TreeNode.id, TreeNode.title)
            .where(TreeNode.parent_id == node.id)
            .order_by(TreeNode.sort_path)
            .limit(NODES_CAP)
        )
        for child_id, title in children:
            nodes.append({"id": child_id, "title": title})
        return nodes[:NODES_CAP]

    def resolve(
        self,
        spec: ContextSpec,
        use_embeddings: bool = True,
        embedding_warning: Callable[[str], None] | None = None,
    ) -> ContextBundle:
        course = self._session.get(Course, spec.course_id)
        if course is None:
            raise ContextError("course not found")
        node = self._node(spec)
        material_ids, materials = self._resolve_material_ids(spec, node)
        notes = self._resolve_notes(spec)
        concepts = self._resolve_concepts(spec)
        hints = self._hints(spec, node)
        nodes = self._scope_nodes(node)
        chunks: list[dict[str, Any]] = []
        if spec.max_chunks > 0 and (material_ids is None or material_ids):
            chunks = retrieve_chunks_hybrid(
                self._session,
                spec.query or "course material overview",
                self._embed_query,
                course_id=spec.course_id,
                material_ids=material_ids,
                limit=spec.max_chunks,
                use_embeddings=use_embeddings,
                embedding_warning=embedding_warning,
            )
        return ContextBundle(
            spec,
            node=None if node.is_root else node,
            breadcrumb=self._breadcrumb(node),
            material_ids=material_ids,
            materials=materials,
            chunks=chunks,
            notes=notes,
            concepts=concepts,
            hints=hints,
            nodes=nodes,
        )
