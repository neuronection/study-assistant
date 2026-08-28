from time import monotonic as time_monotonic
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from ..domain.models import (
    Activity,
    ChatSession,
    Concept,
    Course,
    Exercise,
    FsrsState,
    Material,
    MaterialFolder,
    MaterialFolderLink,
    MaterialLink,
    MaterialStudyState,
    NodeConcept,
    Note,
    TreeNode,
    utcnow,
)
from .folders import folder_links_by_node, folder_member_ids

MAX_DEPTH = 4
ORDER_STEP = 1000

_SNAPSHOT_TTL_SEC = 300.0
_SNAPSHOT_CAP = 20

_SNAPSHOTS: dict[str, dict[str, Any]] = {}


def _prune_snapshots() -> None:
    now = time_monotonic()
    expired = [
        token for token, entry in _SNAPSHOTS.items()
        if now - entry["created_at"] > _SNAPSHOT_TTL_SEC
    ]
    for token in expired:
        del _SNAPSHOTS[token]
    while len(_SNAPSHOTS) > _SNAPSHOT_CAP:
        oldest = min(_SNAPSHOTS, key=lambda token: _SNAPSHOTS[token]["created_at"])
        del _SNAPSHOTS[oldest]


def subtree_material_ids(session: Session, node: TreeNode) -> list[int]:
    subtree = list(
        session.scalars(
            select(TreeNode.id).where(
                TreeNode.course_id == node.course_id,
                TreeNode.path.like(f"{node.path}%"),
            )
        )
    )
    if not subtree:
        return []
    ids: set[int] = set(
        session.scalars(
            select(MaterialLink.material_id).where(
                MaterialLink.course_id == node.course_id,
                MaterialLink.node_id.in_(subtree),
            )
        )
    )
    folder_links = [
        link
        for links in folder_links_by_node(session, subtree).values()
        for link in links
    ]
    for folder_link in folder_links:
        folder = session.get(MaterialFolder, folder_link.folder_id)
        if folder is not None:
            ids |= folder_member_ids(session, folder)
    return sorted(ids)


PLACEMENT_TABLES: dict[str, type[Any]] = {
    "material_links": MaterialLink,
    "material_folder_links": MaterialFolderLink,
    "activities": Activity,
    "exercises": Exercise,
    "notes": Note,
    "chat_sessions": ChatSession,
}


class TreeError(ValueError):
    pass


class TreeService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_root(self, course_id: int) -> TreeNode:
        root = self._session.scalars(
            select(TreeNode).where(
                TreeNode.course_id == course_id, TreeNode.is_root.is_(True)
            )
        ).first()
        if root is not None:
            return root
        course = self._session.get(Course, course_id)
        if course is None:
            raise TreeError("course not found")
        root = TreeNode(
            course_id=course_id,
            parent_id=None,
            title=course.title,
            summary=course.description,
            order_idx=0,
            depth=0,
            path="/",
            sort_path="/",
            is_root=True,
        )
        self._session.add(root)
        self._session.flush()
        root.path = f"/{root.id}/"
        self._session.flush()
        return root

    def get(self, node_id: int) -> TreeNode:
        node = self._session.get(TreeNode, node_id)
        if node is None:
            raise TreeError("node not found")
        return node

    def placement_node(self, course_id: int | None, node_id: int | None) -> int | None:
        if node_id is not None:
            node = self.get(node_id)
            if course_id is not None and node.course_id != course_id:
                raise TreeError("node belongs to a different course")
            return node.id
        if course_id is not None:
            return self.ensure_root(course_id).id
        return None

    def _node_sort(self, order_idx: int) -> str:
        return f"{order_idx:06d}/"

    def _refresh_subtree_paths(
        self, node: TreeNode, parent_path: str, parent_sort: str
    ) -> None:
        node.path = f"{parent_path}{node.id}/"
        node.sort_path = f"{parent_sort}{self._node_sort(node.order_idx)}"
        self._session.flush()
        children = list(
            self._session.scalars(
                select(TreeNode)
                .where(TreeNode.parent_id == node.id)
                .order_by(TreeNode.order_idx, TreeNode.id)
            )
        )
        for child in children:
            self._refresh_subtree_paths(child, node.path, node.sort_path)

    def _next_order(self, parent_id: int) -> int:
        sibling_max = self._session.scalars(
            select(TreeNode.order_idx)
            .where(TreeNode.parent_id == parent_id)
            .order_by(TreeNode.order_idx.desc())
            .limit(1)
        ).first()
        return (sibling_max if sibling_max is not None else -ORDER_STEP) + ORDER_STEP

    def create_node(
        self,
        course_id: int,
        parent_id: int,
        title: str,
        summary: str | None = None,
        objectives: list[str] | None = None,
        ai_hint: str | None = None,
    ) -> TreeNode:
        title = title.strip()
        if not title:
            raise TreeError("node title is required")
        parent = self._session.get(TreeNode, parent_id)
        if parent is None or parent.course_id != course_id:
            raise TreeError("parent node not in this course")
        if parent.depth >= MAX_DEPTH:
            raise TreeError(f"nodes may nest at most {MAX_DEPTH} levels")
        node = TreeNode(
            course_id=course_id,
            parent_id=parent_id,
            title=title[:300],
            summary=summary,
            objectives=[o.strip() for o in (objectives or []) if o.strip()] or None,
            ai_hint=(ai_hint.strip() or None) if ai_hint else None,
            order_idx=self._next_order(parent_id),
            depth=parent.depth + 1,
            path="/",
            sort_path="/",
        )
        self._session.add(node)
        self._session.flush()
        self._refresh_subtree_paths(node, parent.path, parent.sort_path)
        return node

    def update_node(
        self,
        node_id: int,
        title: str | None = None,
        summary: str | None = None,
        objectives: list[str] | None = None,
        ai_hint: str | None = None,
    ) -> TreeNode:
        node = self.get(node_id)
        if node.is_root and (
            title is not None or summary is not None or objectives is not None
        ):
            raise TreeError("the course root cannot be edited here")
        if title is not None:
            title = title.strip()
            if not title:
                raise TreeError("node title is required")
            node.title = title[:300]
        if summary is not None:
            node.summary = summary
        if objectives is not None:
            node.objectives = [o.strip() for o in objectives if o.strip()] or None
        if ai_hint is not None:
            node.ai_hint = ai_hint.strip() or None
        self._session.flush()
        return node

    def _renumber_siblings(self, parent_id: int) -> list[TreeNode]:
        siblings = list(
            self._session.scalars(
                select(TreeNode)
                .where(TreeNode.parent_id == parent_id)
                .order_by(TreeNode.order_idx, TreeNode.id)
            )
        )
        for index, sibling in enumerate(siblings):
            sibling.order_idx = index * ORDER_STEP
        self._session.flush()
        return siblings

    def _rewrite_child_sorts(self, parent: TreeNode) -> None:
        for child in self._renumber_siblings(parent.id):
            self._refresh_subtree_paths(child, parent.path, parent.sort_path)

    def move_node(self, node_id: int, parent_id: int, position: int) -> TreeNode:
        node = self.get(node_id)
        if node.is_root:
            raise TreeError("the course root cannot be moved")
        parent = self._session.get(TreeNode, parent_id)
        if parent is None or parent.course_id != node.course_id:
            raise TreeError("target parent not in this course")
        if parent.id == node.id or parent.path.startswith(node.path):
            raise TreeError("cannot move a node into its own subtree")
        subtree_depth = self._subtree_depth(node)
        if parent.depth + subtree_depth > MAX_DEPTH:
            raise TreeError(f"nodes may nest at most {MAX_DEPTH} levels")
        old_parent_id = node.parent_id
        node.parent_id = parent_id
        node.depth = parent.depth + 1
        siblings = list(
            self._session.scalars(
                select(TreeNode)
                .where(TreeNode.parent_id == parent_id)
                .order_by(TreeNode.order_idx, TreeNode.id)
            )
        )
        siblings = [sibling for sibling in siblings if sibling.id != node.id]
        position = max(0, min(position, len(siblings)))
        siblings.insert(position, node)
        for index, sibling in enumerate(siblings):
            sibling.order_idx = index * ORDER_STEP
        self._session.flush()
        self._rewrite_child_sorts(parent)
        self._apply_depths(node, node.depth)
        if old_parent_id is not None and old_parent_id != parent_id:
            old_parent = self._session.get(TreeNode, old_parent_id)
            if old_parent is not None:
                self._rewrite_child_sorts(old_parent)
        return node

    def _subtree_depth(self, node: TreeNode) -> int:
        children = list(
            self._session.scalars(select(TreeNode).where(TreeNode.parent_id == node.id))
        )
        if not children:
            return 1
        return 1 + max(self._subtree_depth(child) for child in children)

    def _apply_depths(self, node: TreeNode, depth: int) -> None:
        for child in self._session.scalars(
            select(TreeNode).where(TreeNode.parent_id == node.id)
        ):
            child.depth = depth + 1
            self._apply_depths(child, child.depth)
        self._session.flush()

    def delete_node(self, node_id: int, snapshot: bool = False) -> str | None:
        node = self.get(node_id)
        if node.is_root:
            raise TreeError("the course root cannot be deleted")
        parent = self._session.get(TreeNode, node.parent_id)
        if parent is None:
            raise TreeError("node has no parent")
        token = self._capture_snapshot(node, parent) if snapshot else None
        children = list(
            self._session.scalars(
                select(TreeNode)
                .where(TreeNode.parent_id == node_id)
                .order_by(TreeNode.order_idx, TreeNode.id)
            )
        )
        for child in children:
            child.parent_id = parent.id
        self._session.flush()
        for child in children:
            self._apply_depths(child, parent.depth + 1)
        duplicate_links = self._session.scalars(
            select(MaterialLink.id).where(
                MaterialLink.node_id == node_id,
                MaterialLink.material_id.in_(
                    select(MaterialLink.material_id).where(
                        MaterialLink.node_id == parent.id
                    )
                ),
            )
        )
        for link_id in duplicate_links:
            self._session.delete(self._session.get(MaterialLink, link_id))
        duplicate_folder_links = self._session.scalars(
            select(MaterialFolderLink.id).where(
                MaterialFolderLink.node_id == node_id,
                MaterialFolderLink.folder_id.in_(
                    select(MaterialFolderLink.folder_id).where(
                        MaterialFolderLink.node_id == parent.id
                    )
                ),
            )
        )
        for link_id in duplicate_folder_links:
            self._session.delete(self._session.get(MaterialFolderLink, link_id))
        self._session.flush()
        for table in PLACEMENT_TABLES.values():
            self._session.execute(
                sa_update(table)
                .where(table.node_id == node_id)
                .values(node_id=parent.id)
            )
        self._session.delete(node)
        self._session.flush()
        self._rewrite_child_sorts(parent)
        return token

    def _capture_snapshot(self, node: TreeNode, parent: TreeNode) -> str:
        links = [
            {
                "material_id": link.material_id,
                "rationale": link.rationale,
                "auto_assigned": link.auto_assigned,
                "confidence": link.confidence,
            }
            for link in self._session.scalars(
                select(MaterialLink).where(MaterialLink.node_id == node.id)
            )
        ]
        folder_links = [
            {
                "folder_id": link.folder_id,
                "rationale": link.rationale,
                "auto_assigned": link.auto_assigned,
                "confidence": link.confidence,
            }
            for link in self._session.scalars(
                select(MaterialFolderLink).where(MaterialFolderLink.node_id == node.id)
            )
        ]
        concepts = list(
            self._session.scalars(
                select(NodeConcept.concept_id).where(NodeConcept.node_id == node.id)
            )
        )
        placements: dict[str, list[int]] = {}
        for key, model in PLACEMENT_TABLES.items():
            placements[key] = list(
                self._session.scalars(select(model.id).where(model.node_id == node.id))
            )
        child_ids = list(
            self._session.scalars(
                select(TreeNode.id)
                .where(TreeNode.parent_id == node.id)
                .order_by(TreeNode.order_idx, TreeNode.id)
            )
        )
        sibling_ids = list(
            self._session.scalars(
                select(TreeNode.id)
                .where(TreeNode.parent_id == parent.id)
                .order_by(TreeNode.order_idx, TreeNode.id)
            )
        )
        token = uuid4().hex
        _SNAPSHOTS[token] = {
            "course_id": node.course_id,
            "parent_id": parent.id,
            "title": node.title,
            "summary": node.summary,
            "objectives": node.objectives,
            "ai_hint": node.ai_hint,
            "sibling_index": sibling_ids.index(node.id),
            "children": child_ids,
            "links": links,
            "folder_links": folder_links,
            "concepts": concepts,
            "placements": placements,
            "created_at": time_monotonic(),
        }
        _prune_snapshots()
        return token

    def restore_node(self, token: str) -> int:
        _prune_snapshots()
        entry = _SNAPSHOTS.pop(token, None)
        if entry is None:
            raise TreeError("undo expired or unknown")
        parent = self._session.get(TreeNode, entry["parent_id"])
        if parent is None or parent.course_id != entry["course_id"]:
            raise TreeError("original parent is gone")
        node = self.create_node(
            entry["course_id"],
            parent.id,
            entry["title"],
            summary=entry["summary"],
            objectives=entry["objectives"],
            ai_hint=entry["ai_hint"],
        )
        sibling_ids = list(
            self._session.scalars(
                select(TreeNode.id)
                .where(TreeNode.parent_id == parent.id)
                .order_by(TreeNode.order_idx, TreeNode.id)
            )
        )
        sibling_ids.remove(node.id)
        position = min(entry["sibling_index"], len(sibling_ids))
        sibling_ids.insert(position, node.id)
        self.move_node(node.id, parent.id, position)
        for child_id in entry["children"]:
            child = self._session.get(TreeNode, child_id)
            if child is not None and child.course_id == entry["course_id"]:
                child_count = len(
                    list(
                        self._session.scalars(
                            select(TreeNode.id).where(TreeNode.parent_id == node.id)
                        )
                    )
                )
                self.move_node(child.id, node.id, child_count)
        for key, model in PLACEMENT_TABLES.items():
            ids = entry["placements"].get(key, [])
            if not ids:
                continue
            rows = self._session.scalars(
                select(model).where(model.id.in_(ids), model.node_id == parent.id)
            )
            for row in rows:
                row.node_id = node.id
        self._session.flush()
        existing_links = {
            link.material_id
            for link in self._session.scalars(
                select(MaterialLink).where(MaterialLink.node_id == node.id)
            )
        }
        for link in entry["links"]:
            if link["material_id"] in existing_links:
                continue
            material = self._session.get(Material, link["material_id"])
            if (
                material is not None
                and material.course_id == entry["course_id"]
                and material.status != "failed"
            ):
                self._session.add(
                    MaterialLink(
                        node_id=node.id,
                        material_id=link["material_id"],
                        course_id=entry["course_id"],
                        rationale=link["rationale"],
                        auto_assigned=link["auto_assigned"],
                        confidence=link["confidence"],
                    )
                )
        existing_folder_links = {
            link.folder_id
            for link in self._session.scalars(
                select(MaterialFolderLink).where(MaterialFolderLink.node_id == node.id)
            )
        }
        for link in entry["folder_links"]:
            if link["folder_id"] in existing_folder_links:
                continue
            folder = self._session.get(MaterialFolder, link["folder_id"])
            if folder is not None and folder.course_id == entry["course_id"]:
                self._session.add(
                    MaterialFolderLink(
                        node_id=node.id,
                        folder_id=link["folder_id"],
                        course_id=entry["course_id"],
                        rationale=link["rationale"],
                        auto_assigned=link["auto_assigned"],
                        confidence=link["confidence"],
                    )
                )
        existing_concepts = set(
            self._session.scalars(
                select(NodeConcept.concept_id).where(NodeConcept.node_id == node.id)
            )
        )
        for concept_id in entry["concepts"]:
            if concept_id in existing_concepts:
                continue
            concept = self._session.get(Concept, concept_id)
            if concept is not None and concept.course_id == entry["course_id"]:
                self._session.add(
                    NodeConcept(node_id=node.id, concept_id=concept_id)
                )
        self._session.flush()
        return node.id

    def subtree_ids(self, node: TreeNode, include_children: bool = True) -> list[int]:
        if not include_children:
            return [node.id]
        prefix = node.path
        rows = self._session.scalars(
            select(TreeNode.id).where(
                TreeNode.course_id == node.course_id,
                TreeNode.path.like(f"{prefix}%"),
            )
        )
        return list(rows)

    def scoped_node_ids(
        self, node_id: int, include_children: bool = True
    ) -> list[int]:
        node = self.get(node_id)
        return self.subtree_ids(node, include_children)

    def breadcrumb(self, node: TreeNode) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        current: TreeNode | None = node
        while current is not None:
            chain.append({"id": current.id, "title": current.title, "depth": current.depth})
            current = (
                self._session.get(TreeNode, current.parent_id)
                if current.parent_id is not None
                else None
            )
        chain.reverse()
        course = self._session.get(Course, node.course_id)
        if course is not None:
            chain[0] = {"id": chain[0]["id"], "title": course.title, "depth": 0}
        return chain

    def _direct_counts(
        self, node_ids: list[int], profile_id: int | None = None
    ) -> dict[int, dict[str, int]]:
        empty = {
            "materials": 0,
            "notes": 0,
            "quizzes": 0,
            "exercises": 0,
            "flashcards": 0,
            "studied": 0,
            "cards_due": 0,
        }
        result = {node_id: dict(empty) for node_id in node_ids}
        if not node_ids:
            return result
        for key, kind_filter in (
            ("materials", None),
            ("notes", None),
            ("quizzes", None),
            ("exercises", Exercise.kind.not_like("card_%")),
            ("flashcards", Exercise.kind.like("card_%")),
        ):
            if key == "materials":
                model: Any = MaterialLink
            elif key == "notes":
                model = Note
            elif key == "quizzes":
                model = Activity
            else:
                model = Exercise
            statement = select(model.node_id, func.count()).where(
                model.node_id.in_(node_ids)
            )
            if kind_filter is not None:
                statement = statement.where(kind_filter)
            rows = self._session.execute(statement.group_by(model.node_id)).all()
            for node_id, count in rows:
                result[node_id][key] = int(count)
        if profile_id is not None:
            studied = self._session.execute(
                select(MaterialLink.node_id, func.count())
                .join(
                    MaterialStudyState,
                    (MaterialStudyState.material_id == MaterialLink.material_id)
                    & (MaterialStudyState.profile_id == profile_id)
                    & (MaterialStudyState.status == "studied"),
                )
                .where(MaterialLink.node_id.in_(node_ids))
                .group_by(MaterialLink.node_id)
            ).all()
            for node_id, count in studied:
                result[node_id]["studied"] = int(count)
        folder_map = folder_links_by_node(self._session, node_ids)
        folder_link_nodes = [node_id for node_id, links in folder_map.items() if links]
        if folder_link_nodes:
            resolved_materials = self._resolved_material_ids(folder_link_nodes)
            studied_ids: set[int] | None = None
            if profile_id is not None:
                studied_ids = set(
                    self._session.scalars(
                        select(MaterialStudyState.material_id).where(
                            MaterialStudyState.profile_id == profile_id,
                            MaterialStudyState.status == "studied",
                        )
                    )
                )
            for node_id in folder_link_nodes:
                ids = resolved_materials[node_id]
                result[node_id]["materials"] = len(ids)
                if studied_ids is not None:
                    result[node_id]["studied"] = len(ids & studied_ids)
        now = utcnow()
        due = self._session.execute(
            select(Exercise.node_id, func.count())
            .outerjoin(FsrsState, FsrsState.card_id == Exercise.id)
            .where(
                Exercise.node_id.in_(node_ids),
                Exercise.kind.like("card_%"),
                or_(
                    FsrsState.due_at.is_(None),
                    FsrsState.due_at <= now,
                ),
            )
            .group_by(Exercise.node_id)
        ).all()
        for node_id, count in due:
            result[node_id]["cards_due"] = int(count)
        return result

    def _resolved_material_ids(self, node_ids: list[int]) -> dict[int, set[int]]:
        result: dict[int, set[int]] = {node_id: set() for node_id in node_ids}
        rows = self._session.execute(
            select(MaterialLink.node_id, MaterialLink.material_id).where(
                MaterialLink.node_id.in_(node_ids)
            )
        ).all()
        for node_id, material_id in rows:
            result[node_id].add(material_id)
        for node_id, links in folder_links_by_node(self._session, node_ids).items():
            for link in links:
                folder = self._session.get(MaterialFolder, link.folder_id)
                if folder is not None:
                    result[node_id] |= folder_member_ids(self._session, folder)
        return result

    def tree(self, course_id: int, profile_id: int | None = None) -> list[dict[str, Any]]:
        root = self.ensure_root(course_id)
        nodes = list(
            self._session.scalars(
                select(TreeNode)
                .where(TreeNode.course_id == course_id)
                .order_by(TreeNode.sort_path)
            )
        )
        links = list(
            self._session.scalars(
                select(MaterialLink).where(
                    MaterialLink.course_id == course_id,
                    MaterialLink.node_id.in_([node.id for node in nodes]),
                )
            )
        )
        materials = {
            material.id: material
            for material in self._session.scalars(
                select(Material).where(
                    Material.id.in_([link.material_id for link in links])
                )
            )
        }
        by_parent: dict[int, list[TreeNode]] = {}
        for node in nodes:
            parent_id = node.parent_id
            if parent_id is not None:
                by_parent.setdefault(parent_id, []).append(node)
        link_by_node: dict[int, list[MaterialLink]] = {}
        for link in links:
            link_by_node.setdefault(link.node_id, []).append(link)
        folder_links = list(
            self._session.scalars(
                select(MaterialFolderLink).where(
                    MaterialFolderLink.course_id == course_id
                )
            )
        )
        folders = {
            folder.id: folder
            for folder in self._session.scalars(
                select(MaterialFolder).where(
                    MaterialFolder.id.in_([link.folder_id for link in folder_links])
                )
            )
        } if folder_links else {}
        folder_link_by_node: dict[int, list[dict[str, Any]]] = {}
        for folder_link in folder_links:
            folder = folders.get(folder_link.folder_id)
            if folder is None:
                continue
            folder_link_by_node.setdefault(folder_link.node_id, []).append(
                {
                    "folder_id": folder.id,
                    "name": folder.name,
                    "source_id": folder.source_id,
                }
            )
        counts_by_node = self._direct_counts([node.id for node in nodes], profile_id)

        def node_entry(node: TreeNode) -> dict[str, Any]:
            return {
                "id": node.id,
                "title": node.title,
                "summary": node.summary,
                "objectives": node.objectives or [],
                "ai_hint": node.ai_hint,
                "order_idx": node.order_idx,
                "depth": node.depth,
                "is_root": node.is_root,
                "children": [node_entry(child) for child in by_parent.get(node.id, [])],
                "counts": counts_by_node[node.id],
                "folder_links": folder_link_by_node.get(node.id, []),
                "materials": [
                    {
                        "material_id": link.material_id,
                        "title": (
                            materials[link.material_id].title
                            if link.material_id in materials
                            else f"#{link.material_id}"
                        ),
                        "rationale": link.rationale,
                        "auto_assigned": link.auto_assigned,
                        "confidence": link.confidence,
                    }
                    for link in link_by_node.get(node.id, [])
                ],
            }

        return [node_entry(root)]

    def node_with_children(self, node: TreeNode) -> list[dict[str, Any]]:
        children = list(
            self._session.scalars(
                select(TreeNode)
                .where(TreeNode.parent_id == node.id)
                .order_by(TreeNode.order_idx, TreeNode.id)
            )
        )
        result: list[dict[str, Any]] = []
        for child in children:
            result.append(
                {
                    "id": child.id,
                    "title": child.title,
                    "depth": child.depth,
                    "order_idx": child.order_idx,
                    "objectives": child.objectives or [],
                    "summary": child.summary,
                }
            )
        return result

    def workspace(self, node_id: int, profile_id: int) -> dict[str, Any]:
        node = self.get(node_id)
        course = self._session.get(Course, node.course_id)
        scope_ids = self.subtree_ids(node)
        children_payload = self.node_with_children(node)
        child_ids = [entry["id"] for entry in children_payload]
        links = list(
            self._session.scalars(
                select(MaterialLink).where(
                    MaterialLink.course_id == node.course_id,
                    MaterialLink.node_id.in_(scope_ids),
                )
            )
        )
        folder_links_map = folder_links_by_node(self._session, scope_ids)
        all_folder_ids = [
            link.folder_id
            for folder_links in folder_links_map.values()
            for link in folder_links
        ]
        folders = (
            {
                folder.id: folder
                for folder in self._session.scalars(
                    select(MaterialFolder).where(
                        MaterialFolder.id.in_(all_folder_ids)
                    )
                )
            }
            if all_folder_ids
            else {}
        )
        via_by_node: dict[int, dict[int, MaterialFolder]] = {}
        member_ids: set[int] = set()
        for scope_node_id, folder_links in folder_links_map.items():
            via = via_by_node.setdefault(scope_node_id, {})
            for folder_link in folder_links:
                folder = folders.get(folder_link.folder_id)
                if folder is None:
                    continue
                for member_id in folder_member_ids(self._session, folder):
                    via.setdefault(member_id, folder)
                    member_ids.add(member_id)
        relevant_material_ids = {link.material_id for link in links} | member_ids
        materials = {
            material.id: material
            for material in self._session.scalars(
                select(Material).where(Material.id.in_(relevant_material_ids))
            )
        }
        states = {
            state.material_id: state
            for state in self._session.scalars(
                select(MaterialStudyState).where(
                    MaterialStudyState.profile_id == profile_id,
                    MaterialStudyState.material_id.in_(relevant_material_ids),
                )
            )
        }

        node_folder_links = folder_links_by_node(self._session, [node.id])[node.id]
        node_folder_ids = [link.folder_id for link in node_folder_links]

        def material_entry(
            material_id: int,
            link: MaterialLink | None = None,
            via: MaterialFolder | None = None,
        ) -> dict[str, Any]:
            material = materials.get(material_id)
            state = states.get(material_id)
            return {
                "material_id": material_id,
                "title": material.title if material else f"#{material_id}",
                "kind": material.kind if material else "doc",
                "status": material.status if material else "missing",
                "read_status": state.status if state else "unread",
                "progress": state.progress if state else 0.0,
                "rationale": link.rationale if link is not None else None,
                "auto_assigned": link.auto_assigned if link is not None else None,
                "confidence": link.confidence if link is not None else None,
                "provenance": material.provenance if material else None,
                "via_folder_id": via.id if via is not None else None,
                "via_folder_name": via.name if via is not None else None,
            }

        def node_material_entries(node_id: int) -> list[dict[str, Any]]:
            direct = [link for link in links if link.node_id == node_id]
            direct_ids = {link.material_id for link in direct}
            entries = [
                material_entry(link.material_id, link=link) for link in direct
            ]
            via = via_by_node.get(node_id, {})
            for material_id in sorted(via):
                if material_id in direct_ids:
                    continue
                entries.append(material_entry(material_id, via=via[material_id]))
            return entries

        def folder_entry(folder_id: int) -> dict[str, Any]:
            folder = folders.get(folder_id)
            link = next(
                (
                    candidate
                    for candidate in node_folder_links
                    if candidate.folder_id == folder_id
                ),
                None,
            )
            if folder is None:
                return {
                    "folder_id": folder_id,
                    "name": f"#{folder_id}",
                    "source_id": None,
                    "member_count": 0,
                    "rationale": link.rationale if link is not None else None,
                    "auto_assigned": link.auto_assigned if link is not None else False,
                }
            return {
                "folder_id": folder.id,
                "name": folder.name,
                "source_id": folder.source_id,
                "member_count": len(folder_member_ids(self._session, folder)),
                "rationale": link.rationale if link is not None else None,
                "auto_assigned": link.auto_assigned if link is not None else False,
            }

        notes = list(
            self._session.scalars(
                select(Note)
                .where(
                    Note.course_id == node.course_id,
                    Note.node_id.in_(scope_ids),
                )
                .order_by(Note.pinned.desc(), Note.updated_at.desc())
                .limit(50)
            )
        )
        material_owned = list(
            self._session.scalars(
                select(Note)
                .where(
                    Note.course_id == node.course_id,
                    Note.owner_type == "material",
                    Note.owner_id.in_(relevant_material_ids),
                )
                .order_by(Note.pinned.desc(), Note.updated_at.desc())
                .limit(50)
            )
        )
        counts = self._scoped_counts(node.course_id, scope_ids, node.id)
        concepts = list(
            self._session.execute(
                select(NodeConcept, Concept)
                .join(Concept, Concept.id == NodeConcept.concept_id)
                .where(
                    NodeConcept.node_id.in_(scope_ids),
                    Concept.course_id == node.course_id,
                )
                .order_by(Concept.name)
            ).all()
        )
        concept_entries = [
            {
                "id": concept.id,
                "name": concept.name,
                "direct": node_concept.node_id == node.id,
                "node_ids": [node_concept.node_id],
            }
            for node_concept, concept in concepts
        ]
        merged: dict[int, dict[str, Any]] = {}
        for entry in concept_entries:
            existing = merged.get(entry["id"])
            if existing is None:
                merged[entry["id"]] = entry
            else:
                existing["node_ids"].extend(entry["node_ids"])
                existing["direct"] = existing["direct"] or entry["direct"]
        return {
            "node": {
                "id": node.id,
                "course_id": node.course_id,
                "course_title": course.title if course else None,
                "title": node.title,
                "summary": node.summary,
                "objectives": node.objectives or [],
                "ai_hint": node.ai_hint,
                "depth": node.depth,
                "is_root": node.is_root,
                "parent_id": node.parent_id,
                "breadcrumb": self.breadcrumb(node),
            },
            "children": children_payload,
            "folders": [folder_entry(folder_id) for folder_id in node_folder_ids],
            "materials": [
                material_entry(link.material_id, link=link)
                for link in links
                if link.node_id == node.id
            ],
            "folder_material_ids": sorted(via_by_node.get(node.id, {})),
            "child_materials": {
                str(child_id): node_material_entries(child_id)
                for child_id in child_ids
            },
            "notes": [
                {
                    "id": note.id,
                    "title": note.title,
                    "node_id": note.node_id,
                    "owner_type": note.owner_type,
                    "owner_id": note.owner_id,
                    "pinned": note.pinned,
                    "updated_at": note.updated_at.isoformat() if note.updated_at else None,
                }
                for note in notes + material_owned
            ],
            "counts": counts,
            "concepts": list(merged.values()),
        }

    def _scoped_counts(
        self, course_id: int, scope_ids: list[int], own_node_id: int
    ) -> dict[str, Any]:
        child_ids = [node_id for node_id in scope_ids if node_id != own_node_id]

        def counts(model: type[Any], kind_filter: Any = None) -> dict[str, int]:
            direct_statement = select(model.id).where(model.node_id == own_node_id)
            total_statement = select(model.id).where(model.node_id.in_(scope_ids))
            if kind_filter is not None:
                direct_statement = direct_statement.where(kind_filter)
                total_statement = total_statement.where(kind_filter)
            direct = len(list(self._session.scalars(direct_statement)))
            total = len(list(self._session.scalars(total_statement)))
            return {"direct": direct, "with_children": total}

        return {
            "notes": counts(Note),
            "quizzes": counts(Activity),
            "exercises": counts(Exercise, Exercise.kind.not_like("card_%")),
            "flashcards": counts(Exercise, Exercise.kind.like("card_%")),
            "child_nodes": len(child_ids),
        }
