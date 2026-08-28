from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.models import (
    Concept,
    Material,
    MaterialFolder,
    MaterialLink,
    NodeConcept,
    TreeNode,
    utcnow,
)
from .folders import folder_links_by_node, folder_member_ids


class ProposalActionError(ValueError):
    pass


def _node_in_course(session: Session, node_id: int, course_id: int) -> TreeNode:
    node = session.get(TreeNode, node_id)
    if node is None or node.course_id != course_id:
        raise ProposalActionError(
            f"target node {node_id} no longer exists in this course"
        )
    return node


def execute_proposal(
    session: Session,
    *,
    action: str,
    payload: dict[str, Any],
    course_id: int,
) -> tuple[str, dict[str, Any]]:
    if action == "create_note":
        raise ProposalActionError("create_note executes in the API layer")
    if action == "assign_material":
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
                if folder is not None and material.id in folder_member_ids(
                    session, folder
                ):
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
    if action == "cover_concept":
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
    if action == "set_node_ai_hint":
        node = _node_in_course(session, int(payload["node_id"]), course_id)
        hint = str(payload["hint"]).strip()
        if not hint:
            raise ProposalActionError("hint must not be empty")
        node.ai_hint = hint[:2000]
        session.flush()
        return "executed", {"node_id": node.id}
    raise ProposalActionError(f"unsupported proposal action '{action}'")


def mark_stale(proposal: Any, reason: str) -> None:
    proposal.status = "stale"
    proposal.result = {"error": reason}
    proposal.executed_at = utcnow()
