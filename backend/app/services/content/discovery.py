"""Discovery suggestion tracking: found URLs worth keeping (plan 73-D).

A suggestion is a pointer, not study content: the table tracks what was
found (status `suggested` by future scans), saved for later, attached to a
material, or dismissed. One row per (profile, normalized URL).
"""

from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...core.urls import normalize_url
from ...core.vocab import DiscoveryKind, SuggestionStatus
from ...domain.models import Course, Material, MaterialSuggestion

MAX_TITLE = 300
MAX_SNIPPET = 2000
MAX_PROVIDER = 100


class SuggestionError(ValueError):
    pass


def _validated_url(url: str) -> tuple[str, str]:
    text = (url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SuggestionError("expecting an http(s) URL")
    return text[:2048], normalize_url(text)[:2048]


def _validated_kind(kind: str | None) -> str:
    if kind is None or kind == "":
        return DiscoveryKind.ARTICLE.value
    return DiscoveryKind.parse(kind)


def _validated_placement(
    session: Session,
    profile_id: int,
    course_id: int | None,
    node_id: int | None,
) -> tuple[int | None, int | None]:
    if node_id is not None and course_id is None:
        raise SuggestionError("node placement requires a course")
    if course_id is not None:
        course = session.get(Course, course_id)
        if course is None or course.profile_id != profile_id:
            raise SuggestionError("course not found")
    if node_id is not None:
        from ..knowledge.tree import TreeError, TreeService

        try:
            node_id = TreeService(session).placement_node(course_id, node_id)
        except TreeError as error:
            raise SuggestionError(str(error)) from error
    return course_id, node_id


def save_suggestion(
    session: Session,
    profile_id: int,
    *,
    provider: str,
    url: str,
    title: str,
    snippet: str | None = None,
    kind: str | None = None,
    meta: dict[str, Any] | None = None,
    course_id: int | None = None,
    node_id: int | None = None,
) -> tuple[MaterialSuggestion, bool]:
    raw_url, url_norm = _validated_url(url)
    kind_value = _validated_kind(kind)
    course_id, node_id = _validated_placement(
        session, profile_id, course_id, node_id
    )
    display_title = (title or "").strip()
    if not display_title:
        raise SuggestionError("title cannot be empty")
    existing = session.scalars(
        select(MaterialSuggestion).where(
            MaterialSuggestion.profile_id == profile_id,
            MaterialSuggestion.url_norm == url_norm,
        )
    ).first()
    if existing is not None:
        existing.provider = (provider or "").strip()[:MAX_PROVIDER] or "web"
        existing.title = display_title[:MAX_TITLE]
        existing.snippet = (snippet or "").strip()[:MAX_SNIPPET] or None
        existing.kind = kind_value
        existing.meta = meta if isinstance(meta, dict) else existing.meta
        if existing.course_id is None:
            existing.course_id = course_id
            existing.node_id = node_id
        session.flush()
        return existing, False
    row = MaterialSuggestion(
        profile_id=profile_id,
        course_id=course_id,
        node_id=node_id,
        provider=(provider or "").strip()[:MAX_PROVIDER] or "web",
        url=raw_url,
        url_norm=url_norm,
        title=display_title[:MAX_TITLE],
        snippet=(snippet or "").strip()[:MAX_SNIPPET] or None,
        kind=kind_value,
        meta=meta if isinstance(meta, dict) else None,
        status=SuggestionStatus.SAVED.value,
    )
    session.add(row)
    session.flush()
    return row, True


def list_suggestions(
    session: Session,
    profile_id: int,
    *,
    course_id: int | None = None,
    node_id: int | None = None,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    cursor: int | None = None,
) -> tuple[list[MaterialSuggestion], int | None]:
    stmt = select(MaterialSuggestion).where(
        MaterialSuggestion.profile_id == profile_id
    )
    if course_id is not None:
        stmt = stmt.where(MaterialSuggestion.course_id == course_id)
    if node_id is not None:
        stmt = stmt.where(MaterialSuggestion.node_id == node_id)
    if status is not None:
        stmt = stmt.where(MaterialSuggestion.status == status)
    if kind is not None:
        stmt = stmt.where(MaterialSuggestion.kind == kind)
    if cursor is not None:
        stmt = stmt.where(MaterialSuggestion.id < cursor)
    stmt = stmt.order_by(MaterialSuggestion.id.desc())
    rows = list(session.scalars(stmt.limit(limit + 1)))
    next_cursor: int | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = rows[-1].id
    return rows, next_cursor


def get_suggestion(
    session: Session, profile_id: int, suggestion_id: int
) -> MaterialSuggestion | None:
    row = session.get(MaterialSuggestion, suggestion_id)
    if row is None or row.profile_id != profile_id:
        return None
    return row


def forget_suggestion(
    session: Session, profile_id: int, suggestion_id: int
) -> None:
    row = get_suggestion(session, profile_id, suggestion_id)
    if row is None:
        raise SuggestionError("suggestion not found")
    session.delete(row)
    session.flush()


def update_suggestion(
    session: Session,
    profile_id: int,
    suggestion_id: int,
    *,
    status: str | None = None,
    material_id: int | None = None,
    node_id: int | None = None,
) -> MaterialSuggestion:
    row = get_suggestion(session, profile_id, suggestion_id)
    if row is None:
        raise SuggestionError("suggestion not found")
    if status is not None:
        parsed = SuggestionStatus.parse(status)
        row.status = parsed.value
        if parsed is not SuggestionStatus.SAVED:
            row.material_id = None
    if material_id is not None:
        material = session.get(Material, material_id)
        if material is None or material.profile_id != profile_id:
            raise SuggestionError("material not found")
        if row.course_id is not None and material.course_id != row.course_id:
            raise SuggestionError("material belongs to a different course")
        row.material_id = material.id
        row.status = SuggestionStatus.SAVED.value
    if node_id is not None:
        _, resolved_node = _validated_placement(
            session, profile_id, row.course_id, node_id
        )
        row.node_id = resolved_node
    session.flush()
    return row


def revert_suggestions_for_material(session: Session, material_id: int) -> None:
    session.execute(
        update(MaterialSuggestion)
        .where(MaterialSuggestion.material_id == material_id)
        .values(
            material_id=None, status=SuggestionStatus.SUGGESTED.value
        )
    )


def suggestion_states_for_urls(
    session: Session, profile_id: int, urls: list[str]
) -> dict[str, MaterialSuggestion]:
    norm_by_url = {url: normalize_url(url) for url in urls if url}
    norms = {norm for norm in norm_by_url.values() if norm}
    if not norms:
        return {}
    rows = session.scalars(
        select(MaterialSuggestion).where(
            MaterialSuggestion.profile_id == profile_id,
            MaterialSuggestion.url_norm.in_(norms),
        )
    )
    by_norm = {row.url_norm: row for row in rows}
    return {url: by_norm[norm] for url, norm in norm_by_url.items() if norm in by_norm}
