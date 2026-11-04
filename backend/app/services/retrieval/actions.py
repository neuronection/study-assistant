"""The management/action seam over the legacy retrieval space (plan 51 Q3b).

Every mutating action is admin-only at the router, idempotent for the two
enqueue actions, serialized by the one-active-run lock, and audited through
the family ``vector.*`` vocabulary in the existing ``audit_events`` table.
Execution is never duplicated here: reindex and maintenance enqueue the same
``VECTOR_*`` handlers Q3a shipped.

Study has one synthetic legacy space (``legacy-chunk-vecs``) and no
vector-space lifecycle. Lifecycle verbs are deliberately absent from this
module; the router answers them with a structured ``unsupported`` refusal.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy.orm import Session

from ...core.vocab import JobStatus, JobType
from ...domain.models import Job, utcnow
from ...jobs.cancellation import request_cancel
from ...storage.retrieval_ops import (
    MaintenanceAction,
    RetrievalAction,
    RetrievalActionResponse,
    RunStatus,
    assert_no_raw_text,
)
from .audit import build_vector_event, run_resource, space_resource
from .jobs import (
    ACTIVE_STATUSES,
    REAPABLE_JOB_TYPES,
    RetrievalJobConflict,
    enqueue_vector_job,
    reap_stale_runs,
    validate_key,
)
from .legacy import LEGACY_KIND, LEGACY_SPACE_ID

MAINTENANCE_ACTIONS = tuple(member.value for member in MaintenanceAction)
DRY_RUN_ACTIONS = frozenset({MaintenanceAction.ORPHAN_SWEEP.value})
DEFAULT_LIMIT = 500
MAX_LIMIT = 5_000
DEFAULT_BATCH_SIZE = 32
MAX_BATCH_SIZE = 256
MAX_CHUNK_IDS = 500

_STATUS_MAP = {
    JobStatus.QUEUED.value: RunStatus.QUEUED,
    JobStatus.RUNNING.value: RunStatus.RUNNING,
    JobStatus.DONE.value: RunStatus.SUCCEEDED,
    JobStatus.FAILED.value: RunStatus.FAILED,
    JobStatus.CANCELLED.value: RunStatus.CANCELLED,
}

_TERMINAL = frozenset(
    {JobStatus.DONE.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}
)


class RetrievalActionError(Exception):
    """A refusal the router renders as ``{"reason", "message", ...}``."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 409,
        reason: str = "conflict",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason
        self.extra = extra or {}


def _actor(actor: str) -> str:
    return (actor or "admin")[:200]


def _run_status(job: Job) -> RunStatus:
    return _STATUS_MAP.get(str(job.status), RunStatus.QUEUED)


def _bounded(value: int, *, minimum: int, maximum: int, field: str) -> int:
    if value < minimum or value > maximum:
        raise RetrievalActionError(
            f"{field} must be between {minimum} and {maximum}",
            status_code=422,
            reason="invalid_request",
        )
    return int(value)


def _chunk_ids(value: list[str] | None, *, required: bool = False) -> list[str] | None:
    if value is None:
        if required:
            raise RetrievalActionError(
                "chunk_ids is required for retry-failed",
                status_code=422,
                reason="invalid_request",
            )
        return None
    ids = [str(item) for item in value if str(item).strip()]
    if not ids and required:
        raise RetrievalActionError(
            "chunk_ids must contain at least one id",
            status_code=422,
            reason="invalid_request",
        )
    if len(ids) > MAX_CHUNK_IDS:
        raise RetrievalActionError(
            f"chunk_ids is capped at {MAX_CHUNK_IDS} entries",
            status_code=422,
            reason="invalid_request",
        )
    return ids or None


def _ensure_legacy_space(space_id: str | None) -> None:
    if space_id not in (None, "", LEGACY_SPACE_ID):
        raise RetrievalActionError(
            "study exposes one legacy space (legacy-chunk-vecs); "
            "vector-space lifecycle is not implemented in this build",
            reason="unsupported_space",
            extra={"space_id": space_id},
        )


def _ensure_kind(kind: str | None) -> str | None:
    if kind in (None, ""):
        return None
    if kind != LEGACY_KIND:
        raise RetrievalActionError(
            f"the legacy store only indexes kind {LEGACY_KIND!r}",
            status_code=422,
            reason="unsupported_kind",
            extra={"kind": kind},
        )
    return kind


def _response(
    action: RetrievalAction,
    job: Job,
    *,
    audit_event: str,
    http_status: int,
    message: str,
    deduplicated: bool = False,
    extra: dict[str, Any] | None = None,
    status: RunStatus | None = None,
) -> dict[str, Any]:
    payload = RetrievalActionResponse(
        action=action,
        accepted=True,
        audit_event=audit_event,
        http_status=http_status,
        deduplicated=deduplicated,
        run_id=job.id,
        status=status or _run_status(job),
        idempotency_key=job.idempotency_key,
        message=message,
    ).to_dict()
    if extra:
        payload.update(extra)
    return cast(dict[str, Any], assert_no_raw_text(payload))


def _vector_run(session: Session, run_id: str) -> Job:
    job = session.get(Job, run_id)
    if job is None or str(job.type) not in REAPABLE_JOB_TYPES:
        raise RetrievalActionError(
            f"no vector run {run_id!r}",
            status_code=404,
            reason="run_not_found",
        )
    return job


def reindex(
    session: Session,
    *,
    actor: str,
    idempotency_key: str,
    limit: int = DEFAULT_LIMIT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    force: bool = False,
    chunk_ids: list[str] | None = None,
    kind: str | None = None,
    space_id: str | None = None,
    view: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    _ensure_legacy_space(space_id)
    if view is not None or since is not None:
        raise RetrievalActionError(
            "view/since scoping is not supported by the legacy chunk store",
            status_code=422,
            reason="unsupported_scope",
        )
    bounded_limit = _bounded(limit, minimum=1, maximum=MAX_LIMIT, field="limit")
    bounded_batch = _bounded(
        batch_size, minimum=1, maximum=MAX_BATCH_SIZE, field="batch_size"
    )
    ids = _chunk_ids(chunk_ids)
    payload: dict[str, Any] = {
        "action": "reindex",
        "space_id": LEGACY_SPACE_ID,
        "limit": bounded_limit,
        "batch_size": bounded_batch,
        "force": bool(force),
    }
    normalized_kind = _ensure_kind(kind)
    if normalized_kind is not None:
        payload["kind"] = normalized_kind
    if ids is not None:
        payload["chunk_ids"] = ids

    reap_stale_runs(session)
    audit = build_vector_event(
        actor=_actor(actor),
        action="vector.reindex.started",
        outcome="accepted",
        resource=space_resource(),
    )
    try:
        job, deduplicated = enqueue_vector_job(
            session,
            job_type=JobType.VECTOR_REINDEX.value,
            payload=payload,
            idempotency_key=idempotency_key,
            audit=audit,
        )
    except RetrievalJobConflict as error:
        raise RetrievalActionError(
            str(error),
            reason=error.reason,
            extra=error.extra,
        ) from error
    return _response(
        RetrievalAction.REINDEX,
        job,
        audit_event="vector.reindex.started",
        http_status=200 if deduplicated else 202,
        deduplicated=deduplicated,
        message=(
            "replay of the original reindex run"
            if deduplicated
            else "reindex queued"
        ),
        extra={"space_id": LEGACY_SPACE_ID},
    )


def maintenance(
    session: Session,
    *,
    actor: str,
    idempotency_key: str,
    action: str,
    dry_run: bool = False,
    chunk_ids: list[str] | None = None,
    space_id: str | None = None,
) -> dict[str, Any]:
    _ensure_legacy_space(space_id)
    if action not in MAINTENANCE_ACTIONS:
        raise RetrievalActionError(
            f"unknown maintenance action {action!r}; expected one of {MAINTENANCE_ACTIONS}",
            status_code=422,
            reason="unknown_action",
        )
    if dry_run and action not in DRY_RUN_ACTIONS:
        raise RetrievalActionError(
            f"dry-run is only supported for {sorted(DRY_RUN_ACTIONS)}",
            status_code=422,
            reason="unsupported_dry_run",
        )
    ids = _chunk_ids(
        chunk_ids, required=action == MaintenanceAction.RETRY_FAILED.value
    )
    payload: dict[str, Any] = {
        "action": action,
        "space_id": LEGACY_SPACE_ID,
        "dry_run": bool(dry_run),
    }
    if ids is not None:
        payload["chunk_ids"] = ids

    reap_stale_runs(session)
    audit = build_vector_event(
        actor=_actor(actor),
        action="vector.maintenance.started",
        outcome="accepted",
        resource=space_resource(),
    )
    try:
        job, deduplicated = enqueue_vector_job(
            session,
            job_type=JobType.VECTOR_MAINTENANCE.value,
            payload=payload,
            idempotency_key=idempotency_key,
            audit=audit,
        )
    except RetrievalJobConflict as error:
        raise RetrievalActionError(
            str(error),
            reason=error.reason,
            extra=error.extra,
        ) from error
    return _response(
        RetrievalAction.MAINTENANCE,
        job,
        audit_event="vector.maintenance.started",
        http_status=200 if deduplicated else 202,
        deduplicated=deduplicated,
        message=(
            "replay of the original maintenance run"
            if deduplicated
            else f"maintenance ({action}) queued"
        ),
        extra={"space_id": LEGACY_SPACE_ID, "maintenance_action": action},
    )


def cancel_run(session: Session, *, actor: str, run_id: str) -> dict[str, Any]:
    reap_stale_runs(session)
    job = _vector_run(session, run_id)
    if str(job.status) not in ACTIVE_STATUSES:
        raise RetrievalActionError(
            f"run {job.id} is already {job.status}; nothing to cancel",
            reason="run_not_active",
            extra={"run_id": job.id, "run_status": str(job.status)},
        )

    changed = False
    if job.status == JobStatus.QUEUED.value:
        job.status = JobStatus.CANCELLED.value
        job.error = "cancelled by admin"
        job.finished_at = utcnow()
        job.lock_key = None
        changed = True
    else:
        job.cancel_requested = True
        request_cancel(job.id)
        changed = True
    session.add(
        build_vector_event(
            actor=_actor(actor),
            action="vector.reindex.cancelled",
            outcome="accepted" if changed else "noop",
            resource=run_resource(job.id),
        )
    )
    session.commit()
    session.refresh(job)
    status = _run_status(job)
    payload = {
        "action": RetrievalAction.CANCEL_RUN.value,
        "accepted": True,
        "audit_event": "vector.reindex.cancelled",
        "http_status": 200,
        "deduplicated": not changed,
        "run_id": job.id,
        "status": status.value,
        "idempotency_key": job.idempotency_key,
        "message": (
            "cancellation requested; the worker observes it at its next checkpoint"
            if job.status == JobStatus.RUNNING.value
            else "run cancelled"
        ),
        "cancel_requested": bool(job.cancel_requested),
    }
    return cast(dict[str, Any], assert_no_raw_text(payload))


def retry_run(
    session: Session,
    *,
    actor: str,
    run_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    reap_stale_runs(session)
    target = _vector_run(session, run_id)
    if target.type == JobType.VECTOR_CUTOVER.value:
        raise RetrievalActionError(
            "cutover is unavailable in this build (no vector-space lifecycle)",
            reason="unsupported_action",
        )
    if target.status not in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        raise RetrievalActionError(
            f"run {target.id} is {target.status}; only failed or cancelled runs retry",
            reason="run_not_retriable",
            extra={"run_id": target.id, "run_status": str(target.status)},
        )
    payload = dict(target.payload or {})
    payload["requeue_of"] = target.id
    audit = build_vector_event(
        actor=_actor(actor),
        action="vector.reindex.retried",
        outcome="accepted",
        resource=run_resource(target.id),
    )
    try:
        job, deduplicated = enqueue_vector_job(
            session,
            job_type=str(target.type),
            payload=payload,
            idempotency_key=idempotency_key,
            audit=audit,
        )
    except RetrievalJobConflict as error:
        raise RetrievalActionError(
            str(error),
            reason=error.reason,
            extra=error.extra,
        ) from error
    return _response(
        RetrievalAction.RETRY_RUN,
        job,
        audit_event="vector.reindex.retried",
        http_status=200 if deduplicated else 202,
        deduplicated=deduplicated,
        message=(
            "replay of the retry"
            if deduplicated
            else f"retry of {target.id} queued"
        ),
        extra={"retry_of": target.id, "space_id": LEGACY_SPACE_ID},
    )


def unsupported_lifecycle(action: str) -> RetrievalActionError:
    return RetrievalActionError(
        f"{action} is unavailable: study has one legacy chunk_vecs space and "
        "no vector-space lifecycle (plan 51 Q3c)",
        reason="unsupported_action",
        extra={"action": action, "space_id": LEGACY_SPACE_ID},
    )


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_LIMIT",
    "DRY_RUN_ACTIONS",
    "MAINTENANCE_ACTIONS",
    "RetrievalActionError",
    "cancel_run",
    "maintenance",
    "reindex",
    "retry_run",
    "unsupported_lifecycle",
    "validate_key",
]
