import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...ai.gateway import LLMGateway, Message
from ...core.vocab import ConceptRelation
from ...domain.models import Concept, ConceptLink, Course, NodeConcept, TreeNode

CONCEPTS_TASK = "concepts"

MAX_CONCEPTS = 60
MAX_LINKS = 120

SYSTEM_PROMPT = (
    "You are a curriculum analyst. Given a course's materials (summaries and "
    "topics) and its outline, extract the key concepts and their relations.\n"
    "Respond with ONLY a JSON object:\n"
    "{\n"
    '  "concepts": [\n'
    '    {"name": str (<= 60 chars), "description": str, "aliases": [str]}\n'
    "  ],\n"
    '  "links": [\n'
    '    {"from": str, "to": str, "relation": "prereq-of"|"part-of"|"related-to"}\n'
    "  ],\n"
    '  "nodes": [{"node_title": str, "concepts": [str]}]\n'
    "}\n"
    "Rules: 5-60 concepts, concrete topic names (e.g. 'chain rule', "
    "'definite integral'); every link endpoint must be a listed concept; "
    "node titles must match the outline exactly; 0-8 concepts per node."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class ConceptsError(ValueError):
    pass


def extract_concepts(
    gateway: LLMGateway, course: Course, materials: list[dict[str, Any]]
) -> dict[str, Any]:
    material_lines = []
    for material in materials:
        topics = ", ".join(material.get("topics") or [])
        summary = material.get("summary") or ""
        line = f"- {material['title']}"
        if topics:
            line += f" — topics: {topics}"
        if summary:
            line += f" — {summary[:200]}"
        material_lines.append(line)
    prompt = (
        f"Course: {course.title}\n"
        f"Subject: {course.subject or 'unspecified'}\n\n"
        "Materials:\n" + "\n".join(material_lines)
    )
    text = gateway.generate(
        CONCEPTS_TASK,
        [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ],
        course_id=course.id,
    )
    match = _JSON_RE.search(text)
    if match is None:
        raise ConceptsError("concept model returned no JSON")
    try:
        parsed = json.loads(match.group(0))
    except ValueError as error:
        raise ConceptsError("concept model returned invalid JSON") from error
    return _validate(parsed, materials)


def _clean_name(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    name = raw.strip().lower()[:60]
    return name or None


def _validate(
    draft: Any, materials: list[dict[str, Any]]
) -> dict[str, Any]:
    if not isinstance(draft, dict):
        raise ConceptsError("concept draft is not an object")
    concepts_out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in (draft.get("concepts") or [])[:MAX_CONCEPTS]:
        if not isinstance(entry, dict):
            continue
        name = _clean_name(entry.get("name"))
        if name is None or name in seen:
            continue
        seen.add(name)
        aliases = [
            alias.strip().lower()[:60]
            for alias in (entry.get("aliases") or [])
            if isinstance(alias, str) and alias.strip()
        ][:8]
        concepts_out.append(
            {
                "name": name,
                "description": (
                    str(entry.get("description", "")).strip()[:500] or None
                ),
                "aliases": aliases,
            }
        )
    if not concepts_out:
        raise ConceptsError("concept draft contained no concepts")
    links_out: list[dict[str, Any]] = []
    link_seen: set[tuple[str, str, str]] = set()
    for entry in (draft.get("links") or [])[:MAX_LINKS]:
        if not isinstance(entry, dict):
            continue
        source = _clean_name(entry.get("from"))
        target = _clean_name(entry.get("to"))
        try:
            relation = ConceptRelation.parse(str(entry.get("relation", "")).strip())
        except ValueError:
            continue
        if source not in seen or target not in seen or source == target:
            continue
        key = (source, target, relation)
        if key in link_seen:
            continue
        link_seen.add(key)
        links_out.append({"from": source, "to": target, "relation": relation})
    nodes_out: list[dict[str, Any]] = []
    node_titles = {
        str(material.get("node_title", "")).strip()
        for material in materials
        if material.get("node_title")
    }
    for entry in (draft.get("nodes") or [])[:80]:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("node_title", "")).strip()
        if not title or (node_titles and title not in node_titles):
            continue
        names = [
            name
            for raw in (entry.get("concepts") or [])[:8]
            if (name := _clean_name(raw)) in seen
        ]
        if names:
            nodes_out.append({"node_title": title, "concepts": names})
    return {
        "concepts": concepts_out,
        "links": links_out,
        "nodes": nodes_out,
    }


def commit_concepts(
    session: Session, course_id: int, draft: dict[str, Any]
) -> dict[str, int]:
    nodes = list(
        session.scalars(
            select(TreeNode).where(
                TreeNode.course_id == course_id, TreeNode.is_root.is_(False)
            )
        )
    )
    node_by_title: dict[str, TreeNode] = {}
    for node in nodes:
        existing_node = node_by_title.get(node.title.strip())
        if existing_node is None:
            node_by_title[node.title.strip()] = node
    existing_concepts = {
        concept.name: concept
        for concept in session.scalars(
            select(Concept).where(Concept.course_id == course_id)
        )
    }
    created = 0
    for entry in draft.get("concepts", []):
        name = entry["name"]
        concept = existing_concepts.get(name)
        if concept is None:
            concept = Concept(
                course_id=course_id,
                name=name,
                description=entry.get("description"),
                aliases=entry.get("aliases"),
            )
            session.add(concept)
            session.flush()
            existing_concepts[name] = concept
            created += 1
    for entry in draft.get("links", []):
        source = existing_concepts.get(entry["from"])
        target = existing_concepts.get(entry["to"])
        if source is None or target is None:
            continue
        link_exists = session.scalars(
            select(ConceptLink).where(
                ConceptLink.from_concept_id == source.id,
                ConceptLink.to_concept_id == target.id,
                ConceptLink.relation == entry["relation"],
            )
        ).first()
        if link_exists is not None:
            continue
        session.add(
            ConceptLink(
                course_id=course_id,
                from_concept_id=source.id,
                to_concept_id=target.id,
                relation=entry["relation"],
            )
        )
    for entry in draft.get("nodes", []):
        target_node = node_by_title.get(str(entry["node_title"]).strip())
        if target_node is None:
            continue
        for name in entry["concepts"]:
            concept = existing_concepts.get(name)
            if concept is None:
                continue
            exists = session.scalars(
                select(NodeConcept).where(
                    NodeConcept.node_id == target_node.id,
                    NodeConcept.concept_id == concept.id,
                )
            ).first()
            if exists is None:
                session.add(NodeConcept(node_id=target_node.id, concept_id=concept.id))
    session.flush()
    return {
        "concepts": len(draft.get("concepts", [])),
        "created": created,
        "links": len(draft.get("links", [])),
        "nodes": len(draft.get("nodes", [])),
    }


def concept_graph(session: Session, course_id: int) -> dict[str, Any]:
    concepts = list(
        session.scalars(
            select(Concept)
            .where(Concept.course_id == course_id)
            .order_by(Concept.name)
        )
    )
    by_id = {concept.id: concept for concept in concepts}
    links = list(
        session.scalars(select(ConceptLink).where(ConceptLink.course_id == course_id))
    )
    node_rows = session.execute(
        select(NodeConcept, TreeNode)
        .join(TreeNode, TreeNode.id == NodeConcept.node_id)
        .where(TreeNode.course_id == course_id)
    ).all()
    coverage: dict[int, list[dict[str, Any]]] = {}
    for row in node_rows:
        node_concept, node = row
        coverage.setdefault(node_concept.concept_id, []).append(
            {"node_id": node.id, "node_title": node.title}
        )
    return {
        "concepts": [
            {
                "id": concept.id,
                "name": concept.name,
                "description": concept.description,
                "aliases": concept.aliases or [],
                "nodes": coverage.get(concept.id, []),
            }
            for concept in concepts
        ],
        "links": [
            {
                "from": by_id[link.from_concept_id].name
                if link.from_concept_id in by_id
                else None,
                "to": by_id[link.to_concept_id].name
                if link.to_concept_id in by_id
                else None,
                "relation": link.relation,
            }
            for link in links
            if link.from_concept_id in by_id and link.to_concept_id in by_id
        ],
    }
