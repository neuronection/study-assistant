from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import StudySessionKind, StudySessionSource
from ...domain.models import StudySession, utcnow

HEARTBEAT_SEC = 60
RESUME_WINDOW_SEC = 120
END_GRACE_SEC = 120
MAX_SESSION_SEC = 12 * 3600


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _clamped_duration(started_at: datetime, ended_at: datetime) -> int:
    seconds = int((_aware(ended_at) - _aware(started_at)).total_seconds())
    return max(0, min(seconds, MAX_SESSION_SEC))


def start_session(
    session: Session,
    profile_id: int,
    *,
    kind: StudySessionKind,
    source: StudySessionSource,
    course_id: int | None = None,
    node_id: int | None = None,
    entity_ref: str | None = None,
) -> StudySession:
    now = utcnow()
    if entity_ref is not None and source == StudySessionSource.AUTO:
        resumable = session.scalar(
            select(StudySession)
            .where(
                StudySession.profile_id == profile_id,
                StudySession.kind == kind.value,
                StudySession.source == StudySessionSource.AUTO.value,
                StudySession.entity_ref == entity_ref,
                StudySession.ended_at.is_not(None),
                StudySession.ended_at >= now - timedelta(seconds=RESUME_WINDOW_SEC),
            )
            .order_by(StudySession.id.desc())
            .limit(1)
        )
        if resumable is not None:
            resumable.last_beat = now
            resumable.ended_at = now
            resumable.duration_sec = _clamped_duration(
                resumable.started_at, resumable.ended_at
            )
            session.flush()
            return resumable
    row = StudySession(
        profile_id=profile_id,
        course_id=course_id,
        node_id=node_id,
        kind=kind.value,
        source=source.value,
        entity_ref=entity_ref,
        started_at=now,
        ended_at=now,
        last_beat=now,
        duration_sec=0,
    )
    session.add(row)
    session.flush()
    return row


def beat_session(
    session: Session, row: StudySession, *, end: bool = False
) -> StudySession:
    now = utcnow()
    last_beat = _aware(row.last_beat)
    effective_end = min(_aware(now), last_beat + timedelta(seconds=END_GRACE_SEC))
    row.last_beat = now
    row.ended_at = effective_end
    row.duration_sec = _clamped_duration(row.started_at, effective_end)
    if end:
        row.last_beat = effective_end
    session.flush()
    return row


def session_summary(session: Session, profile_id: int, days: int) -> dict[str, Any]:
    horizon_start = (utcnow() - timedelta(days=max(1, min(days, 365)))).date()
    rows = session.execute(
        select(
            StudySession.started_at,
            StudySession.kind,
            StudySession.duration_sec,
        )
        .where(
            StudySession.profile_id == profile_id,
            StudySession.started_at >= horizon_start,
        )
        .order_by(StudySession.started_at)
    ).all()
    per_day: dict[str, dict[str, Any]] = {}
    for started_at, kind, duration_sec in rows:
        key = _aware(started_at).date().isoformat()
        entry = per_day.setdefault(key, {"total_sec": 0, "by_kind": {}})
        entry["total_sec"] += int(duration_sec or 0)
        kind_key = str(kind)
        entry["by_kind"][kind_key] = entry["by_kind"].get(kind_key, 0) + int(
            duration_sec or 0
        )
    day_list = [
        {"day": key, "total_sec": entry["total_sec"], "by_kind": entry["by_kind"]}
        for key, entry in sorted(per_day.items())
    ]
    week_sec = sum(entry["total_sec"] for entry in day_list[-7:])
    today_key = utcnow().date().isoformat()
    today_sec = next(
        (entry["total_sec"] for entry in day_list if entry["day"] == today_key), 0
    )
    return {"days": day_list, "today_sec": today_sec, "week_sec": week_sec}
