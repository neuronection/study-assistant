import json
import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...ai.gateway import LLMGateway, Message
from ...core.vocab import CourseOrigin, StudyStatus
from ...domain.models import (
    Activity,
    Answer,
    Attempt,
    ChatMessage,
    ChatProposal,
    ChatSession,
    Concept,
    ConceptLink,
    Course,
    CourseDefaultTaskAssignment,
    CourseTaskAssignment,
    Exercise,
    ItemStat,
    Material,
    MaterialFolder,
    MaterialFolderLink,
    MaterialGroup,
    MaterialIndexCard,
    MaterialLink,
    MaterialSource,
    MaterialStudyState,
    MaterialSuggestion,
    Mistake,
    NodeConcept,
    Note,
    PlanItem,
    Profile,
    Question,
    QuizHelpEvent,
    ReviewLog,
    StudySession,
    TreeNode,
    utcnow,
)
from ...jobs.cancellation import cancel_jobs_for
from ..content.folders import (
    folder_links_by_node,
    folder_member_ids,
    subtree_folder_ids,
)
from ..content.materials import purge_material
from .tree import MAX_DEPTH, TreeService

OUTLINE_TASK = "outline"

MAX_CHAPTERS = 30
MAX_SECTIONS_PER_CHAPTER = 15

GENESIS_TASK_CAP_DEFAULT = 60

GENESIS_LEVELS = ("school", "university-intro", "university-advanced")

GENESIS_SYSTEM_PROMPT = (
    "You are a curriculum designer. Given a topic (and optionally a level), design a"
    " study course a student can start from immediately — no pre-existing material.\n"
    "Respond with ONLY a JSON object:\n"
    "{\n"
    '  "title": str,\n'
    '  "description": str,\n'
    '  "subject": str,\n'
    '  "level": str,\n'
    '  "goals": [str],\n'
    '  "chapters": [\n'
    "    {\n"
    '      "title": str,\n'
    '      "summary": str,\n'
    '      "sections": [\n'
    "        {\n"
    '          "title": str,\n'
    '          "objectives": [str]\n'
    "        }\n"
    "      ]\n"
    "    }\n"
    "  ]\n"
    "}\n"
    "Rules:\n"
    "- 3 to 8 chapters; each chapter 2 to 6 sections; exactly two levels (no deeper).\n"
    "- Every section carries 1-3 one-line learning objectives.\n"
    "- Order chapters pedagogically (foundations first).\n"
    "- Teach from standard model knowledge; no citations."
)

GENESIS_SKILL_KEY = "course.genesis"

OUTLINE_SYSTEM_PROMPT = (
    "You are a course designer. Given a list of study materials (id, title, topics), "
    "design a course outline.\n"
    "Respond with ONLY a JSON object:\n"
    "{\n"
    '  "chapters": [\n'
    "    {\n"
    '      "title": str,\n'
    '      "summary": str,\n'
    '      "sections": [\n'
    "        {\n"
    '          "title": str,\n'
    '          "objectives": [str],\n'
    '          "material_ids": [int],\n'
    '          "rationale": str,\n'
    '          "confidence": float (0-1)\n'
    "        }\n"
    "      ]\n"
    "    }\n"
    "  ]\n"
    "}\n"
    "Rules: 3-12 chapters, logical progression, every material id may be used at most "
    "once, do not invent material ids, sections are leaf units."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

SCRATCHPAD_TITLE = "Scratchpad"


def ensure_scratch_course(session: Session, profile_id: int) -> Course:
    course = session.scalars(
        select(Course).where(
            Course.profile_id == profile_id,
            Course.origin == CourseOrigin.SCRATCH.value,
        )
    ).first()
    if course is not None:
        return course
    course = Course(
        profile_id=profile_id,
        title=SCRATCHPAD_TITLE,
        origin=CourseOrigin.SCRATCH.value,
        hidden=True,
    )
    session.add(course)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        seeded = session.scalars(
            select(Course).where(
                Course.profile_id == profile_id,
                Course.origin == CourseOrigin.SCRATCH.value,
            )
        ).first()
        assert seeded is not None
        return seeded
    TreeService(session).ensure_root(course.id)
    session.flush()
    return course


def scratch_content_count(session: Session, course: Course) -> int:
    notes = len(
        session.scalars(select(Note.id).where(Note.course_id == course.id)).all()
    )
    materials = len(
        session.scalars(
            select(Material.id).where(Material.course_id == course.id)
        ).all()
    )
    sessions = len(
        session.scalars(
            select(ChatSession.id).where(ChatSession.course_id == course.id)
        ).all()
    )
    return notes + materials + sessions


class CourseError(ValueError):
    pass


class OutlineService:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def draft(
        self,
        course: Course,
        materials: list[Material],
        cards: dict[int, MaterialIndexCard],
    ) -> dict[str, Any]:
        if not materials:
            raise CourseError("course has no materials to outline")
        material_lines = []
        for material in materials:
            card = cards.get(material.id)
            topics = f" — topics: {', '.join(card.topics or [])}" if card and card.topics else ""
            summary = f" — {card.summary}" if card and card.summary else ""
            material_lines.append(f"- id={material.id}: {material.title}{topics}{summary}")
        prompt = (
            f"Course: {course.title}\n"
            f"Subject: {course.subject or 'unspecified'}\n\n"
            "Materials:\n" + "\n".join(material_lines)
        )
        text = self._gateway.generate(
            OUTLINE_TASK,
            [
                Message(role="system", content=OUTLINE_SYSTEM_PROMPT),
                Message(role="user", content=prompt),
            ],
            course_id=course.id,
        )
        match = _JSON_RE.search(text)
        if match is None:
            raise CourseError("outline model returned no JSON")
        try:
            parsed = json.loads(match.group(0))
        except ValueError as error:
            raise CourseError("outline model returned invalid JSON") from error
        return _validate_draft(parsed, materials)

    def draft_genesis(
        self,
        *,
        profile_id: int,
        topic: str,
        level: str | None = None,
        sources_block: str | None = None,
    ) -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            raise CourseError("topic is required")
        if level is not None and level not in GENESIS_LEVELS:
            raise CourseError(f"level must be one of {list(GENESIS_LEVELS)}")
        lines = [f"Topic: {topic}"]
        if level is not None:
            lines.append(f"Level: {level}")
        if sources_block:
            lines.append(
                "Web sources found for this topic — ground the outline in them "
                "where they are relevant:\n" + sources_block
            )
        text = self._gateway.generate(
            OUTLINE_TASK,
            [
                Message(role="system", content=GENESIS_SYSTEM_PROMPT),
                Message(role="user", content="\n".join(lines)),
            ],
        )
        match = _JSON_RE.search(text)
        if match is None:
            raise CourseError("genesis model returned no JSON")
        try:
            parsed = json.loads(match.group(0))
        except ValueError as error:
            raise CourseError("genesis model returned invalid JSON") from error
        return _validate_genesis_draft(parsed)


def _validate_genesis_draft(draft: Any) -> dict[str, Any]:
    if not isinstance(draft, dict) or not isinstance(draft.get("chapters"), list):
        raise CourseError("genesis draft missing 'chapters' list")
    title = str(draft.get("title", "")).strip()
    if not title:
        raise CourseError("genesis draft missing title")
    chapters_out: list[dict[str, Any]] = []
    for chapter in draft["chapters"][:MAX_CHAPTERS]:
        if not isinstance(chapter, dict):
            continue
        chapter_title = str(chapter.get("title", "")).strip()
        if not chapter_title:
            continue
        sections_out: list[dict[str, Any]] = []
        for section in (chapter.get("sections") or [])[:MAX_SECTIONS_PER_CHAPTER]:
            if not isinstance(section, dict):
                continue
            section_title = str(section.get("title", "")).strip()
            if not section_title:
                continue
            objectives = [
                str(objective).strip()
                for objective in (section.get("objectives") or [])[:3]
                if str(objective).strip()
            ]
            sections_out.append(
                {"title": section_title[:300], "objectives": objectives}
            )
        chapters_out.append(
            {
                "title": chapter_title[:300],
                "summary": str(chapter.get("summary", "")).strip()[:2000] or None,
                "sections": sections_out,
            }
        )
    if not chapters_out:
        raise CourseError("genesis draft has no usable chapters")
    goals = [
        str(goal).strip() for goal in (draft.get("goals") or [])[:8] if str(goal).strip()
    ]
    level = draft.get("level")
    return {
        "title": title[:300],
        "description": str(draft.get("description", "")).strip()[:4000] or None,
        "subject": str(draft.get("subject", "")).strip()[:120] or None,
        "level": (str(level).strip()[:120] if level else None),
        "goals": goals,
        "chapters": chapters_out,
    }


def genesis_depth1_nodes(session: Session, course: Course) -> list[TreeNode]:
    root = session.scalars(
        select(TreeNode).where(
            TreeNode.course_id == course.id, TreeNode.is_root.is_(True)
        )
    ).first()
    if root is None:
        return []
    return list(
        session.scalars(
            select(TreeNode)
            .where(TreeNode.course_id == course.id, TreeNode.parent_id == root.id)
            .order_by(TreeNode.order_idx, TreeNode.id)
        )
    )


def genesis_task_estimate(
    node_count: int, *, lessons: bool, quizzes: bool, flashcards: bool
) -> int:
    return node_count * sum((lessons, quizzes, flashcards))


def genesis_task_cap(session: Session, profile_id: int) -> int:
    profile = session.get(Profile, profile_id)
    preferences = profile.preferences if profile is not None else None
    if isinstance(preferences, dict):
        raw = preferences.get("genesis_task_cap")
        try:
            cap = int(raw) if raw is not None else GENESIS_TASK_CAP_DEFAULT
        except (TypeError, ValueError):
            cap = GENESIS_TASK_CAP_DEFAULT
        return max(1, min(cap, 500))
    return GENESIS_TASK_CAP_DEFAULT


def commit_genesis(
    session: Session,
    *,
    profile_id: int,
    draft: dict[str, Any],
    lessons: bool = True,
    quizzes: bool = False,
    flashcards: bool = False,
    sources: list[str] | None = None,
) -> tuple[Course, int]:
    draft = _validate_genesis_draft(draft)
    description = draft["description"]
    clean_sources = [
        url.strip() for url in (sources or []) if url.strip()
    ][:8]
    if clean_sources:
        footer = "Drafted with sources: " + " ".join(clean_sources)
        description = f"{description}\n\n{footer}" if description else footer
    course = Course(
        profile_id=profile_id,
        title=draft["title"],
        description=description,
        subject=draft["subject"],
        level=draft["level"],
        goals=draft["goals"] or None,
        origin=CourseOrigin.GENESIS.value,
    )
    session.add(course)
    session.flush()
    tree = TreeService(session)
    root = tree.ensure_root(course.id)
    root.summary = description
    for chapter in draft["chapters"]:
        chapter_node = tree.create_node(
            course.id,
            root.id,
            chapter["title"],
            summary=chapter["summary"],
            ai_hint=chapter["summary"],
        )
        for section in chapter["sections"]:
            hint = "; ".join(section["objectives"]) or None
            tree.create_node(
                course.id,
                chapter_node.id,
                section["title"],
                ai_hint=hint,
            )
    session.flush()
    estimate = genesis_task_estimate(
        len(genesis_depth1_nodes(session, course)),
        lessons=lessons,
        quizzes=quizzes,
        flashcards=flashcards,
    )
    cap = genesis_task_cap(session, profile_id)
    if estimate > cap:
        raise CourseError(
            f"generation plan needs {estimate} tasks — over the budget cap of {cap}; "
            "deselect some options or raise the cap in Settings"
        )
    return course, estimate


def _validate_draft(
    draft: Any, materials: list[Material]
) -> dict[str, Any]:
    if not isinstance(draft, dict) or not isinstance(draft.get("chapters"), list):
        raise CourseError("outline draft missing 'chapters' list")
    known_ids = {material.id for material in materials}
    used_ids: set[int] = set()
    chapters_out: list[dict[str, Any]] = []
    for chapter in draft["chapters"][:MAX_CHAPTERS]:
        if not isinstance(chapter, dict):
            continue
        title = str(chapter.get("title", "")).strip()
        if not title:
            continue
        sections_out: list[dict[str, Any]] = []
        for section in (chapter.get("sections") or [])[:MAX_SECTIONS_PER_CHAPTER]:
            if not isinstance(section, dict):
                continue
            section_title = str(section.get("title", "")).strip()
            if not section_title:
                continue
            material_ids: list[int] = []
            for raw_id in section.get("material_ids") or []:
                try:
                    material_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if material_id in known_ids and material_id not in used_ids:
                    used_ids.add(material_id)
                    material_ids.append(material_id)
            objectives = [
                str(objective).strip()
                for objective in (section.get("objectives") or [])
                if str(objective).strip()
            ][:8]
            confidence = section.get("confidence")
            try:
                confidence_value = max(0.0, min(1.0, float(confidence or 0.5)))
            except (TypeError, ValueError):
                confidence_value = 0.5
            sections_out.append(
                {
                    "title": section_title,
                    "objectives": objectives,
                    "material_ids": material_ids,
                    "rationale": str(section.get("rationale", "")).strip()[:2000] or None,
                    "confidence": confidence_value,
                }
            )
        chapters_out.append(
            {
                "title": title,
                "summary": str(chapter.get("summary", "")).strip()[:2000] or None,
                "sections": sections_out,
            }
        )
    if not chapters_out:
        raise CourseError("outline draft contained no valid chapters")
    return {"chapters": chapters_out}


class StructureService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._tree = TreeService(session)

    def assign(
        self,
        node_id: int,
        material_id: int,
        rationale: str | None = None,
        auto_assigned: bool = False,
        confidence: float | None = None,
    ) -> MaterialLink:
        node = self._session.get(TreeNode, node_id)
        if node is None:
            raise CourseError("node not found")
        material = self._session.get(Material, material_id)
        if material is None:
            raise CourseError("material not found")
        if material.course_id != node.course_id:
            raise CourseError("material not in this course")
        existing = self._session.scalars(
            select(MaterialLink).where(
                MaterialLink.node_id == node_id,
                MaterialLink.material_id == material_id,
            )
        ).first()
        if existing is not None:
            existing.rationale = rationale
            existing.auto_assigned = auto_assigned
            existing.confidence = confidence
            self._session.flush()
            return existing
        link = MaterialLink(
            course_id=node.course_id,
            node_id=node_id,
            material_id=material_id,
            rationale=rationale,
            auto_assigned=auto_assigned,
            confidence=confidence,
        )
        self._session.add(link)
        self._session.flush()
        return link

    def unassign(self, node_id: int, material_id: int) -> bool:
        existing = self._session.scalars(
            select(MaterialLink).where(
                MaterialLink.node_id == node_id,
                MaterialLink.material_id == material_id,
            )
        ).first()
        if existing is not None:
            self._session.delete(existing)
            self._session.flush()
            return True
        for folder_link in folder_links_by_node(self._session, [node_id])[node_id]:
            folder = self._session.get(MaterialFolder, folder_link.folder_id)
            if folder is None:
                continue
            if material_id in folder_member_ids(self._session, folder):
                raise CourseError(
                    f"material is assigned via folder '{folder.name}' — unassign "
                    "the folder or move the file out of it"
                )
        return False

    def assign_folder(
        self,
        node_id: int,
        folder_id: int,
        rationale: str | None = None,
        auto_assigned: bool = False,
        confidence: float | None = None,
    ) -> MaterialFolderLink:
        node = self._session.get(TreeNode, node_id)
        if node is None:
            raise CourseError("node not found")
        folder = self._session.get(MaterialFolder, folder_id)
        if folder is None:
            raise CourseError("folder not found")
        if folder.course_id != node.course_id:
            raise CourseError("folder not in this course")
        existing = self._session.scalars(
            select(MaterialFolderLink).where(
                MaterialFolderLink.node_id == node_id,
                MaterialFolderLink.folder_id == folder_id,
            )
        ).first()
        if existing is not None:
            existing.rationale = rationale
            existing.auto_assigned = auto_assigned
            existing.confidence = confidence
            self._session.flush()
            return existing
        link = MaterialFolderLink(
            course_id=node.course_id,
            node_id=node_id,
            folder_id=folder_id,
            rationale=rationale,
            auto_assigned=auto_assigned,
            confidence=confidence,
        )
        self._session.add(link)
        self._session.flush()
        return link

    def mirror_folder(
        self,
        node_id: int,
        folder_id: int,
        *,
        recursive: bool = True,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        node = self._session.get(TreeNode, node_id)
        if node is None:
            raise CourseError("node not found")
        folder = self._session.get(MaterialFolder, folder_id)
        if folder is None or folder.course_id != node.course_id:
            raise CourseError("folder not in this course")
        created = 0
        reused = 0
        folder_links = 0
        skipped: list[str] = []

        def child_folders(parent_id: int) -> list[MaterialFolder]:
            return list(
                self._session.scalars(
                    select(MaterialFolder)
                    .where(MaterialFolder.parent_id == parent_id)
                    .order_by(MaterialFolder.name)
                )
            )

        def existing_child_titles(parent_node_id: int) -> dict[str, int]:
            titles: dict[str, int] = {}
            for child in self._session.scalars(
                select(TreeNode).where(TreeNode.parent_id == parent_node_id)
            ):
                titles.setdefault(child.title.casefold(), child.id)
            return titles

        def mirror(parent_folder_id: int, parent_node_id: int) -> None:
            nonlocal created, reused, folder_links
            for child in child_folders(parent_folder_id):
                if node_depth(parent_node_id) >= MAX_DEPTH:
                    skipped.append(child.path)
                    continue
                titles = existing_child_titles(parent_node_id)
                existing_id = titles.get(child.name.casefold())
                if existing_id is None:
                    created_node = self._tree.create_node(
                        node.course_id,
                        parent_node_id,
                        child.name,
                    )
                    created += 1
                    child_node_id = created_node.id
                else:
                    reused += 1
                    child_node_id = existing_id
                self.assign_folder(child_node_id, child.id, rationale=rationale)
                folder_links += 1
                if recursive:
                    mirror(child.id, child_node_id)

        def node_depth(n: int) -> int:
            found = self._session.get(TreeNode, n)
            assert found is not None
            return found.depth

        self.assign_folder(node_id, folder_id, rationale=rationale)
        folder_links += 1
        if recursive:
            mirror(folder_id, node_id)
        self._session.flush()
        return {
            "created_nodes": created,
            "reused_nodes": reused,
            "folder_links": folder_links,
            "skipped_folders": skipped[:20],
        }

    def unassign_folder(self, node_id: int, folder_id: int) -> bool:
        existing = self._session.scalars(
            select(MaterialFolderLink).where(
                MaterialFolderLink.node_id == node_id,
                MaterialFolderLink.folder_id == folder_id,
            )
        ).first()
        if existing is None:
            return False
        self._session.delete(existing)
        self._session.flush()
        return True

    def course_materials(self, course_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            select(MaterialLink, Material, TreeNode)
            .join(Material, MaterialLink.material_id == Material.id)
            .join(TreeNode, MaterialLink.node_id == TreeNode.id)
            .where(MaterialLink.course_id == course_id)
            .order_by(TreeNode.sort_path, MaterialLink.id)
        ).all()
        entries: list[dict[str, Any]] = []
        sort_keys: list[tuple[str, int]] = []
        seen: set[tuple[int, int]] = set()
        for index, (link, material, node) in enumerate(rows):
            seen.add((link.node_id, material.id))
            entries.append(
                {
                    "node_id": link.node_id,
                    "node_title": node.title,
                    "node_is_root": node.is_root,
                    "material_id": material.id,
                    "title": material.title,
                    "rationale": link.rationale,
                    "auto_assigned": link.auto_assigned,
                    "confidence": link.confidence,
                    "via_folder": None,
                }
            )
            sort_keys.append((node.sort_path, index))
        folder_links = self._session.execute(
            select(MaterialFolderLink, TreeNode)
            .join(TreeNode, MaterialFolderLink.node_id == TreeNode.id)
            .where(MaterialFolderLink.course_id == course_id)
            .order_by(TreeNode.sort_path, MaterialFolderLink.id)
        ).all()
        index = len(entries)
        for folder_link, node in folder_links:
            folder = self._session.get(MaterialFolder, folder_link.folder_id)
            if folder is None:
                continue
            members = sorted(folder_member_ids(self._session, folder))
            if not members:
                continue
            materials = {
                material.id: material
                for material in self._session.scalars(
                    select(Material).where(Material.id.in_(members))
                )
            }
            for material_id in members:
                if (folder_link.node_id, material_id) in seen:
                    continue
                material = materials.get(material_id)
                if material is None:
                    continue
                entries.append(
                    {
                        "node_id": folder_link.node_id,
                        "node_title": node.title,
                        "node_is_root": node.is_root,
                        "material_id": material_id,
                        "title": material.title,
                        "rationale": folder_link.rationale,
                        "auto_assigned": folder_link.auto_assigned,
                        "confidence": None,
                        "via_folder": {"id": folder.id, "name": folder.name},
                    }
                )
                sort_keys.append((node.sort_path, index))
                index += 1
        ordered = [
            entry
            for _, entry in sorted(
                zip(sort_keys, entries, strict=True), key=lambda pair: pair[0]
            )
        ]
        return ordered

    def material_links(self, material_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            select(MaterialLink, TreeNode, Course)
            .join(TreeNode, MaterialLink.node_id == TreeNode.id)
            .join(Course, MaterialLink.course_id == Course.id)
            .where(MaterialLink.material_id == material_id)
            .order_by(TreeNode.sort_path)
        ).all()
        breadcrumb_tail: dict[int, list[dict[str, Any]]] = {}
        for _link, node, _course in rows:
            breadcrumb_tail[node.id] = [
                {"id": entry["id"], "title": entry["title"]}
                for entry in self._tree.breadcrumb(node)
            ]
        entries: list[dict[str, Any]] = [
            {
                "node_id": link.node_id,
                "owner_title": node.title,
                "breadcrumb": breadcrumb_tail[node.id],
                "is_course_level": node.is_root,
                "course_id": course.id,
                "course_title": course.title,
                "auto_assigned": link.auto_assigned,
                "rationale": link.rationale,
                "via_folder": None,
            }
            for link, node, course in rows
        ]
        folder_rows = self._session.execute(
            select(MaterialFolderLink, TreeNode, Course, MaterialFolder)
            .join(TreeNode, MaterialFolderLink.node_id == TreeNode.id)
            .join(Course, MaterialFolderLink.course_id == Course.id)
            .join(MaterialFolder, MaterialFolderLink.folder_id == MaterialFolder.id)
            .order_by(TreeNode.sort_path)
        ).all()
        for folder_link, node, course, folder in folder_rows:
            if material_id not in folder_member_ids(self._session, folder):
                continue
            entries.append(
                {
                    "node_id": folder_link.node_id,
                    "owner_title": node.title,
                    "breadcrumb": [
                        {"id": entry["id"], "title": entry["title"]}
                        for entry in self._tree.breadcrumb(node)
                    ],
                    "is_course_level": node.is_root,
                    "course_id": course.id,
                    "course_title": course.title,
                    "auto_assigned": folder_link.auto_assigned,
                    "rationale": folder_link.rationale,
                    "via_folder": {"id": folder.id, "name": folder.name},
                }
            )
        return entries

    def folder_links(self, folder_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            select(MaterialFolderLink, TreeNode, Course)
            .join(TreeNode, MaterialFolderLink.node_id == TreeNode.id)
            .join(Course, MaterialFolderLink.course_id == Course.id)
            .where(MaterialFolderLink.folder_id == folder_id)
            .order_by(TreeNode.sort_path)
        ).all()
        return [
            {
                "node_id": link.node_id,
                "owner_title": node.title,
                "breadcrumb": [
                    {"id": entry["id"], "title": entry["title"]}
                    for entry in self._tree.breadcrumb(node)
                ],
                "is_course_level": node.is_root,
                "course_id": course.id,
                "course_title": course.title,
                "auto_assigned": link.auto_assigned,
                "rationale": link.rationale,
            }
            for link, node, course in rows
        ]

    def folder_delete_info(self, folder_id: int) -> dict[str, Any]:
        folder = self._session.get(MaterialFolder, folder_id)
        if folder is None:
            raise CourseError("folder not found")
        folder_ids = subtree_folder_ids(self._session, folder)
        member_ids = folder_member_ids(self._session, folder)
        for sub_folder in self._session.scalars(
            select(MaterialFolder).where(MaterialFolder.id.in_(folder_ids))
        ):
            if sub_folder.source_id is not None:
                member_ids.update(
                    self._session.scalars(
                        select(Material.id).where(
                            Material.source_id == sub_folder.source_id
                        )
                    )
                )
        node_map: dict[int, dict[str, Any]] = {}
        for _link, node, course in self._session.execute(
            select(MaterialFolderLink, TreeNode, Course)
            .join(TreeNode, MaterialFolderLink.node_id == TreeNode.id)
            .join(Course, MaterialFolderLink.course_id == Course.id)
            .where(MaterialFolderLink.folder_id.in_(folder_ids))
        ).all():
            node_entry = node_map.setdefault(
                node.id, self._folder_delete_node_entry(node, course)
            )
            node_entry["folder_count"] += 1
        for _link, node, course in self._session.execute(
            select(MaterialLink, TreeNode, Course)
            .join(TreeNode, MaterialLink.node_id == TreeNode.id)
            .join(Course, MaterialLink.course_id == Course.id)
            .where(MaterialLink.material_id.in_(member_ids))
        ).all():
            node_entry = node_map.setdefault(
                node.id, self._folder_delete_node_entry(node, course)
            )
            node_entry["material_count"] += 1
        node_links = sorted(
            node_map.values(),
            key=lambda entry: (
                entry["course_title"].lower(),
                " / ".join(part["title"] for part in entry["breadcrumb"]),
            ),
        )
        return {
            "subfolders": len(folder_ids) - 1,
            "materials": len(member_ids),
            "node_links": node_links,
        }

    def _folder_delete_node_entry(
        self, node: TreeNode, course: Course
    ) -> dict[str, Any]:
        return {
            "node_id": node.id,
            "owner_title": node.title,
            "breadcrumb": [
                {"id": entry["id"], "title": entry["title"]}
                for entry in self._tree.breadcrumb(node)
            ],
            "is_course_level": node.is_root,
            "course_title": course.title,
            "folder_count": 0,
            "material_count": 0,
        }

    def commit_outline(self, course_id: int, draft: dict[str, Any]) -> dict[str, Any]:
        material_ids: set[int] = set()
        for chapter in draft.get("chapters", []):
            for section in chapter.get("sections", []):
                material_ids.update(section.get("material_ids", []))
        materials = {
            material.id: material
            for material in self._session.scalars(
                select(Material).where(
                    Material.course_id == course_id, Material.id.in_(material_ids)
                )
            )
        }
        root = self._tree.ensure_root(course_id)
        created_chapters = 0
        created_sections = 0
        allocations = 0
        for chapter_draft in draft.get("chapters", []):
            chapter = self._tree.create_node(
                course_id,
                root.id,
                chapter_draft["title"],
                summary=chapter_draft.get("summary"),
            )
            created_chapters += 1
            for section_draft in chapter_draft.get("sections", []):
                section = self._tree.create_node(
                    course_id,
                    chapter.id,
                    section_draft["title"],
                    objectives=section_draft.get("objectives"),
                )
                created_sections += 1
                for material_id in section_draft.get("material_ids", []):
                    if material_id not in materials:
                        continue
                    self.assign(
                        section.id,
                        material_id,
                        rationale=section_draft.get("rationale"),
                        auto_assigned=True,
                        confidence=section_draft.get("confidence"),
                    )
                    allocations += 1
        return {
            "chapters": created_chapters,
            "sections": created_sections,
            "allocations": allocations,
        }

    def set_study_state(
        self, material_id: int, profile_id: int, status: str, progress: float | None = None
    ) -> MaterialStudyState:
        try:
            status_value = StudyStatus.parse(status)
        except ValueError as error:
            raise CourseError(str(error)) from error
        state = self._session.scalars(
            select(MaterialStudyState).where(
                MaterialStudyState.material_id == material_id,
                MaterialStudyState.profile_id == profile_id,
            )
        ).first()
        if state is None:
            state = MaterialStudyState(
                material_id=material_id,
                profile_id=profile_id,
                status=StudyStatus.UNREAD,
                progress=0.0,
            )
            self._session.add(state)
        state.status = status_value
        state.last_opened_at = utcnow()
        if progress is not None:
            state.progress = max(0.0, min(1.0, progress))
        elif status_value == StudyStatus.STUDIED:
            state.progress = 1.0
        self._session.flush()
        return state

    def study_states(self, profile_id: int) -> dict[int, dict[str, Any]]:
        rows = self._session.scalars(
            select(MaterialStudyState).where(MaterialStudyState.profile_id == profile_id)
        )
        return {
            state.material_id: {
                "status": state.status,
                "progress": state.progress,
                "last_opened_at": (
                    state.last_opened_at.isoformat() if state.last_opened_at else None
                ),
            }
            for state in rows
        }


def purge_course(session: Session, course: Course) -> None:
    session.execute(
        delete(StudySession).where(StudySession.course_id == course.id)
    )
    session_ids = list(
        session.scalars(
            select(ChatSession.id).where(ChatSession.course_id == course.id)
        )
    )
    if session_ids:
        cancel_jobs_for(session, chat_session_ids=session_ids)
        message_ids = list(
            session.scalars(
                select(ChatMessage.id).where(ChatMessage.session_id.in_(session_ids))
            )
        )
        if message_ids:
            session.execute(
                delete(ChatProposal).where(ChatProposal.message_id.in_(message_ids))
            )
        session.execute(
            delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids))
        )
        session.execute(delete(ChatSession).where(ChatSession.id.in_(session_ids)))
    activities = list(
        session.scalars(select(Activity).where(Activity.course_id == course.id))
    )
    if activities:
        activity_ids = [activity.id for activity in activities]
        attempt_ids = list(
            session.scalars(
                select(Attempt.id).where(Attempt.activity_id.in_(activity_ids))
            )
        )
        question_ids = list(
            session.scalars(
                select(Question.id).where(Question.activity_id.in_(activity_ids))
            )
        )
        if attempt_ids:
            session.execute(
                delete(QuizHelpEvent).where(QuizHelpEvent.attempt_id.in_(attempt_ids))
            )
            session.execute(
                delete(Answer).where(Answer.attempt_id.in_(attempt_ids))
            )
            session.execute(delete(Attempt).where(Attempt.id.in_(attempt_ids)))
        if question_ids:
            session.execute(delete(Mistake).where(Mistake.question_id.in_(question_ids)))
            session.execute(delete(ItemStat).where(ItemStat.question_id.in_(question_ids)))
            session.execute(delete(Question).where(Question.id.in_(question_ids)))
        for activity in activities:
            session.delete(activity)
    for exercise in list(
        session.scalars(select(Exercise).where(Exercise.course_id == course.id))
    ):
        session.execute(delete(ReviewLog).where(ReviewLog.card_id == exercise.id))
        session.delete(exercise)
    for note in list(session.scalars(select(Note).where(Note.course_id == course.id))):
        cancel_jobs_for(session, note_ids=[note.id])
        session.delete(note)
    for material in list(
        session.scalars(select(Material).where(Material.course_id == course.id))
    ):
        purge_material(session, material)
    session.execute(
        delete(MaterialFolderLink).where(MaterialFolderLink.course_id == course.id)
    )
    session.execute(
        delete(MaterialFolder).where(MaterialFolder.course_id == course.id)
    )
    session.execute(
        delete(MaterialSource).where(MaterialSource.course_id == course.id)
    )
    session.execute(
        delete(MaterialSuggestion).where(MaterialSuggestion.course_id == course.id)
    )
    session.execute(delete(PlanItem).where(PlanItem.course_id == course.id))
    session.execute(
        delete(NodeConcept).where(
            NodeConcept.node_id.in_(
                select(TreeNode.id).where(TreeNode.course_id == course.id)
            )
        )
    )
    session.execute(
        delete(ConceptLink).where(ConceptLink.course_id == course.id)
    )
    session.execute(delete(Concept).where(Concept.course_id == course.id))
    max_depth = session.scalars(
        select(TreeNode.depth)
        .where(TreeNode.course_id == course.id)
        .order_by(TreeNode.depth.desc())
        .limit(1)
    ).first()
    for depth in range(int(max_depth or 0), -1, -1):
        session.execute(
            delete(TreeNode).where(
                TreeNode.course_id == course.id, TreeNode.depth == depth
            )
        )
    session.execute(delete(MaterialGroup).where(MaterialGroup.course_id == course.id))
    session.execute(
        delete(CourseTaskAssignment).where(
            CourseTaskAssignment.course_id == course.id
        )
    )
    session.execute(
        delete(CourseDefaultTaskAssignment).where(
            CourseDefaultTaskAssignment.course_id == course.id
        )
    )
    session.delete(course)
    session.flush()
