"""The one notification funnel (plan 51 Q3c3a).

Study's bell/aggregate is the delivery surface; retrieval alerts need a
durable, deduped event row so a restart cannot re-spam an admin and so a
recovered condition can release its key. This module is that store's only
write seam — every emitter calls :meth:`NotificationService.emit`, exactly
like the family's NotificationService rule (ADR-0044 §6). There is no second
delivery path.

Kinds are boot-seeded from the closed :class:`NotificationKind` vocabulary and
the vendored contract's :data:`ALERT_DEFAULTS` (thresholds/windows/dedup
scopes/daily caps). Alert payloads carry ids, counts, scores and reasons only;
the contract's :func:`assert_no_raw_text` is applied by the alert evaluator.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.vocab import NotificationKind, NotificationSeverity
from ...domain.models import Notification, NotificationKindRow, User
from ...storage.retrieval_ops import ALERT_DEFAULTS, AlertDefault, assert_no_raw_text

RETRIEVAL_INDEXING_URL = "/settings?tab=tools&section=indexing"
RETRIEVAL_AI_TASKS_URL = "/settings?tab=ai&section=tasks"

KIND_TITLES: dict[str, str] = {
    NotificationKind.RETRIEVAL_COVERAGE_LOW.value: "Retrieval coverage below gate",
    NotificationKind.RETRIEVAL_REINDEX_FAILED.value: "Retrieval reindex failed",
    NotificationKind.RETRIEVAL_REINDEX_STALLED.value: "Retrieval reindex stalled",
    NotificationKind.RETRIEVAL_QUALITY_GATE.value: "Retrieval quality below floor",
    NotificationKind.RETRIEVAL_QUERY_SLO.value: "Retrieval query latency above budget",
    NotificationKind.RETRIEVAL_DEGRADED_RATE.value: "Retrieval degraded query share high",
    NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value: "Embeddings provider not assigned",
    NotificationKind.RETRIEVAL_INDEX_MISSING.value: "Retrieval index missing",
    NotificationKind.RETRIEVAL_BUDGET_EXHAUSTED.value: "Embedding token budget exhausted",
    NotificationKind.RETRIEVAL_SPACE_DROP_PENDING.value: "Retired retrieval space waiting to drop",
}

# Study ships the retrieval controls inside Tools -> Indexing (plan 51 Q3b),
# so every alert resolves to that real page, never career's Audit -> Retrieval
# route. The run id still travels in the payload and as a `detail` query hint.
MANAGE_URLS: dict[str, str] = dict.fromkeys(KIND_TITLES, RETRIEVAL_INDEXING_URL)
MANAGE_URLS[NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value] = RETRIEVAL_AI_TASKS_URL
MANAGE_URLS[NotificationKind.RETRIEVAL_BUDGET_EXHAUSTED.value] = RETRIEVAL_AI_TASKS_URL

KIND_DEFAULTS: dict[str, AlertDefault] = {row.kind: row for row in ALERT_DEFAULTS}
DEFAULT_DEDUP_TTL_DAYS = 7
ADMIN_FANOUT_LIMIT = 20


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    moment = _as_utc(value)
    return moment.isoformat().replace("+00:00", "Z") if moment is not None else None


def manage_url(kind: str, *, run_id: str | None = None) -> str:
    """The real shipped managing page for a kind (never a redirect)."""
    base = MANAGE_URLS.get(kind, RETRIEVAL_INDEXING_URL)
    if run_id is None:
        return base
    return f"{base}&detail={run_id}"


def seed_notification_kinds(session: Session) -> int:
    """Idempotently register every closed kind; returns rows inserted."""
    existing = set(session.scalars(select(NotificationKindRow.key)))
    inserted = 0
    for kind in NotificationKind:
        if kind.value in existing:
            continue
        default = KIND_DEFAULTS.get(kind.value)
        session.add(
            NotificationKindRow(
                key=kind.value,
                title=KIND_TITLES[kind.value],
                description=default.condition if default is not None else "",
                severity=NotificationSeverity.WARNING.value,
                admin_only=True,
                default_enabled=True,
            )
        )
        inserted += 1
    if inserted:
        session.flush()
    return inserted


def _kind_row(session: Session, kind: str) -> NotificationKindRow | None:
    row = session.get(NotificationKindRow, kind)
    if row is not None:
        return row
    if kind not in {member.value for member in NotificationKind}:
        return None
    seed_notification_kinds(session)
    return session.get(NotificationKindRow, kind)


def admin_recipients(session: Session) -> list[str]:
    """Bounded admin fanout (the family's `admins[:20]` precedent)."""
    rows = session.scalars(
        select(User.id)
        .where(User.is_admin.is_(True), User.is_active.is_(True))
        .order_by(User.created_at, User.id)
        .limit(ADMIN_FANOUT_LIMIT)
    )
    return [str(value) for value in rows]


class NotificationService:
    """Emit one deduped event to admin recipients; the only write seam."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def emit(
        self,
        kind: str | NotificationKind,
        recipients: Sequence[str],
        *,
        title: str,
        body: str = "",
        payload: Mapping[str, Any] | None = None,
        source_ref: Mapping[str, Any] | None = None,
        dedup_key: str | None = None,
        dedup_ttl_days: int | None = None,
        max_per_day: int | None = None,
        severity: str | None = None,
        now: datetime | None = None,
    ) -> Notification | None:
        """Write the event, or return None when suppressed.

        Suppression is fail-soft: an unregistered kind, an empty recipient
        list, an active dedup key or today's cap all mean "notify nobody".
        """
        key = kind.value if isinstance(kind, NotificationKind) else str(kind)
        kind_row = _kind_row(self.session, key)
        if kind_row is None or not kind_row.default_enabled:
            return None
        targets = list(dict.fromkeys(str(value) for value in recipients if value))
        if not targets:
            return None
        moment = _as_utc(now) or _utcnow()
        if dedup_key is not None:
            existing = self.session.scalars(
                select(Notification.id).where(
                    Notification.dedup_key == dedup_key,
                    Notification.dedup_expires_at > moment,
                )
            ).first()
            if existing is not None:
                return None
        if max_per_day is not None and max_per_day > 0:
            day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
            used = self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.kind == key, Notification.created_at >= day_start)
            )
            if int(used or 0) >= int(max_per_day):
                return None
        row = Notification(
            kind=key,
            severity=severity or kind_row.severity,
            title=title[:200],
            body=body,
            payload=assert_no_raw_text(dict(payload or {})),
            source_ref=dict(source_ref) if source_ref is not None else None,
            recipients=targets,
            dedup_key=dedup_key,
            dedup_expires_at=(
                moment + timedelta(days=dedup_ttl_days or DEFAULT_DEDUP_TTL_DAYS)
                if dedup_key is not None
                else None
            ),
            created_at=moment,
        )
        self.session.add(row)
        self.session.flush()
        return row


def active_alerts(
    session: Session, user_id: str | None, *, limit: int = 20
) -> list[dict[str, Any]]:
    """The current user's still-active alerts for the existing bell aggregate."""
    if not user_id:
        return []
    now = _utcnow()
    rows = session.scalars(
        select(Notification)
        .where(
            Notification.dedup_key.is_not(None),
            Notification.dedup_expires_at > now,
        )
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(max(1, min(limit, 50)))
    ).all()
    return [
        {
            "id": str(row.id),
            "kind": str(row.kind),
            "severity": str(row.severity),
            "title": str(row.title),
            "body": str(row.body),
            "link": str((row.payload or {}).get("link") or RETRIEVAL_INDEXING_URL),
            "created_at": _iso(row.created_at),
        }
        for row in rows
        if user_id in {str(value) for value in (row.recipients or [])}
    ]


def _iter_defaults() -> Iterable[AlertDefault]:
    return ALERT_DEFAULTS


__all__ = [
    "ADMIN_FANOUT_LIMIT",
    "KIND_DEFAULTS",
    "KIND_TITLES",
    "MANAGE_URLS",
    "RETRIEVAL_AI_TASKS_URL",
    "RETRIEVAL_INDEXING_URL",
    "NotificationService",
    "active_alerts",
    "admin_recipients",
    "manage_url",
    "seed_notification_kinds",
]
