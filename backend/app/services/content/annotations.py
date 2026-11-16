from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import AnchorKind, AnchorSource
from ...domain.anchors import AnchorPayloadError, normalize_quote, validate_anchor
from ...domain.models import DocumentAnchor, Extraction, Material, utcnow
from ...domain.payloads import AnchorPayload


class AnchorNotFound(LookupError):
    pass


class AnchorConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class QuoteMatch:
    start: int
    end: int
    occurrence: int


def _normalized_with_map(text: str) -> tuple[str, list[int]]:
    characters: list[str] = []
    origin: list[int] = []
    pending_space = False
    for index, character in enumerate(text):
        if character.isspace():
            pending_space = bool(characters)
            continue
        if pending_space:
            characters.append(" ")
            origin.append(index)
            pending_space = False
        characters.append(character)
        origin.append(index)
    return "".join(characters), origin


def find_quote(markdown: str, quote: str, occurrence: int = 0) -> QuoteMatch | None:
    needle = normalize_quote(quote)
    if not needle:
        return None
    haystack, origin = _normalized_with_map(markdown)
    start = -1
    for _ in range(occurrence + 1):
        start = haystack.find(needle, start + 1)
        if start < 0:
            return None
    end = start + len(needle)
    if origin:
        original_start = origin[start]
        original_end = origin[end - 1] + 1
    else:
        original_start, original_end = 0, 0
    return QuoteMatch(start=original_start, end=original_end, occurrence=occurrence)


def latest_extraction(session: Session, material_id: str) -> Extraction | None:
    return session.scalar(
        select(Extraction)
        .where(Extraction.material_id == material_id)
        .order_by(Extraction.version.desc())
        .limit(1)
    )


def _material(session: Session, material_id: str, profile_id: str) -> Material:
    material = session.get(Material, material_id)
    if material is None or material.profile_id != profile_id:
        raise AnchorNotFound("material not found")
    return material


def create_anchor(
    session: Session,
    *,
    profile_id: str,
    material_id: str,
    anchor_kind: str,
    quote: str | None,
    payload: dict[str, Any],
    page: int | None = None,
    color: str = "yellow",
    note_md: str | None = None,
    source: str = AnchorSource.USER.value,
) -> DocumentAnchor:
    _material(session, material_id, profile_id)
    try:
        kind = AnchorKind(anchor_kind)
    except ValueError:
        raise AnchorPayloadError(f"unknown anchor kind '{anchor_kind}'") from None
    if kind is AnchorKind.TEXT_RANGE:
        if not quote or not quote.strip():
            raise AnchorPayloadError("a text highlight needs a quote")
        extraction = latest_extraction(session, material_id)
        if extraction is None:
            raise AnchorConflict("material has no extraction to anchor")
        requested_version = payload.get("version_id")
        if requested_version not in (None, extraction.id):
            raise AnchorConflict("anchor targets a stale extraction version")
        occurrence = payload.get("occurrence", 0)
        if not isinstance(occurrence, int) or occurrence < 0:
            occurrence = 0
        match = find_quote(extraction.markdown, quote, occurrence)
        if match is None:
            raise AnchorPayloadError("quote was not found in the current extraction")
        payload = {
            "version_id": extraction.id,
            "start": match.start,
            "end": match.end,
            "occurrence": match.occurrence,
        }
        page = None
    try:
        validated = validate_anchor(kind, payload)
    except AnchorPayloadError:
        raise
    if page is not None and page < 1:
        raise AnchorPayloadError("page must be positive")
    try:
        anchor_source = AnchorSource(source)
    except ValueError:
        raise AnchorPayloadError(f"unknown anchor source '{source}'") from None
    anchor = DocumentAnchor(
        profile_id=profile_id,
        material_id=material_id,
        anchor_kind=kind.value,
        page=page if kind is not AnchorKind.TEXT_RANGE else None,
        quote=normalize_quote(quote) if quote else None,
        payload=validated,
        color=color,
        note_md=note_md,
        source=anchor_source.value,
    )
    session.add(anchor)
    session.flush()
    return anchor


def list_anchors(
    session: Session,
    *,
    profile_id: str,
    material_id: str,
    include_orphaned: bool = True,
) -> list[DocumentAnchor]:
    statement = select(DocumentAnchor).where(
        DocumentAnchor.profile_id == profile_id,
        DocumentAnchor.material_id == material_id,
    )
    if not include_orphaned:
        statement = statement.where(DocumentAnchor.orphaned_at.is_(None))
    return list(
        session.scalars(
            statement.order_by(
                DocumentAnchor.page.asc().nulls_last(),
                DocumentAnchor.created_at,
                DocumentAnchor.id,
            )
        )
    )


def get_anchor(session: Session, *, profile_id: str, anchor_id: str) -> DocumentAnchor:
    anchor = session.get(DocumentAnchor, anchor_id)
    if anchor is None or anchor.profile_id != profile_id:
        raise AnchorNotFound("anchor not found")
    return anchor


def update_anchor(
    session: Session,
    *,
    profile_id: str,
    anchor_id: str,
    color: str | None = None,
    note_md: str | None = None,
    payload: dict[str, Any] | None = None,
) -> DocumentAnchor:
    anchor = get_anchor(session, profile_id=profile_id, anchor_id=anchor_id)
    kind = AnchorKind(anchor.anchor_kind)
    if payload is not None:
        anchor.payload = validate_anchor(kind, payload)
    if color is not None:
        anchor.color = color
    if note_md is not None:
        anchor.note_md = note_md
    anchor.updated_at = utcnow()
    session.flush()
    return anchor


def delete_anchor(session: Session, *, profile_id: str, anchor_id: str) -> None:
    anchor = get_anchor(session, profile_id=profile_id, anchor_id=anchor_id)
    session.delete(anchor)
    session.flush()


def reanchor_material(session: Session, material_id: str) -> int:
    extraction = latest_extraction(session, material_id)
    if extraction is None:
        return 0
    changed = 0
    anchors = session.scalars(
        select(DocumentAnchor).where(
            DocumentAnchor.material_id == material_id,
            DocumentAnchor.anchor_kind.in_(
                [AnchorKind.TEXT_RANGE.value, AnchorKind.PDF_QUAD.value]
            ),
        )
    )
    for anchor in anchors:
        if not anchor.quote:
            continue
        payload = dict(anchor.payload or {})
        occurrence = payload.get("occurrence", 0)
        if not isinstance(occurrence, int) or occurrence < 0:
            occurrence = 0
        match = find_quote(extraction.markdown, anchor.quote, occurrence)
        if match is None:
            if anchor.orphaned_at is None:
                anchor.orphaned_at = utcnow()
                changed += 1
            continue
        payload.update(
            version_id=extraction.id,
            start=match.start,
            end=match.end,
            occurrence=match.occurrence,
        )
        anchor.payload = cast(AnchorPayload, payload)
        anchor.orphaned_at = None
        anchor.updated_at = utcnow()
        changed += 1
    session.flush()
    return changed
