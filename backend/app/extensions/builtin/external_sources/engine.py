"""The provider-agnostic reconciliation engine (plan 86 A, ADR-214)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....core.vocab import DiscoveryKind, MaterialStatus
from ....domain.models import (
    Exercise,
    ExternalReviewEvent,
    ExternalSource,
    FsrsState,
    Material,
    MaterialSuggestion,
    utcnow,
)
from ....domain.payloads import SuggestionMeta
from ....scheduling import fsrs
from ...errors import ExtensionError
from .adapters import build_adapter
from .adapters.anki import AnkiAdapter
from .adapters.base import RemoteEntry, discovery_kind_for, is_media, material_kind_for
from .providers import provider_for_kind, validate_registration

MAX_ENTRY_BYTES = 200 * 1024 * 1024
MEDIA_SIZE_CAP = 200 * 1024 * 1024


@dataclass
class Reconciled:
    stats: dict[str, int]
    suggestions: list[MaterialSuggestion]


def _suggestion_meta(source: ExternalSource, entry: RemoteEntry) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "source_id": source.id,
        "remote_id": entry.remote_id,
        "remote_name": entry.name,
        "mime": entry.mime,
    }
    for key, value in entry.meta.items():
        if value is not None:
            meta[key] = value
    material_kind = entry.meta.get("material_kind") or material_kind_for(entry.name, entry.mime)
    if material_kind:
        meta["material_kind"] = material_kind
    if entry.size is not None:
        meta["size"] = entry.size
    return meta


def _vanished(
    session: Session, source: ExternalSource, cursor: dict[str, Any], ids: list[str]
) -> int:
    known_raw = cursor.get("known")
    known: dict[str, dict[str, Any]] = known_raw if isinstance(known_raw, dict) else {}
    urls: list[str] = []
    for remote_id in ids:
        row = known.get(remote_id)
        if isinstance(row, dict) and row.get("url"):
            urls.append(str(row["url"]))
    if not urls:
        return 0
    from ....core.urls import normalize_url

    norms = {normalize_url(url) for url in urls}
    rows = session.scalars(
        select(MaterialSuggestion).where(
            MaterialSuggestion.profile_id == source.profile_id,
            MaterialSuggestion.url_norm.in_(norms),
        )
    )
    marked = 0
    for suggestion in rows:
        meta_doc = dict(suggestion.meta or {})
        if meta_doc.get("source_id") != source.id:
            continue
        meta_doc["remote_state"] = "vanished"
        suggestion.meta = cast(SuggestionMeta, meta_doc)
        marked += 1
        if suggestion.material_id:
            material = session.get(Material, suggestion.material_id)
            if material is not None:
                material.status = MaterialStatus.MISSING.value
    return marked


def reconcile(
    session: Session,
    source: ExternalSource,
    record: Any,
    *,
    transport: Any = None,
    adapter: Any = None,
) -> dict[str, int]:
    provider_id = source.provider or provider_for_kind(source.kind)
    provider = validate_registration(provider_id, source.kind, source.auth_kind)
    built = adapter or build_adapter(provider_id, transport)
    probe = built.auth_probe(source)
    if probe == "needs-config":
        raise ExtensionError(
            "needs-secret",
            f"{provider.label} is not connected yet — add its credentials first",
        )
    if probe == "expired":
        raise ExtensionError("auth", f"{provider.label} credentials expired — reconnect")
    if isinstance(built, AnkiAdapter):
        return sync_anki_reviews(session, source, built)

    cursor = source.cursor if isinstance(source.cursor, dict) else {}
    changes = built.changes(source, cursor)
    stats = {"new": 0, "updated": 0, "unchanged": 0, "missing": 0, "skipped": 0}
    max_items = 0
    options = source.options if isinstance(source.options, dict) else {}
    raw_max = options.get("max_items")
    if isinstance(raw_max, int) and 1 <= raw_max <= 100:
        max_items = raw_max
    upserted = changes.upserted[:max_items] if max_items else changes.upserted
    next_cursor = dict(changes.cursor)
    known_raw = next_cursor.get("known")
    known: dict[str, dict[str, Any]] = known_raw if isinstance(known_raw, dict) else {}
    for entry in upserted:
        if (
            entry.size is not None
            and entry.size > MEDIA_SIZE_CAP
            and is_media(entry.name, entry.mime)
        ):
            stats["skipped"] += 1
            continue
        kind = entry.kind or discovery_kind_for(entry.name, entry.mime)
        meta = _suggestion_meta(source, entry)
        try:
            outcome = record(
                session,
                source.profile_id,
                provider=f"{source.provider}:{source.label or provider.label}",
                url=entry.url,
                title=entry.title or entry.name,
                snippet=None,
                kind=kind,
                meta=meta,
                course_id=source.course_id,
            )
        except Exception as error:
            if isinstance(error, ExtensionError):
                raise
            stats["skipped"] += 1
            continue
        if outcome == "created":
            stats["new"] += 1
        elif outcome == "updated":
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1
        known[entry.remote_id] = {
            "fingerprint": entry.fingerprint(),
            "name": entry.name,
            "url": entry.url,
        }
    if changes.vanished:
        stats["missing"] = _vanished(session, source, cursor, changes.vanished)
    next_cursor["known"] = known
    source.cursor = next_cursor
    source.last_scanned_at = utcnow()
    source.last_scan_error = None
    source.consecutive_failures = 0
    return stats


def fetch_entry(source: ExternalSource, entry: RemoteEntry, *, transport: Any = None) -> bytes:
    if entry.size is not None and entry.size > MAX_ENTRY_BYTES:
        raise ExtensionError("invalid", f"entry is too large to import ({entry.size} bytes)")
    adapter = build_adapter(source.provider, transport)
    data: bytes = adapter.fetch(source, entry)
    if len(data) > MAX_ENTRY_BYTES:
        raise ExtensionError("invalid", "entry is too large to import")
    return data


def sync_anki_reviews(
    session: Session,
    source: ExternalSource,
    adapter: AnkiAdapter | None = None,
) -> dict[str, int]:
    built = adapter or AnkiAdapter()
    events = built.reviews(source)
    stats = {
        "new": 0,
        "merged": 0,
        "unchanged": 0,
        "unmatched": 0,
        "recomputed": 0,
        "skipped": 0,
    }
    seen: set[tuple[str, Any]] = set()
    for event in events:
        reviewed_at = _parse_time(event["reviewed_at"])
        key = (str(event["remote_card_id"]), reviewed_at)
        if key in seen:
            stats["skipped"] += 1
            continue
        seen.add(key)
        existing = session.scalars(
            select(ExternalReviewEvent).where(
                ExternalReviewEvent.source_id == source.id,
                ExternalReviewEvent.remote_card_id == key[0],
                ExternalReviewEvent.reviewed_at == reviewed_at,
            )
        ).first()
        if existing is not None:
            stats["unchanged"] += 1
            continue
        session.add(
            ExternalReviewEvent(
                source_id=source.id,
                remote_card_id=key[0],
                reviewed_at=reviewed_at,
                rating=int(event["rating"]),
                interval_days=float(event["interval_days"]),
                elapsed_days=float(event["elapsed_days"]),
            )
        )
        stats["new"] += 1
    session.flush()
    remote_ids = {str(event["remote_card_id"]) for event in events}
    for remote_id in remote_ids:
        cards = list(
            session.scalars(
                select(Exercise).where(
                    Exercise.profile_id == source.profile_id,
                    Exercise.external_uid == remote_id,
                )
            )
        )
        if not cards:
            stats["unmatched"] += 1
            continue
        for card in cards:
            recompute_card(session, card, remote_id)
            stats["recomputed"] += 1
    stats["merged"] = stats["new"]
    source.last_scanned_at = utcnow()
    source.last_scan_error = None
    source.consecutive_failures = 0
    return stats


def recompute_card(session: Session, card: Exercise, remote_id: str) -> FsrsState:
    events = list(
        session.scalars(
            select(ExternalReviewEvent)
            .where(ExternalReviewEvent.remote_card_id == remote_id)
            .order_by(ExternalReviewEvent.reviewed_at, ExternalReviewEvent.id)
        )
    )
    stability: float | None = None
    difficulty: float | None = None
    reps = 0
    lapses = 0
    last_review_at: Any = None
    due_at: Any = None
    state_name = "new"
    for event in events:
        prior = fsrs.FsrsCard(
            stability=stability,
            difficulty=difficulty,
            reps=reps,
            lapses=lapses,
            last_review_at=last_review_at,
        )
        outcome = fsrs.review(prior, int(event.rating), event.reviewed_at)
        stability = outcome.stability
        difficulty = outcome.difficulty
        state_name = outcome.state
        reps += 1
        if int(event.rating) == fsrs.RATING_AGAIN:
            lapses += 1
        last_review_at = event.reviewed_at
        due_at = fsrs.due_date(event.reviewed_at, int(outcome.interval_days))
    row = session.scalars(select(FsrsState).where(FsrsState.card_id == card.id)).first()
    if row is None:
        row = FsrsState(card_id=card.id, due_at=due_at or utcnow())
        session.add(row)
    row.stability = stability
    row.difficulty = difficulty
    row.state = state_name
    row.reps = reps
    row.lapses = lapses
    row.last_review_at = last_review_at
    if due_at is not None:
        row.due_at = due_at
    session.flush()
    return row


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


def entry_from_suggestion(suggestion: MaterialSuggestion) -> RemoteEntry:
    meta = suggestion.meta if isinstance(suggestion.meta, dict) else {}
    remote_id = str(meta.get("remote_id") or suggestion.url)
    name = str(meta.get("remote_name") or suggestion.title)
    mime = str(meta.get("mime") or "") or None
    size_raw = meta.get("size")
    size = int(size_raw) if isinstance(size_raw, int) else None
    kind = str(meta.get("discovery_kind") or "") or None
    attachment = str(meta.get("attachment_url") or "")
    return RemoteEntry(
        remote_id=remote_id,
        name=name,
        url=attachment or suggestion.url,
        mime=mime,
        size=size,
        kind=kind if kind in {member.value for member in DiscoveryKind} else None,
        meta={
            key: value
            for key, value in meta.items()
            if key
            in {
                "citation_kind",
                "authors",
                "year",
                "doi",
                "container",
                "material_kind",
                "attachment_url",
                "remote_state",
            }
        },
    )


def is_remote_url(url: str) -> bool:
    return urlparse(url).scheme in ("http", "https")
