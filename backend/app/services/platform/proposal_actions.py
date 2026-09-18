from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...ai.proposals import PROPOSAL_ACTIONS
from ...core.vocab import ChatProposalStatus
from ...domain.models import (
    Activity,
    Concept,
    Course,
    Exercise,
    Extraction,
    Material,
    MaterialFolder,
    MaterialLink,
    NodeConcept,
    Note,
    PlanItem,
    TreeNode,
    utcnow,
)
from ...jobs.runner import JobRunner
from ...storage.blobs import BlobStore
from ..content.drawings import blocks_md
from ..content.folders import folder_links_by_node, folder_member_ids
from ..content.materials import MaterialsService
from ..content.notes import NoteBodyError, normalize_tags, save_note_body
from ..knowledge.tree import TreeError, TreeService
from ..study.planner import PlannerError, generate_plan


class ProposalActionError(ValueError):
    pass


@dataclass(frozen=True)
class ProposalContext:
    blobs: BlobStore | None = None
    jobs: JobRunner | None = None
    profile_id: int | None = None


Executor = Callable[
    [Session, dict[str, Any], int, ProposalContext], tuple[str, dict[str, Any]]
]


def _node_in_course(session: Session, node_id: int, course_id: int) -> TreeNode:
    node = session.get(TreeNode, node_id)
    if node is None or node.course_id != course_id:
        raise ProposalActionError(
            f"target node {node_id} no longer exists in this course"
        )
    return node


def capture_proposal_snapshot(
    session: Session, *, action: str, payload: dict[str, Any], course_id: int
) -> dict[str, Any] | None:
    spec = PROPOSAL_ACTIONS.get(action)
    if spec is None or spec.snapshot is None:
        return None
    if spec.snapshot == "note_body":
        note_id = payload.get("note_id")
        if note_id is None:
            return None
        note = session.get(Note, int(note_id))
        if note is None or note.course_id != course_id:
            return None
        return {"original_md": blocks_md(note.body or [])}
    if spec.snapshot == "extraction_md":
        material_id = payload.get("material_id")
        if material_id is None:
            return None
        material = session.get(Material, int(material_id))
        if material is None or material.course_id != course_id:
            return None
        latest = session.scalars(
            select(Extraction)
            .where(Extraction.material_id == material.id)
            .order_by(Extraction.version.desc())
            .limit(1)
        ).first()
        if latest is None:
            return None
        return {"original_md": latest.markdown}
    return None


_TARGET_KINDS = {
    "edit_note": ("note", "note_id"),
    "append_note": ("note", "note_id"),
    "edit_material": ("material", "material_id"),
    "append_material": ("material", "material_id"),
    "create_note": ("note", None),
    "create_material": ("material", None),
    "create_concept": ("concept", None),
    "attach_link": ("link", None),
}


def _node_title_path(
    session: Session, node: TreeNode, course_id: int
) -> list[str]:
    path: list[str] = []
    current: TreeNode | None = node
    while current is not None:
        path.append(current.title)
        current = (
            session.get(TreeNode, current.parent_id)
            if current.parent_id is not None
            else None
        )
    path.reverse()
    course = session.get(Course, course_id)
    if course is not None and path:
        path[0] = course.title
    return path


def resolve_proposal_target(
    session: Session, *, action: str, payload: dict[str, Any], course_id: int
) -> dict[str, Any] | None:
    target = _TARGET_KINDS.get(action)
    if target is None:
        return None
    kind, id_field = target
    info: dict[str, Any] = {"target_kind": kind}
    if id_field == "note_id":
        note_id = payload.get("note_id")
        if note_id is None:
            return None
        note = session.get(Note, int(note_id))
        if note is None or note.course_id != course_id:
            return None
        info["target_name"] = note.title
    elif id_field == "material_id":
        material_id = payload.get("material_id")
        if material_id is None:
            return None
        material = session.get(Material, int(material_id))
        if material is None or material.course_id != course_id:
            return None
        info["target_name"] = material.title
    else:
        title = payload.get("name") if kind == "concept" else payload.get("title")
        if not isinstance(title, str) or not title.strip():
            if kind == "link":
                parsed = urlsplit(str(payload.get("url") or ""))
                if parsed.netloc:
                    title = parsed.netloc
                else:
                    return None
            else:
                return None
        info["target_name"] = str(title).strip()
    node_id = payload.get("node_id")
    if node_id is not None:
        node = session.get(TreeNode, int(node_id))
        if node is not None and node.course_id == course_id:
            info["target_node_id"] = node.id
            info["target_node_path"] = _node_title_path(session, node, course_id)
    return info


def _execute_assign_material(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    node = _node_in_course(session, int(payload["node_id"]), course_id)
    material = session.get(Material, int(payload["material_id"]))
    if material is None or material.course_id != course_id:
        raise ProposalActionError(
            f"material {payload['material_id']} no longer exists in this course"
        )
    existing = session.scalars(
        select(MaterialLink).where(
            MaterialLink.course_id == course_id,
            MaterialLink.node_id == node.id,
            MaterialLink.material_id == material.id,
        )
    ).first()
    if existing is None:
        via_folder = False
        for folder_link in folder_links_by_node(session, [node.id])[node.id]:
            folder = session.get(MaterialFolder, folder_link.folder_id)
            if folder is not None and material.id in folder_member_ids(session, folder):
                via_folder = True
                break
        if via_folder:
            return "executed", {
                "note": "already assigned via folder",
                "node_id": node.id,
                "material_id": material.id,
            }
    if existing is not None:
        return "executed", {
            "note": "already assigned",
            "node_id": node.id,
            "material_id": material.id,
        }
    session.add(
        MaterialLink(
            course_id=course_id,
            node_id=node.id,
            material_id=material.id,
            rationale="AI proposal",
        )
    )
    session.flush()
    return "executed", {"node_id": node.id, "material_id": material.id}


def _execute_cover_concept(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    node = _node_in_course(session, int(payload["node_id"]), course_id)
    concept = session.get(Concept, int(payload["concept_id"]))
    if concept is None or concept.course_id != course_id:
        raise ProposalActionError(
            f"concept {payload['concept_id']} no longer exists in this course"
        )
    existing_cover = session.scalars(
        select(NodeConcept).where(
            NodeConcept.node_id == node.id,
            NodeConcept.concept_id == concept.id,
        )
    ).first()
    if existing_cover is not None:
        return "executed", {
            "note": "already covered",
            "node_id": node.id,
            "concept_id": concept.id,
        }
    session.add(NodeConcept(node_id=node.id, concept_id=concept.id))
    session.flush()
    return "executed", {"node_id": node.id, "concept_id": concept.id}


def _execute_set_node_ai_hint(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    node = _node_in_course(session, int(payload["node_id"]), course_id)
    hint = str(payload["hint"]).strip()
    if not hint:
        raise ProposalActionError("hint must not be empty")
    node.ai_hint = hint[:2000]
    session.flush()
    return "executed", {"node_id": node.id}


def _load_note(session: Session, note_id: int, course_id: int) -> Note:
    note = session.get(Note, note_id)
    if note is None or note.course_id != course_id:
        raise ProposalActionError(f"note {note_id} no longer exists in this course")
    return note


def _ensure_unmodified(note: Note, payload: dict[str, Any]) -> None:
    original = payload.get("original_md")
    if original is not None and blocks_md(note.body or []) != original:
        raise ProposalActionError("note changed since this proposal was made")


def _execute_edit_note(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    note = _load_note(session, int(payload["note_id"]), course_id)
    _ensure_unmodified(note, payload)
    try:
        save_note_body(
            session, note, str(payload["new_body_md"]), cause="ai-edit", force=True
        )
    except NoteBodyError as error:
        raise ProposalActionError(str(error)) from None
    return "executed", {"note_id": note.id}


def _execute_append_note(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    note = _load_note(session, int(payload["note_id"]), course_id)
    _ensure_unmodified(note, payload)
    current = blocks_md(note.body or [])
    addition = str(payload["markdown"])
    heading = str(payload.get("heading") or "").strip().lstrip("#").strip()
    if heading:
        addition = f"## {heading}\n\n{addition}"
    merged = f"{current.rstrip()}\n\n{addition.strip()}" if current.strip() else addition
    try:
        save_note_body(session, note, merged, cause="ai-edit", force=True)
    except NoteBodyError as error:
        raise ProposalActionError(str(error)) from None
    return "executed", {"note_id": note.id}


def _load_material_with_extraction(
    session: Session,
    material_id: int,
    course_id: int,
    context: ProposalContext,
) -> tuple[Material, MaterialsService, Extraction]:
    if context.blobs is None:
        raise ProposalActionError("proposal execution context is missing blobs")
    material = session.get(Material, material_id)
    if material is None or material.course_id != course_id:
        raise ProposalActionError(
            f"material {material_id} no longer exists in this course"
        )
    service = MaterialsService(session, context.blobs)
    latest = service.latest_extraction(material.id)
    if latest is None:
        raise ProposalActionError(
            f"material {material_id} has no extraction to edit"
        )
    return material, service, latest


def _ensure_extraction_unmodified(latest: Extraction, payload: dict[str, Any]) -> None:
    original = payload.get("original_md")
    if original is not None and latest.markdown != original:
        raise ProposalActionError("material changed since this proposal was made")


def _execute_edit_material(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    material, service, latest = _load_material_with_extraction(
        session, int(payload["material_id"]), course_id, context
    )
    _ensure_extraction_unmodified(latest, payload)
    try:
        extraction, old_chunk_ids = service.edit_extraction(
            material, str(payload["new_markdown"])
        )
    except ValueError as error:
        raise ProposalActionError(str(error)) from None
    return "executed", {
        "material_id": material.id,
        "extraction_id": extraction.id,
        "old_chunk_ids": old_chunk_ids,
    }


def _execute_append_material(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    material, service, latest = _load_material_with_extraction(
        session, int(payload["material_id"]), course_id, context
    )
    _ensure_extraction_unmodified(latest, payload)
    addition = str(payload["markdown"]).strip()
    heading = str(payload.get("heading") or "").strip().lstrip("#").strip()
    if heading:
        addition = f"## {heading}\n\n{addition}"
    merged = f"{latest.markdown.rstrip()}\n\n{addition}"
    try:
        extraction, old_chunk_ids = service.edit_extraction(material, merged)
    except ValueError as error:
        raise ProposalActionError(str(error)) from None
    return "executed", {
        "material_id": material.id,
        "extraction_id": extraction.id,
        "old_chunk_ids": old_chunk_ids,
    }


def _execute_create_material(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    if context.blobs is None or context.profile_id is None:
        raise ProposalActionError("proposal execution context is incomplete")
    service = MaterialsService(session, context.blobs)
    title = str(payload["title"]).strip()
    safe_name = title.replace("/", " ").replace("\\", " ").strip() or "material"
    try:
        material, deduped = service.create_text(
            profile_id=context.profile_id,
            course_id=course_id,
            filename=f"{safe_name}.md",
            content=str(payload["body_md"]),
        )
    except ValueError as error:
        raise ProposalActionError(str(error)) from None
    node_id = payload.get("node_id")
    if node_id is not None:
        node = _node_in_course(session, int(node_id), course_id)
        session.add(
            MaterialLink(
                course_id=course_id,
                node_id=node.id,
                material_id=material.id,
                rationale="AI proposal",
            )
        )
        session.flush()
    if not deduped and context.jobs is not None:
        service.queue_ingest(material, context.jobs)
    return "executed", {
        "material_id": material.id,
        "deduped": deduped,
    }


def _execute_attach_link(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    if context.blobs is None or context.profile_id is None:
        raise ProposalActionError("proposal execution context is incomplete")
    url = str(payload["url"]).strip()
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ProposalActionError("attach_link url must be an http(s) URL")
    service = MaterialsService(session, context.blobs)
    title = str(payload.get("title") or "").strip() or None
    node_id = payload.get("node_id")
    placement: int | None = None
    if node_id is not None:
        placement = _node_in_course(session, int(node_id), course_id).id
    try:
        material, deduped = service.create_link(
            profile_id=context.profile_id,
            course_id=course_id,
            url=url,
            title=title,
            node_id=placement,
        )
    except ValueError as error:
        raise ProposalActionError(str(error)) from None
    return "executed", {
        "material_id": material.id,
        "deduped": deduped,
    }


def _execute_create_concept(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    del context
    name = str(payload["name"]).strip()
    if not name:
        raise ProposalActionError("concept name must not be empty")
    description = payload.get("description")
    concept = session.scalars(
        select(Concept).where(Concept.course_id == course_id, Concept.name == name)
    ).first()
    created = False
    if concept is None:
        concept = Concept(
            course_id=course_id,
            name=name[:200],
            description=str(description).strip()[:2000]
            if description
            else None,
        )
        session.add(concept)
        session.flush()
        created = True
    node_id = payload.get("node_id")
    linked_node_id: int | None = None
    if node_id is not None:
        node = _node_in_course(session, int(node_id), course_id)
        existing = session.scalars(
            select(NodeConcept).where(
                NodeConcept.node_id == node.id,
                NodeConcept.concept_id == concept.id,
            )
        ).first()
        if existing is None:
            session.add(NodeConcept(node_id=node.id, concept_id=concept.id))
            session.flush()
        linked_node_id = node.id
    return "executed", {
        "concept_id": concept.id,
        "created": created,
        "node_id": linked_node_id,
    }


def _execute_move_to_node(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    del context
    kind = str(payload["kind"])
    target_id = int(payload["id"])
    node = _node_in_course(session, int(payload["node_id"]), course_id)
    try:
        placement = TreeService(session).placement_node(course_id, node.id)
    except TreeError as error:
        raise ProposalActionError(str(error)) from None
    if kind == "material":
        return _execute_assign_material(
            session,
            {"material_id": target_id, "node_id": node.id},
            course_id,
            ProposalContext(),
        )
    scoped: Note | Activity | Exercise | None
    if kind == "note":
        scoped = session.get(Note, target_id)
    elif kind == "quiz":
        scoped = session.get(Activity, target_id)
    else:
        scoped = session.get(Exercise, target_id)
    if scoped is None or scoped.course_id != course_id:
        raise ProposalActionError(
            f"{kind} {target_id} no longer exists in this course"
        )
    scoped.node_id = placement
    session.flush()
    return "executed", {"kind": kind, "id": target_id, "node_id": placement}


def _execute_tag_note(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    del context
    note = _load_note(session, int(payload["note_id"]), course_id)
    addition = [str(tag) for tag in payload.get("add") or []]
    note.tags = normalize_tags(list(note.tags or []) + addition)
    session.flush()
    return "executed", {"note_id": note.id, "tags": note.tags}


def _execute_set_exam_date(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    del context
    course = session.get(Course, course_id)
    if course is None:
        raise ProposalActionError("course no longer exists")
    raw = payload["exam_date"]
    course.exam_date = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
    session.flush()
    return "executed", {
        "course_id": course_id,
        "exam_date": course.exam_date.isoformat(),
    }


def _execute_generate_plan(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    del payload
    if context.profile_id is None:
        raise ProposalActionError("proposal execution context is incomplete")
    course = session.get(Course, course_id)
    if course is None:
        raise ProposalActionError("course no longer exists")
    try:
        items = generate_plan(session, course, context.profile_id)
    except PlannerError as error:
        raise ProposalActionError(str(error)) from None
    return "executed", {"course_id": course_id, "draft_count": len(items)}


def _execute_add_plan_items(
    session: Session,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext,
) -> tuple[str, dict[str, Any]]:
    if context.profile_id is None:
        raise ProposalActionError("proposal execution context is incomplete")
    today = utcnow().date()
    created = 0
    for entry in payload.get("items") or []:
        due = entry.get("due_date")
        if due is not None and not isinstance(due, date):
            due = date.fromisoformat(str(due))
        if due is None:
            days_ahead = int(entry.get("days_ahead") or 0)
            due = today.fromordinal(today.toordinal() + days_ahead)
        session.add(
            PlanItem(
                profile_id=context.profile_id,
                course_id=course_id,
                title=str(entry["title"]).strip()[:300],
                kind=str(entry.get("kind") or "study"),
                due_date=due,
                origin="manual",
            )
        )
        created += 1
    session.flush()
    return "executed", {"course_id": course_id, "created": created}


EXECUTORS: dict[str, Executor] = {
    "assign_material": _execute_assign_material,
    "cover_concept": _execute_cover_concept,
    "set_node_ai_hint": _execute_set_node_ai_hint,
    "edit_note": _execute_edit_note,
    "append_note": _execute_append_note,
    "edit_material": _execute_edit_material,
    "append_material": _execute_append_material,
    "create_material": _execute_create_material,
    "create_concept": _execute_create_concept,
    "attach_link": _execute_attach_link,
    "move_to_node": _execute_move_to_node,
    "tag_note": _execute_tag_note,
    "set_exam_date": _execute_set_exam_date,
    "generate_plan": _execute_generate_plan,
    "add_plan_items": _execute_add_plan_items,
}

POSTPROCESS_ACTIONS = ("edit_material", "append_material")


def execute_proposal(
    session: Session,
    *,
    action: str,
    payload: dict[str, Any],
    course_id: int,
    context: ProposalContext | None = None,
) -> tuple[str, dict[str, Any]]:
    executor = EXECUTORS.get(action)
    if executor is None:
        raise ProposalActionError(f"unsupported proposal action '{action}'")
    return executor(session, payload, course_id, context or ProposalContext())


def mark_stale(proposal: Any, reason: str) -> None:
    proposal.status = ChatProposalStatus.STALE.value
    proposal.result = {"error": reason}
    proposal.executed_at = utcnow()
