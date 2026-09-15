from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import MaterialStatus
from ...domain.models import (
    Concept,
    Material,
    MaterialFolder,
    MaterialFolderLink,
    MaterialIndexCard,
    MaterialLink,
    NodeConcept,
    TreeNode,
)
from ..content.folders import folder_member_ids

CAP = 40

STOPWORDS = frozenset(
    {
        "the",
        "and",
        "of",
        "a",
        "an",
        "in",
        "on",
        "for",
        "to",
        "with",
        "by",
        "at",
        "is",
        "are",
        "be",
        "or",
        "as",
        "its",
        "their",
        "this",
        "that",
        "from",
        "into",
        "de",
        "di",
        "e",
        "et",
        "und",
        "der",
        "dero",
        "ein",
        "eine",
    }
)


def _tokens(text: str) -> set[str]:
    cleaned = text.casefold().replace("_", " ")
    tokens = set()
    current: list[str] = []
    for char in cleaned:
        if char.isalnum() or (ord(char) > 127 and char.isalpha()):
            current.append(char)
        else:
            if len(current) >= 3:
                tokens.add("".join(current))
            current = []
    if len(current) >= 3:
        tokens.add("".join(current))
    return tokens - STOPWORDS

CAP = 40


def assigned_material_ids(
    session: Session, course_id: int
) -> set[int]:
    assigned: set[int] = set(
        session.scalars(
            select(MaterialLink.material_id).where(
                MaterialLink.course_id == course_id
            )
        )
    )
    folder_ids = list(
        session.scalars(
            select(MaterialFolderLink.folder_id).where(
                MaterialFolderLink.course_id == course_id
            )
        )
    )
    for folder_id in folder_ids:
        folder = session.get(MaterialFolder, folder_id)
        if folder is None:
            continue
        assigned |= folder_member_ids(session, folder)
    return assigned


def unassigned_materials(
    session: Session, course_id: int
) -> list[Material]:
    assigned = assigned_material_ids(session, course_id)
    materials = list(
        session.scalars(
            select(Material)
            .where(Material.course_id == course_id)
            .order_by(Material.id)
        )
    )
    ready = [material for material in materials if material.status == MaterialStatus.READY]
    unassigned = [material for material in ready if material.id not in assigned]
    return unassigned[:CAP]


def unassigned_payload(
    session: Session, course_id: int
) -> dict[str, Any]:
    materials = unassigned_materials(session, course_id)
    return {
        "count": len(materials),
        "materials": [
            {"id": material.id, "title": material.title}
            for material in materials
        ],
    }


MAX_PER_MATERIAL = 3
MAX_MATERIALS = 40
CONTAINMENT_BONUS = 0.15


def _material_tokens(session: Session, material: Material) -> tuple[set[str], set[str]]:
    title_tokens = _tokens(material.title)
    card = session.get(MaterialIndexCard, material.id)
    card_tokens: set[str] = set()
    if card is not None:
        for entry in card.topics or []:
            card_tokens |= _tokens(entry)
        for entry in card.key_terms or []:
            card_tokens |= _tokens(entry)
    return title_tokens, card_tokens


def _node_infos(session: Session, course_id: int) -> list[dict[str, Any]]:
    nodes = list(
        session.scalars(
            select(TreeNode)
            .where(TreeNode.course_id == course_id)
            .order_by(TreeNode.sort_path)
        )
    )
    live = [node for node in nodes if not node.is_root]
    if not live:
        return []
    concept_map: dict[int, set[str]] = {}
    rows = session.execute(
        select(NodeConcept.node_id, Concept.name).where(
            NodeConcept.node_id.in_([node.id for node in live])
        )
    ).all()
    for node_id, name in rows:
        concept_map.setdefault(int(node_id), set()).add(name)
    infos: list[dict[str, Any]] = []
    for node in live:
        title_tokens = _tokens(node.title)
        summary_tokens = _tokens(node.summary or "")
        objective_tokens = _tokens(" ".join(node.objectives or []))
        concept_tokens = concept_map.get(node.id, set())
        infos.append(
            {
                "node": node,
                "rank": len(infos),
                "core": title_tokens,
                "extras": summary_tokens | objective_tokens | concept_tokens,
                "all": title_tokens
                | summary_tokens
                | objective_tokens
                | concept_tokens,
            }
        )
    return infos


def _node_breadcrumbs(
    session: Session, infos: list[dict[str, Any]]
) -> dict[int, list[dict[str, Any]]]:
    from .tree import TreeService

    tree = TreeService(session)
    breadcrumbs: dict[int, list[dict[str, Any]]] = {}
    for info in infos:
        node = info["node"]
        breadcrumbs[node.id] = [
            {"id": entry["id"], "title": entry["title"]}
            for entry in tree.breadcrumb(node)
        ]
    return breadcrumbs


def suggest_placements(
    session: Session, course_id: int, material_ids: list[int]
) -> list[dict[str, Any]]:
    if not material_ids:
        return []
    material_ids = material_ids[:MAX_MATERIALS]
    materials = {
        material.id: material
        for material in session.scalars(
            select(Material).where(
                Material.course_id == course_id,
                Material.id.in_(material_ids),
            )
        )
    }
    node_infos = _node_infos(session, course_id)
    breadcrumbs = _node_breadcrumbs(session, node_infos)
    suggestions: list[dict[str, Any]] = []
    for material_id in material_ids:
        material = materials.get(material_id)
        if material is None:
            suggestions.append({"material_id": material_id, "candidates": []})
            continue
        title_tokens, card_tokens = _material_tokens(session, material)
        material_tokens = title_tokens | card_tokens
        ranked: list[tuple[float, int, int, list[str]]] = []
        for info in node_infos:
            overlap = material_tokens & set(info["all"])
            if not overlap:
                continue
            union_size = len(material_tokens | set(info["all"]))
            jaccard = len(overlap) / union_size
            containment = len(overlap & title_tokens) / len(title_tokens)
            score = jaccard + CONTAINMENT_BONUS * containment
            ranked.append((-score, info["rank"], info["node"].id, sorted(overlap)))
        ranked.sort()
        candidates: list[dict[str, Any]] = []
        for neg_score, _rank, node_id, matched_on in ranked[:MAX_PER_MATERIAL]:
            node = session.get(TreeNode, node_id)
            assert node is not None
            candidates.append(
                {
                    "node_id": node_id,
                    "node_title": node.title,
                    "breadcrumb": breadcrumbs[node_id],
                    "score": round(-neg_score, 4),
                    "matched_on": matched_on[:6],
                }
            )
        suggestions.append(
            {
                "material_id": material_id,
                "candidates": candidates,
            }
        )
    return suggestions
