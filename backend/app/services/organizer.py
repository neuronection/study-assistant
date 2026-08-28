import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway, Message
from ..domain.models import (
    Concept,
    Material,
    MaterialFolder,
    MaterialLink,
    NodeConcept,
    TreeNode,
)
from ..services.tree import TreeService
from .folders import folder_links_by_node, folder_member_ids

REVIEW_TASK = "description"

MAX_FINDINGS = 12

REVIEW_SYSTEM = (
    "You are a course organizer reviewing one node of a study course outline. You get "
    "the node's children, the material summaries assigned to them, and any "
    "known concept coverage.\n"
    "Respond with ONLY a JSON object:\n"
    "{\n"
    '  "findings": [\n'
    '    {"kind": "gap"|"ordering"|"orphan"|"coverage",\n'
    '     "title": str, "detail": str, "suggestion": str}\n'
    "  ]\n"
    "}\n"
    "Rules: 3-8 findings, each honest and specific (name the child/material); "
    '"gap" = a topic in the material with no child node for it; "ordering" = a '
    'child taught before its prerequisites; "orphan" = material assigned '
    'nowhere or irrelevant; "coverage" = child node without material. If the '
    "node looks well organized, say so with fewer findings."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_FINDING_KINDS = ("gap", "ordering", "orphan", "coverage")


class OrganizerError(ValueError):
    pass


def review_node(
    gateway: LLMGateway,
    node: TreeNode,
    children: list[dict[str, Any]],
    unassigned: list[dict[str, Any]],
    concepts: list[str],
) -> list[dict[str, Any]]:
    prompt = json.dumps(
        {
            "node": {"title": node.title, "summary": node.summary},
            "children": children,
            "unassigned_materials": unassigned,
            "known_concepts": concepts,
        },
        ensure_ascii=False,
    )
    text = gateway.generate(
        REVIEW_TASK,
        [
            Message(role="system", content=REVIEW_SYSTEM),
            Message(role="user", content=prompt),
        ],
        course_id=node.course_id,
    )
    match = _JSON_RE.search(text)
    if match is None:
        raise OrganizerError("review model returned no JSON")
    try:
        parsed = json.loads(match.group(0))
    except ValueError as error:
        raise OrganizerError("review model returned invalid JSON") from error
    findings: list[dict[str, Any]] = []
    for entry in (parsed.get("findings") or [])[:MAX_FINDINGS]:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind", "")).strip()
        title = str(entry.get("title", "")).strip()[:200]
        if kind not in _FINDING_KINDS or not title:
            continue
        findings.append(
            {
                "kind": kind,
                "title": title,
                "detail": str(entry.get("detail", "")).strip()[:1000] or None,
                "suggestion": str(entry.get("suggestion", "")).strip()[:500] or None,
            }
        )
    return findings


def node_context(
    session: Session, node_id: int
) -> tuple[TreeNode, list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    tree = TreeService(session)
    node = tree.get(node_id)
    scope_ids = tree.subtree_ids(node)
    links = list(
        session.scalars(
            select(MaterialLink).where(
                MaterialLink.course_id == node.course_id,
                MaterialLink.node_id.in_(scope_ids),
            )
        )
    )
    folder_member_map: dict[int, set[int]] = {}
    for scope_node_id, folder_links in folder_links_by_node(session, scope_ids).items():
        members: set[int] = set()
        for folder_link in folder_links:
            folder = session.get(MaterialFolder, folder_link.folder_id)
            if folder is not None:
                members |= folder_member_ids(session, folder)
        if members:
            folder_member_map[scope_node_id] = members
    all_material_ids = {link.material_id for link in links} | {
        material_id for members in folder_member_map.values() for material_id in members
    }
    materials = {
        material.id: material
        for material in session.scalars(
            select(Material).where(Material.id.in_(all_material_ids))
        )
    }
    children = tree.node_with_children(node)
    assigned_ids: set[int] = set()
    children_payload: list[dict[str, Any]] = []
    for child in children:
        child_direct = {
            link.material_id
            for link in links
            if link.node_id == child["id"]
        }
        child_ids = child_direct | folder_member_map.get(child["id"], set())
        child_materials = [
            materials[material_id]
            for material_id in sorted(child_ids)
            if material_id in materials
        ]
        assigned_ids.update(material.id for material in child_materials)
        children_payload.append(
            {
                "title": child["title"],
                "objectives": child["objectives"],
                "materials": [
                    {"title": material.title, "status": material.status}
                    for material in child_materials
                ],
            }
        )
    own_direct = {
        link.material_id for link in links if link.node_id == node.id
    }
    own_ids = own_direct | folder_member_map.get(node.id, set())
    own_materials = [
        materials[material_id]
        for material_id in sorted(own_ids)
        if material_id in materials
    ]
    assigned_ids.update(material.id for material in own_materials)
    course_materials = list(
        session.scalars(
            select(Material).where(
                Material.course_id == node.course_id,
                Material.status == "ready",
            )
        )
    )
    unassigned = [
        {"title": material.title}
        for material in course_materials
        if material.id not in assigned_ids
    ][:40]
    concepts = list(
        session.scalars(
            select(Concept.name)
            .join(NodeConcept, NodeConcept.concept_id == Concept.id)
            .where(NodeConcept.node_id.in_(scope_ids))
        )
    )
    return node, children_payload, unassigned, sorted(set(concepts))


def review_report_markdown(node_title: str, findings: list[dict[str, Any]]) -> str:
    lines = [f"Organizer review of **{node_title}**.", ""]
    if not findings:
        lines.append("No issues found — this part of the course looks well organized.")
        return "\n".join(lines)
    kind_names = {
        "gap": "Gap",
        "ordering": "Ordering",
        "orphan": "Orphaned material",
        "coverage": "Coverage",
    }
    for finding in findings:
        lines.append(f"### {kind_names.get(finding['kind'], finding['kind'])}: {finding['title']}")
        if finding.get("detail"):
            lines.append(str(finding["detail"]))
        if finding.get("suggestion"):
            lines.append(f"→ Suggestion: {finding['suggestion']}")
        lines.append("")
    return "\n".join(lines).strip()


def missing_note_markdown(
    gateway: LLMGateway, node: TreeNode, materials: list[dict[str, Any]]
) -> str:
    prompt = json.dumps(
        {"node": {"title": node.title, "objectives": node.objectives or []},
         "materials": materials},
        ensure_ascii=False,
    )
    system = (
        "You draft study notes for one course outline node from its material "
        "summaries: a short intro, the key ideas as bullets, and the important "
        "formulas in LaTeX ($...$ / $$...$$). Markdown only, at most ~300 words. "
        "These are AI-drafted notes — faithful to the material, no inventions."
    )
    return gateway.generate(
        REVIEW_TASK,
        [
            Message(role="system", content=system),
            Message(role="user", content=prompt),
        ],
        course_id=node.course_id,
    ).strip()
