"""Idempotency, the single-active-run lock and the stale-heartbeat reaper.

Plan 51 Q3b runtime over the migration's ``jobs.idempotency_key`` /
``jobs.lock_key`` / ``jobs.heartbeat_at`` columns. Only ``VECTOR_*`` rows are
touched — the generic ``JobRunner.enqueue`` contract stays unchanged for every
other job family.

Semantics:

* an action replayed with the same ``Idempotency-Key`` and the same payload
  returns the original row (inside the contract's 24 hour window); the same
  key with a different payload is a conflict;
* a new bulk run holds ``lock_key = vector_space:<space>``; the partial unique
  index over queued/running is the database-level one-active-run invariant;
* a ``running`` vector row whose heartbeat is older than the contract's stale
  window is failed by :func:`reap_stale_runs`, releasing the lock and writing
  ``vector.run.stalled`` — a crash never blocks the space until restart.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.vocab import JobStatus, JobType
from ...domain.models import AuditEvent as AuditEventRow
from ...domain.models import Job
from ...jobs.payloads import JobResult
from ...storage.retrieval_ops import (
    HEARTBEAT_STALE_SECONDS,
    IDEMPOTENCY_TTL_SECONDS,
    VECTOR_JOB_TYPES,
    run_lock_key,
    validate_idempotency_key,
)
from .audit import build_vector_event, run_resource
from .legacy import LEGACY_SPACE_ID

logger = structlog.get_logger(__name__)

ACTIVE_STATUSES = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
LOCKED_JOB_TYPES = frozenset(
    {
        JobType.VECTOR_REINDEX.value,
        JobType.VECTOR_MAINTENANCE.value,
        JobType.VECTOR_CUTOVER.value,
    }
)
REAPABLE_JOB_TYPES = LOCKED_JOB_TYPES
STALE_ERROR = f"stalled: no heartbeat for {HEARTBEAT_STALE_SECONDS // 60}m"
VECTOR_TYPE_SET = frozenset(VECTOR_JOB_TYPES)


class RetrievalJobConflict(Exception):
    """A replay/lock refusal the router turns into a structured 409."""

    def __init__(
        self,
        message: str,
        *,
        reason: str = "conflict",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.extra = extra or {}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def replay_cutoff(now: datetime | None = None) -> datetime:
    return (now or _utcnow()) - timedelta(seconds=IDEMPOTENCY_TTL_SECONDS)


def validate_key(value: Any) -> str:
    """Validate through the family contract (raises ``ValueError``)."""
    return validate_idempotency_key(value)


def default_lock_key() -> str:
    return run_lock_key(LEGACY_SPACE_ID)


def _canonical(payload: Mapping[str, Any] | None) -> str:
    return json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)


def _same_request(
    left: Mapping[str, Any] | None, right: Mapping[str, Any] | None
) -> bool:
    return _canonical(left) == _canonical(right)


def find_replay(
    session: Session, *, job_type: str, idempotency_key: str
) -> Job | None:
    return session.scalars(
        select(Job)
        .where(
            Job.type == job_type,
            Job.idempotency_key == idempotency_key,
            Job.created_at >= replay_cutoff(),
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    ).first()


def active_run(session: Session, *, lock_key: str | None = None) -> Job | None:
    key = lock_key or default_lock_key()
    return session.scalars(
        select(Job)
        .where(Job.lock_key == key, Job.status.in_(ACTIVE_STATUSES))
        .order_by(Job.created_at)
        .limit(1)
    ).first()


def active_run_for_space(session: Session, space_id: str) -> Job | None:
    return active_run(session, lock_key=run_lock_key(space_id))


def _replay_or_conflict(
    session: Session, *, job_type: str, payload: dict[str, Any], key: str
) -> Job | None:
    existing = find_replay(session, job_type=job_type, idempotency_key=key)
    if existing is None:
        return None
    if not _same_request(existing.payload, payload):
        raise RetrievalJobConflict(
            "this Idempotency-Key was already used with a different request; "
            "use a new key for a new action",
            reason="idempotency_mismatch",
        )
    return existing


def _active_conflict(active: Job) -> RetrievalJobConflict:
    return RetrievalJobConflict(
        f"a vector run is already active ({active.type}, {active.status}); "
        "wait for it to finish or cancel it",
        reason="run_in_progress",
        extra={"active_run_id": active.id, "active_status": active.status},
    )


def _add_audit(
    session: Session,
    audit: AuditEventRow | Sequence[AuditEventRow] | None,
) -> None:
    if audit is None:
        return
    if isinstance(audit, AuditEventRow):
        session.add(audit)
        return
    for event in audit:
        session.add(event)


def enqueue_vector_job(
    session: Session,
    *,
    job_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    audit: AuditEventRow | Sequence[AuditEventRow] | None = None,
    space_id: str | None = None,
) -> tuple[Job, bool]:
    """Queue a vector run with replay and one-active-run semantics."""
    if job_type not in VECTOR_TYPE_SET:
        raise ValueError(f"{job_type!r} is not a vector job type")
    key = validate_key(idempotency_key)
    lock_key = run_lock_key(space_id) if space_id else default_lock_key()
    replay = _replay_or_conflict(
        session, job_type=job_type, payload=payload, key=key
    )
    if replay is not None:
        return replay, True

    active = active_run(session, lock_key=lock_key)
    if active is not None:
        raise _active_conflict(active)

    job = Job(
        type=job_type,
        payload=payload,
        status=JobStatus.QUEUED.value,
        progress=0,
        idempotency_key=key,
        lock_key=lock_key,
    )
    session.add(job)
    _add_audit(session, audit)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        replay = _replay_or_conflict(
            session, job_type=job_type, payload=payload, key=key
        )
        if replay is not None:
            return replay, True
        active = active_run(session, lock_key=lock_key)
        if active is not None:
            raise _active_conflict(active) from None
        raise RetrievalJobConflict(
            "a concurrent retrieval action collided on the same key or space; retry",
            reason="concurrent_action",
        ) from None
    session.refresh(job)
    return job, False


def run_vector_action(
    session: Session,
    *,
    job_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    lock_key: str,
    execute: Callable[[Job], dict[str, Any]],
    audit: AuditEventRow | Sequence[AuditEventRow] | None = None,
    failure_audit: AuditEventRow | None = None,
) -> tuple[dict[str, Any], bool]:
    """Run one short lifecycle action as a real job row (sync, under the lock).

    The row gives the action the same idempotency replay, one-active-run lock
    and audit trail as the queued reindex/maintenance actions. It is never
    visible as ``queued``: it is created ``running`` and finishes in this
    request.
    """
    if job_type not in VECTOR_TYPE_SET:
        raise ValueError(f"{job_type!r} is not a vector job type")
    key = validate_key(idempotency_key)
    replay = _replay_or_conflict(session, job_type=job_type, payload=payload, key=key)
    if replay is not None:
        stored = (
            (replay.result or {}).get("response")
            if isinstance(replay.result, dict)
            else None
        )
        if isinstance(stored, dict):
            return cast(dict[str, Any], stored), True
    active = active_run(session, lock_key=lock_key)
    if active is not None:
        raise _active_conflict(active)
    moment = _utcnow()
    job = Job(
        type=job_type,
        payload=payload,
        status=JobStatus.RUNNING.value,
        progress=1,
        idempotency_key=key,
        lock_key=lock_key,
        started_at=moment,
        heartbeat_at=moment,
    )
    session.add(job)
    _add_audit(session, audit)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        replay = _replay_or_conflict(session, job_type=job_type, payload=payload, key=key)
        if replay is not None:
            stored = (
                (replay.result or {}).get("response")
                if isinstance(replay.result, dict)
                else None
            )
            if isinstance(stored, dict):
                return cast(dict[str, Any], stored), True
        active = active_run(session, lock_key=lock_key)
        if active is not None:
            raise _active_conflict(active) from None
        raise RetrievalJobConflict(
            "a concurrent retrieval action collided on the same key or lock; retry",
            reason="concurrent_action",
        ) from None
    try:
        response = execute(job)
        if isinstance(response, dict):
            response["run_id"] = job.id
    except Exception as error:
        session.rollback()
        failed = session.get(Job, job.id)
        if failed is not None:
            failed.status = JobStatus.FAILED.value
            failed.error = str(error)[:500]
            failed.finished_at = _utcnow()
            failed.lock_key = None
            reason = getattr(error, "reason", None)
            extra = getattr(error, "extra", None)
            if isinstance(reason, str) and isinstance(extra, dict):
                failed.result = cast(
                    JobResult,
                    {
                        "refusal": {
                            "reason": reason,
                            "message": str(error)[:500],
                            **extra,
                        },
                        **extra,
                    },
                )
            if failure_audit is not None:
                session.add(failure_audit)
            session.commit()
        raise
    job = session.get(Job, job.id) or job
    job.status = JobStatus.DONE.value
    job.progress = 100
    job.finished_at = _utcnow()
    job.heartbeat_at = job.finished_at
    job.lock_key = None
    stored = {"response": response}
    for key in (
        "quality_compare",
        "bad_matches",
        "activation_gate",
        "space",
        "gate",
    ):
        if key in response:
            stored[key] = response[key]
    if response.get("quality_compare") is not None:
        stored["quality"] = response["quality_compare"]
    elif response.get("quality") is not None:
        stored["quality"] = response["quality"]
    job.result = cast(JobResult, stored)
    session.commit()
    return response, False


def reap_stale_runs(
    session: Session, *, now: datetime | None = None
) -> list[Job]:
    """Fail running VECTOR_* rows whose heartbeat outlived the stale window."""
    moment = now or _utcnow()
    cutoff = moment - timedelta(seconds=HEARTBEAT_STALE_SECONDS)
    rows = session.scalars(
        select(Job).where(
            Job.type.in_(REAPABLE_JOB_TYPES),
            Job.status == JobStatus.RUNNING.value,
        )
    ).all()
    reaped: list[Job] = []
    for job in rows:
        beat = (
            _as_utc(job.heartbeat_at)
            or _as_utc(job.started_at)
            or _as_utc(job.created_at)
        )
        if beat is None or beat >= cutoff:
            continue
        job.status = JobStatus.FAILED.value
        job.stage = "stalled"
        job.error = STALE_ERROR
        job.finished_at = moment
        job.lock_key = None
        job.cancel_requested = False
        session.add(
            build_vector_event(
                actor="system",
                action="vector.run.stalled",
                outcome="error",
                resource=run_resource(job.id),
            )
        )
        reaped.append(job)
    if reaped:
        session.commit()
        logger.warning("vector_runs_reaped", count=len(reaped))
    return reaped


__all__ = [
    "ACTIVE_STATUSES",
    "LOCKED_JOB_TYPES",
    "REAPABLE_JOB_TYPES",
    "STALE_ERROR",
    "RetrievalJobConflict",
    "active_run",
    "active_run_for_space",
    "default_lock_key",
    "enqueue_vector_job",
    "find_replay",
    "reap_stale_runs",
    "replay_cutoff",
    "run_vector_action",
    "validate_key",
]
