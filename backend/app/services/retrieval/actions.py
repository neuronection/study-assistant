"""The management/action seam over the retrieval spaces (plan 51 Q3b/Q3c2b1).

Every mutating action is admin-only at the router, idempotent, serialized by
the one-active-run lock and audited through the family ``vector.*`` vocabulary
in the existing ``audit_events`` table. Reindex, maintenance and cutover
enqueue the same ``VECTOR_*`` handlers Q3a shipped; the short lifecycle
transitions (build/activate/retire/drop) execute under a real job row through
:func:`run_vector_action`, so they keep the same replay and lock semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from sqlalchemy.orm import Session

from ...core.vocab import JobStatus, JobType
from ...domain.models import Job, VectorSpace, utcnow
from ...jobs.cancellation import request_cancel
from ...services.progress import carry_from_detail
from ...storage.retrieval_ops import (
    SPACE_DROP_GRACE_DAYS,
    GateStatus,
    MaintenanceAction,
    RetrievalAction,
    RetrievalActionResponse,
    RunStatus,
    assert_no_raw_text,
    run_lock_key,
)
from ...storage.tokenizer_contract import ChunkConfig, TokenizerSpec
from ...storage.vector_provisioning import VectorProvisioningError
from ...storage.vector_store import embedding_assignment
from . import lifecycle, quality
from .audit import build_vector_event, run_resource
from .jobs import (
    ACTIVE_STATUSES,
    REAPABLE_JOB_TYPES,
    RetrievalJobConflict,
    enqueue_vector_job,
    reap_stale_runs,
    run_vector_action,
    validate_key,
)
from .v1_store import V1_KIND, V1_SPACE_ID

MAINTENANCE_ACTIONS = tuple(member.value for member in MaintenanceAction)
DRY_RUN_ACTIONS = frozenset({MaintenanceAction.ORPHAN_SWEEP.value})
_SYNC_ACTION_PAYLOADS = frozenset({"build_space", "activate_space", "retire_space", "drop_space"})
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

_TERMINAL = frozenset({JobStatus.DONE.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value})


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


def _target_space(session: Session, space_id: str | None, *, allow_retired: bool = False) -> str:
    if space_id in (None, ""):
        active = lifecycle.active_space_row(session)
        if active is not None:
            return str(active.id)
        return V1_SPACE_ID
    row = session.get(VectorSpace, str(space_id))
    if row is None:
        raise RetrievalActionError(
            f"no vector space {space_id!r}",
            status_code=404,
            reason="space_not_found",
            extra={"space_id": space_id},
        )
    if row.status == "retired" and not allow_retired:
        raise RetrievalActionError(
            f"space {row.name!r} is retired; activate it or address the active space",
            reason="space_retired",
            extra={"space_id": str(row.id)},
        )
    return str(row.id)


def _audit_for(
    actor: str, action: str, space_id: str | None = None, *, outcome: str = "accepted"
) -> Any:
    return build_vector_event(
        actor=_actor(actor),
        action=action,
        outcome=outcome,
        resource=f"space:{space_id}"[:500] if space_id else "space:unknown",
    )


def _ensure_kind(kind: str | None) -> str | None:
    if kind in (None, ""):
        return None
    if kind != V1_KIND:
        raise RetrievalActionError(
            f"the v1 store only indexes kind {V1_KIND!r}",
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
    target = _target_space(session, space_id)
    if view is not None or since is not None:
        raise RetrievalActionError(
            "view/since scoping is not supported by the chunk store",
            status_code=422,
            reason="unsupported_scope",
        )
    bounded_limit = _bounded(limit, minimum=1, maximum=MAX_LIMIT, field="limit")
    bounded_batch = _bounded(batch_size, minimum=1, maximum=MAX_BATCH_SIZE, field="batch_size")
    ids = _chunk_ids(chunk_ids)
    payload: dict[str, Any] = {
        "action": "reindex",
        "space_id": target,
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
    audit = _audit_for(actor, "vector.reindex.started", target)
    try:
        job, deduplicated = enqueue_vector_job(
            session,
            job_type=JobType.VECTOR_REINDEX.value,
            payload=payload,
            idempotency_key=idempotency_key,
            audit=audit,
            space_id=target,
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
        message=("replay of the original reindex run" if deduplicated else "reindex queued"),
        extra={"space_id": target},
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
    target = _target_space(session, space_id)
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
    ids = _chunk_ids(chunk_ids, required=action == MaintenanceAction.RETRY_FAILED.value)
    payload: dict[str, Any] = {
        "action": action,
        "space_id": target,
        "dry_run": bool(dry_run),
    }
    if ids is not None:
        payload["chunk_ids"] = ids

    reap_stale_runs(session)
    audit = _audit_for(actor, "vector.maintenance.started", target)
    try:
        job, deduplicated = enqueue_vector_job(
            session,
            job_type=JobType.VECTOR_MAINTENANCE.value,
            payload=payload,
            idempotency_key=idempotency_key,
            audit=audit,
            space_id=target,
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
        extra={"space_id": target, "maintenance_action": action},
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
    if target.status not in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        raise RetrievalActionError(
            f"run {target.id} is {target.status}; only failed or cancelled runs retry",
            reason="run_not_retriable",
            extra={"run_id": target.id, "run_status": str(target.status)},
        )
    payload = dict(target.payload or {})
    if str(payload.get("action")) in _SYNC_ACTION_PAYLOADS:
        raise RetrievalActionError(
            "short lifecycle actions replay by repeating the action with the same "
            "Idempotency-Key; only reindex/maintenance/cutover runs retry",
            reason="run_not_retriable",
            extra={"run_id": target.id, "run_status": str(target.status)},
        )
    payload["requeue_of"] = target.id
    try:
        carried = carry_from_detail(target.progress_detail)
    except ValueError:
        carried = {}
    if not carried:
        previous = payload.get("progress_carry")
        try:
            carried = carry_from_detail(previous) if isinstance(previous, Mapping) else {}
        except ValueError:
            carried = {}
    if carried:
        payload["progress_carry"] = carried
    else:
        payload.pop("progress_carry", None)
    retry_space = str(payload.get("space_id") or "") or _target_space(session, None)
    retry_row = session.get(VectorSpace, retry_space)
    if retry_row is not None and retry_row.status == "retired":
        raise RetrievalActionError(
            f"space {retry_row.name!r} is retired; retries must target an active or building space",
            reason="space_retired",
            extra={"space_id": retry_space},
        )
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
            space_id=retry_space,
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
        message=("replay of the retry" if deduplicated else f"retry of {target.id} queued"),
        extra={"retry_of": target.id, "space_id": retry_space},
    )


def _lifecycle_response(
    action: RetrievalAction,
    job: Job,
    *,
    audit_event: str,
    message: str,
    space: dict[str, Any] | None = None,
    deduplicated: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _response(
        action,
        job,
        audit_event=audit_event,
        http_status=200,
        deduplicated=deduplicated,
        status=RunStatus.SUCCEEDED,
        message=message,
        extra={"space": space, **(extra or {})} if space is not None else extra,
    )


def build_space(
    session: Session,
    *,
    actor: str,
    idempotency_key: str,
    name: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    dim: int | None = None,
    normalize: bool = True,
    query_prefix: str | None = None,
    document_prefix: str | None = None,
    token_aware: bool = False,
    tokenizer: TokenizerSpec | None = None,
    chunk: ChunkConfig | None = None,
) -> dict[str, Any]:
    """Provision a real ``building`` space beside the active one."""
    from .chunk_profile import resolve_chunk_profile

    assignment = embedding_assignment(session)
    active = lifecycle.active_space_row(session)
    resolved_provider = provider or assignment.provider or (active.provider if active else "")
    resolved_model = model or assignment.model or (active.model if active else "")
    resolved_dim = dim or (int(active.dim) if active is not None else None)
    if resolved_dim is None:
        raise RetrievalActionError(
            "dim is required when no active space or vec_meta dimension exists",
            status_code=422,
            reason="invalid_request",
        )
    resolved_name = (name or "content").strip()
    if token_aware or tokenizer is not None or chunk is not None:
        if tokenizer is None and chunk is None:
            from ...ai.tokenizers.accounting import embedding_model_pair

            provider_type, assigned_model = embedding_model_pair(session)
            profile = resolve_chunk_profile(
                provider_type,
                assigned_model,
                document_prefix=document_prefix,
            )
            tokenizer, chunk = profile.tokenizer, profile.chunk
        elif tokenizer is None or chunk is None:
            raise RetrievalActionError(
                "tokenizer and chunk must be supplied together",
                status_code=422,
                reason="invalid_request",
            )
    payload = {
        "action": "build_space",
        "name": resolved_name,
        "provider": resolved_provider,
        "model": resolved_model,
        "dim": int(resolved_dim),
        "normalize": bool(normalize),
        "query_prefix": query_prefix,
        "document_prefix": document_prefix,
        "token_aware": bool(tokenizer is not None),
        "tokenizer": tokenizer.to_dict() if tokenizer is not None else None,
        "chunk": chunk.to_dict() if chunk is not None else None,
    }
    audit = _audit_for(actor, "vector.space.provisioned", None)
    try:
        response, deduplicated = run_vector_action(
            session,
            job_type=JobType.VECTOR_CUTOVER.value,
            payload=payload,
            idempotency_key=idempotency_key,
            lock_key=run_lock_key(resolved_name),
            execute=lambda _job: _execute_build(
                session,
                resolved_name,
                resolved_provider,
                resolved_model,
                int(resolved_dim),
                bool(normalize),
                query_prefix,
                document_prefix,
                payload,
                actor,
                tokenizer,
                chunk,
            ),
            audit=audit,
            failure_audit=_audit_for(actor, "vector.space.provisioned", None, outcome="error"),
        )
    except lifecycle.SpaceStateError as error:
        raise RetrievalActionError(str(error), reason="space_conflict") from error
    except lifecycle.SpaceLifecycleError as error:
        raise RetrievalActionError(str(error), reason="space_conflict") from error
    except VectorProvisioningError as error:
        raise RetrievalActionError(str(error), reason="provisioning_failed") from error
    except RetrievalJobConflict as error:
        raise RetrievalActionError(str(error), reason=error.reason, extra=error.extra) from error
    return _lifecycle_response(
        RetrievalAction.BUILD_SPACE,
        session.get(Job, response["run_id"]) or _job_stub(response),
        audit_event="vector.space.provisioned",
        message="building space provisioned" if not deduplicated else "replay of the space build",
        deduplicated=deduplicated,
        extra={
            "space_id": response.get("space_id"),
            "space": response.get("space"),
            "quality_state": "not_sampled",
            "quality": None,
        },
    )


def _execute_build(
    session: Session,
    name: str,
    provider: str,
    model: str,
    dim: int,
    normalize: bool,
    query_prefix: str | None,
    document_prefix: str | None,
    payload: dict[str, Any],
    actor: str,
    tokenizer: TokenizerSpec | None = None,
    chunk: ChunkConfig | None = None,
) -> dict[str, Any]:
    built, model_changed = lifecycle.build_space(
        session,
        name=name,
        provider=provider,
        model=model,
        dim=dim,
        normalize=normalize,
        query_prefix=query_prefix,
        document_prefix=document_prefix,
        tokenizer=tokenizer,
        chunk=chunk,
    )
    session.add(_audit_for(actor, "vector.space.provisioned", built.space_id))
    if model_changed:
        session.add(_audit_for(actor, "vector.model.changed", built.space_id))
    session.flush()
    return {
        "action": RetrievalAction.BUILD_SPACE.value,
        "accepted": True,
        "audit_event": "vector.space.provisioned",
        "http_status": 200,
        "deduplicated": False,
        "run_id": "",
        "status": RunStatus.SUCCEEDED.value,
        "idempotency_key": payload.get("idempotency_key"),
        "message": "building space provisioned",
        "space_id": built.space_id,
        "space": built.as_dict(),
        "model_changed": model_changed,
        "quality_state": "not_sampled",
        "quality": None,
    }


def _job_stub(payload: dict[str, Any]) -> Job:
    return Job(
        id=str(payload.get("run_id") or ""),
        type=JobType.VECTOR_CUTOVER.value,
        payload=payload,
        status=JobStatus.DONE.value,
    )


@dataclass(frozen=True)
class _QualityGate:
    """The quality half of the activation/cutover gate."""

    status: GateStatus
    state: str
    compare: dict[str, Any] | None = None
    quality: dict[str, Any] | None = None
    bad_matches: tuple[dict[str, Any], ...] = ()
    reasons: tuple[str, ...] = ()

    def as_extra(self) -> dict[str, Any]:
        return {
            "quality": self.quality,
            "quality_compare": self.compare,
            "quality_state": self.state,
            "bad_matches": list(self.bad_matches),
            "gate": self.status.value,
        }


def _quality_gate_for(
    session: Session,
    candidate: VectorSpace,
    *,
    embed: quality.EmbedFn,
) -> _QualityGate:
    """Measure the candidate against the golden set; never fabricate a pass.

    Reuses the newest persisted compare for the same candidate, baseline,
    set version and ``k`` (the standalone endpoint's evidence), otherwise runs
    the bounded compare in-place. A missing set is an explicit not-sampled
    refusal; an unassigned/failed embedder is a blocked refusal.
    """
    golden = quality.select_golden_set(candidate, quality.load_golden_sets())
    if golden is None:
        return _QualityGate(
            status=GateStatus.FAIL,
            state="not_sampled",
            reasons=("quality_no_golden_set",),
        )
    active = lifecycle.active_space_row(session)
    baseline = active if active is not None and str(active.id) != str(candidate.id) else None
    persisted = quality.latest_persisted_compare(
        session, candidate=candidate, baseline=baseline, golden=golden
    )
    if persisted is not None:
        _job, compare, stored_bad = persisted
        return _QualityGate(
            status=GateStatus.PASS if compare.passed else GateStatus.FAIL,
            state="sampled",
            compare=compare.to_dict(),
            quality=quality.quality_from_compare(compare).to_dict(),
            bad_matches=tuple(stored_bad),
            reasons=() if compare.passed else ("quality_below_floor",),
        )
    try:
        outcome = quality.compare_spaces(
            session,
            baseline,
            candidate,
            embed=embed,
            golden_sets=(golden,),
        )
    except quality.GoldenSetMissing:
        return _QualityGate(
            status=GateStatus.FAIL,
            state="not_sampled",
            reasons=("quality_no_golden_set",),
        )
    except quality.QualitySetupBlocked:
        return _QualityGate(
            status=GateStatus.FAIL,
            state="blocked",
            reasons=("quality_blocked",),
        )
    return _QualityGate(
        status=outcome.gate,
        state="sampled",
        compare=outcome.compare.to_dict(),
        quality=quality.quality_from_compare(outcome.compare).to_dict(),
        bad_matches=outcome.bad_matches,
        reasons=() if outcome.passed else ("quality_below_floor",),
    )


def _gate_refusal(
    row: VectorSpace,
    gate: lifecycle.ActivationGate,
    quality_gate: _QualityGate,
    *,
    action: RetrievalAction,
    job: Job | None = None,
) -> RetrievalActionError:
    quality_reasons = [reason for reason in gate.reasons if reason.startswith("quality_")]
    reason = "quality_gate_failed" if quality_reasons else "coverage_gate_failed"
    extra = {
        "space_id": str(row.id),
        "activation_gate": gate.as_dict(),
        "coverage": dict(gate.coverage),
        **quality_gate.as_extra(),
    }
    del job, action
    return RetrievalActionError(
        str(gate.reasons[0]) if gate.reasons else "activation refused",
        reason=reason,
        extra=extra,
    )


def activate_space(
    session: Session,
    *,
    actor: str,
    space_id: str,
    idempotency_key: str,
    embed: quality.EmbedFn,
) -> dict[str, Any]:
    row = session.get(VectorSpace, str(space_id))
    if row is None:
        raise RetrievalActionError(
            f"no vector space {space_id!r}",
            status_code=404,
            reason="space_not_found",
        )
    payload = {"action": "activate_space", "space_id": str(row.id)}
    try:
        response, deduplicated = run_vector_action(
            session,
            job_type=JobType.VECTOR_CUTOVER.value,
            payload=payload,
            idempotency_key=idempotency_key,
            lock_key=run_lock_key(str(row.id)),
            execute=lambda job: _execute_activate(session, str(row.id), actor, embed, job),
            audit=_audit_for(actor, "vector.space.activated", str(row.id)),
            failure_audit=_audit_for(actor, "vector.gate.failed", str(row.id), outcome="fail"),
        )
    except lifecycle.SpaceLifecycleError as error:
        raise RetrievalActionError(
            str(error), reason="space_state_invalid", extra={"space_id": str(row.id)}
        ) from error
    except RetrievalJobConflict as error:
        raise RetrievalActionError(str(error), reason=error.reason, extra=error.extra) from error
    job = session.get(Job, response.get("run_id")) or _job_stub(response)
    return _lifecycle_response(
        RetrievalAction.ACTIVATE_SPACE,
        job,
        audit_event="vector.space.activated",
        message="space activated" if not deduplicated else "replay of the activation",
        deduplicated=deduplicated,
        extra={
            "space_id": str(row.id),
            "quality": response.get("quality"),
            "quality_compare": response.get("quality_compare"),
            "quality_state": response.get("quality_state"),
            "bad_matches": response.get("bad_matches"),
            "gate": response.get("gate"),
            "activation_gate": response.get("activation_gate"),
            "space": response.get("space"),
            "already_active": response.get("already_active"),
        },
    )


def _execute_activate(
    session: Session,
    space_id: str,
    actor: str,
    embed: quality.EmbedFn,
    job: Job,
) -> dict[str, Any]:
    row = session.get(VectorSpace, space_id)
    if row is None:
        raise RetrievalActionError(
            f"no vector space {space_id!r}", status_code=404, reason="space_not_found"
        )
    if row.status == "active":
        return {
            "action": RetrievalAction.ACTIVATE_SPACE.value,
            "accepted": True,
            "audit_event": "vector.space.activated",
            "http_status": 200,
            "deduplicated": False,
            "run_id": "",
            "status": RunStatus.SUCCEEDED.value,
            "message": "space is already active",
            "space_id": space_id,
            "space": lifecycle.ActivationResult(
                space_id=str(row.id),
                name=str(row.name),
                space_key=lifecycle.space_key_for(row),
                already_active=True,
            ).as_dict(),
            "activation_gate": {
                "space_id": str(row.id),
                "coverage": "unknown",
                "quality": "unknown",
                "quality_state": "already_active",
                "allowed": True,
                "reasons": ["already_active"],
            },
            "quality": None,
            "quality_compare": None,
            "quality_state": "already_active",
            "bad_matches": [],
            "gate": "unknown",
            "already_active": True,
        }
    quality_gate = _quality_gate_for(session, row, embed=embed)
    try:
        activated = lifecycle.activate_space(
            session,
            space_id,
            quality=quality_gate.status,
            quality_state=quality_gate.state,
            quality_compare=quality_gate.compare,
            quality_reasons=quality_gate.reasons,
        )
    except lifecycle.SpaceActivationRefused as refused:
        raise _gate_refusal(
            row,
            refused.gate,
            quality_gate,
            action=RetrievalAction.ACTIVATE_SPACE,
            job=job,
        ) from refused
    session.add(_audit_for(actor, "vector.space.activated", space_id))
    session.flush()
    payload = activated.as_dict()
    gate = activated.gate.as_dict() if activated.gate is not None else None
    return {
        "action": RetrievalAction.ACTIVATE_SPACE.value,
        "accepted": True,
        "audit_event": "vector.space.activated",
        "http_status": 200,
        "deduplicated": False,
        "run_id": "",
        "status": RunStatus.SUCCEEDED.value,
        "message": "space activated",
        "space_id": space_id,
        "space": payload,
        "activation_gate": gate,
        **quality_gate.as_extra(),
        "already_active": payload.get("already_active", False),
    }


def retire_space(
    session: Session,
    *,
    actor: str,
    space_id: str,
    confirm_space_name: str,
    idempotency_key: str,
) -> dict[str, Any]:
    row = session.get(VectorSpace, str(space_id))
    if row is None:
        raise RetrievalActionError(
            f"no vector space {space_id!r}", status_code=404, reason="space_not_found"
        )
    if confirm_space_name != row.name:
        raise RetrievalActionError(
            f"typed confirmation must equal the space name {row.name!r}",
            status_code=422,
            reason="confirmation_mismatch",
        )
    payload = {"action": "retire_space", "space_id": str(row.id), "name": str(row.name)}
    try:
        response, deduplicated = run_vector_action(
            session,
            job_type=JobType.VECTOR_MAINTENANCE.value,
            payload=payload,
            idempotency_key=idempotency_key,
            lock_key=run_lock_key(str(row.id)),
            execute=lambda _job: _execute_retire(session, str(row.id), actor),
            audit=_audit_for(actor, "vector.space.retired", str(row.id)),
            failure_audit=_audit_for(actor, "vector.space.retired", str(row.id), outcome="error"),
        )
    except lifecycle.SpaceStateError as error:
        raise RetrievalActionError(
            str(error), reason="space_state_invalid", extra={"space_id": str(row.id)}
        ) from error
    except RetrievalJobConflict as error:
        raise RetrievalActionError(str(error), reason=error.reason, extra=error.extra) from error
    return _lifecycle_response(
        RetrievalAction.RETIRE_SPACE,
        session.get(Job, response.get("run_id")) or _job_stub(response),
        audit_event="vector.space.retired",
        message="space retired" if not deduplicated else "replay of the retirement",
        deduplicated=deduplicated,
        extra={"space_id": str(row.id), "space": response.get("space")},
    )


def _execute_retire(session: Session, space_id: str, actor: str) -> dict[str, Any]:
    retired = lifecycle.retire_space(session, space_id)
    session.add(_audit_for(actor, "vector.space.retired", space_id))
    session.flush()
    return {
        "action": RetrievalAction.RETIRE_SPACE.value,
        "accepted": True,
        "audit_event": "vector.space.retired",
        "http_status": 200,
        "deduplicated": False,
        "run_id": "",
        "status": RunStatus.SUCCEEDED.value,
        "message": "space retired",
        "space_id": space_id,
        "space": retired,
    }


def drop_space(
    session: Session,
    *,
    actor: str,
    space_id: str,
    confirm_space_name: str,
    force: bool,
    idempotency_key: str,
) -> dict[str, Any]:
    row = session.get(VectorSpace, str(space_id))
    if row is None:
        raise RetrievalActionError(
            f"no vector space {space_id!r}", status_code=404, reason="space_not_found"
        )
    if confirm_space_name != row.name:
        raise RetrievalActionError(
            f"typed confirmation must equal the space name {row.name!r}",
            status_code=422,
            reason="confirmation_mismatch",
        )
    payload = {
        "action": "drop_space",
        "space_id": str(row.id),
        "name": str(row.name),
        "force": bool(force),
    }
    try:
        response, deduplicated = run_vector_action(
            session,
            job_type=JobType.VECTOR_MAINTENANCE.value,
            payload=payload,
            idempotency_key=idempotency_key,
            lock_key=run_lock_key(str(row.id)),
            execute=lambda _job: _execute_drop(session, str(row.id), str(row.name), actor, force),
            audit=_audit_for(actor, "vector.space.dropped", str(row.id)),
            failure_audit=_audit_for(actor, "vector.space.dropped", str(row.id), outcome="error"),
        )
    except lifecycle.SpaceStateError as error:
        raise RetrievalActionError(
            str(error), reason="space_state_invalid", extra={"space_id": str(row.id)}
        ) from error
    except RetrievalJobConflict as error:
        raise RetrievalActionError(str(error), reason=error.reason, extra=error.extra) from error
    return _lifecycle_response(
        RetrievalAction.DROP_SPACE,
        session.get(Job, response.get("run_id")) or _job_stub(response),
        audit_event="vector.space.dropped",
        message="space dropped" if not deduplicated else "replay of the drop",
        deduplicated=deduplicated,
        extra={"space_id": str(row.id), "space": response.get("space")},
    )


def _execute_drop(
    session: Session, space_id: str, name: str, actor: str, force: bool
) -> dict[str, Any]:
    dropped = lifecycle.drop_space(
        session,
        space_id,
        confirm=name,
        force=force,
        grace=timedelta(days=SPACE_DROP_GRACE_DAYS),
    )
    session.add(_audit_for(actor, "vector.space.dropped", space_id))
    session.flush()
    return {
        "action": RetrievalAction.DROP_SPACE.value,
        "accepted": True,
        "audit_event": "vector.space.dropped",
        "http_status": 200,
        "deduplicated": False,
        "run_id": "",
        "status": RunStatus.SUCCEEDED.value,
        "message": "space dropped",
        "space_id": space_id,
        "space": dropped.as_dict(),
    }


def cutover(
    session: Session,
    *,
    actor: str,
    space_id: str,
    idempotency_key: str,
    limit: int = DEFAULT_LIMIT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    force: bool = False,
) -> dict[str, Any]:
    row = session.get(VectorSpace, str(space_id))
    if row is None:
        raise RetrievalActionError(
            f"no vector space {space_id!r}", status_code=404, reason="space_not_found"
        )
    if row.status == "retired":
        raise RetrievalActionError(
            f"space {row.name!r} is retired; only a building space can be cut over",
            reason="space_state_invalid",
            extra={"space_id": str(row.id)},
        )
    payload = {
        "action": "cutover",
        "space_id": str(row.id),
        "limit": _bounded(limit, minimum=1, maximum=MAX_LIMIT, field="limit"),
        "batch_size": _bounded(batch_size, minimum=1, maximum=MAX_BATCH_SIZE, field="batch_size"),
        "force": bool(force),
    }
    if row.status == "active":
        response = {
            "action": RetrievalAction.ACTIVATE_SPACE.value,
            "accepted": True,
            "audit_event": "vector.space.activated",
            "http_status": 200,
            "deduplicated": True,
            "run_id": None,
            "status": RunStatus.SUCCEEDED.value,
            "idempotency_key": None,
            "message": "space is already active",
            "space_id": str(row.id),
            "quality": None,
            "quality_state": "already_active",
            "bad_matches": [],
            "already_active": True,
        }
        return cast(dict[str, Any], assert_no_raw_text(response))
    reap_stale_runs(session)
    audit = _audit_for(actor, "vector.space.activated", str(row.id))
    try:
        job, deduplicated = enqueue_vector_job(
            session,
            job_type=JobType.VECTOR_CUTOVER.value,
            payload=payload,
            idempotency_key=idempotency_key,
            audit=audit,
            space_id=str(row.id),
        )
    except RetrievalJobConflict as error:
        raise RetrievalActionError(str(error), reason=error.reason, extra=error.extra) from error
    return _response(
        RetrievalAction.ACTIVATE_SPACE,
        job,
        audit_event="vector.space.activated",
        http_status=200 if deduplicated else 202,
        deduplicated=deduplicated,
        message=(
            "replay of the original cutover run"
            if deduplicated
            else "cutover queued: the candidate is backfilled, quality-gated and activated"
        ),
        extra={
            "space_id": str(row.id),
            "quality": None,
            "quality_state": "pending",
            "bad_matches": [],
        },
    )


def compare_quality(
    session: Session,
    *,
    actor: str,
    space_id: str,
    compare_space_id: str,
    idempotency_key: str,
    embed: quality.EmbedFn,
) -> dict[str, Any]:
    """Run the versioned golden set against old and new space; persist the result."""
    try:
        new_space = lifecycle.resolve_space(session, space_id)
        baseline_space = lifecycle.resolve_space(session, compare_space_id)
    except lifecycle.SpaceNotFound as error:
        raise RetrievalActionError(str(error), status_code=404, reason="space_not_found") from error
    if str(new_space.id) == str(baseline_space.id):
        raise RetrievalActionError(
            "compare spaces must differ",
            status_code=422,
            reason="invalid_request",
        )
    payload = {
        "action": RetrievalAction.QUALITY_COMPARE.value,
        "space_id": str(new_space.id),
        "compare_space_id": str(baseline_space.id),
    }
    try:
        response, deduplicated = run_vector_action(
            session,
            job_type=JobType.VECTOR_CUTOVER.value,
            payload=payload,
            idempotency_key=idempotency_key,
            lock_key=run_lock_key(str(new_space.id)),
            execute=lambda job: _execute_compare(
                session, job, new_space, baseline_space, actor, embed
            ),
            failure_audit=_audit_for(
                actor, "vector.gate.failed", str(new_space.id), outcome="fail"
            ),
        )
    except RetrievalJobConflict as error:
        raise RetrievalActionError(str(error), reason=error.reason, extra=error.extra) from error
    job = session.get(Job, response.get("run_id")) or _job_stub(response)
    return _response(
        RetrievalAction.QUALITY_COMPARE,
        job,
        audit_event="vector.gate.failed",
        http_status=200,
        deduplicated=deduplicated,
        message=(
            "replay of the original quality compare" if deduplicated else "quality compare complete"
        ),
        extra={
            "space_id": str(new_space.id),
            "baseline_space_id": str(baseline_space.id),
            **{
                key: response.get(key)
                for key in (
                    "quality",
                    "quality_compare",
                    "quality_state",
                    "bad_matches",
                    "gate",
                    "baseline_degraded",
                    "new_degraded",
                    "no_baseline",
                )
            },
        },
    )


def _execute_compare(
    session: Session,
    job: Job,
    new_space: VectorSpace,
    baseline_space: VectorSpace,
    actor: str,
    embed: quality.EmbedFn,
) -> dict[str, Any]:
    try:
        outcome = quality.compare_spaces(session, baseline_space, new_space, embed=embed)
    except quality.GoldenSetMissing as error:
        raise RetrievalActionError(
            str(error),
            reason="quality_no_golden_set",
            extra={
                "space_id": str(new_space.id),
                "quality": None,
                "quality_state": "not_sampled",
                "bad_matches": [],
                "gate": GateStatus.FAIL.value,
            },
        ) from error
    except quality.QualitySetupBlocked as error:
        raise RetrievalActionError(
            str(error),
            reason="quality_blocked",
            extra={
                "space_id": str(new_space.id),
                "quality": None,
                "quality_state": "blocked",
                "bad_matches": [],
                "gate": GateStatus.FAIL.value,
            },
        ) from error
    if not outcome.passed:
        session.add(
            _audit_for(
                actor,
                "vector.gate.failed",
                str(new_space.id),
                outcome="fail",
            )
        )
    session.flush()
    return {
        "action": RetrievalAction.QUALITY_COMPARE.value,
        "accepted": True,
        "audit_event": "vector.gate.failed",
        "http_status": 200,
        "deduplicated": False,
        "run_id": job.id,
        "status": RunStatus.SUCCEEDED.value,
        "idempotency_key": job.idempotency_key,
        "message": "quality compare complete",
        "space_id": str(new_space.id),
        "baseline_space_id": str(baseline_space.id),
        "quality": quality.quality_from_compare(outcome.compare).to_dict(),
        "quality_compare": outcome.compare.to_dict(),
        "quality_state": "sampled",
        "bad_matches": list(outcome.bad_matches),
        "gate": outcome.gate.value,
        "baseline_degraded": outcome.baseline_degraded,
        "new_degraded": outcome.new_degraded,
        "no_baseline": outcome.no_baseline,
    }


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_LIMIT",
    "DRY_RUN_ACTIONS",
    "MAINTENANCE_ACTIONS",
    "RetrievalActionError",
    "activate_space",
    "build_space",
    "cancel_run",
    "compare_quality",
    "cutover",
    "drop_space",
    "maintenance",
    "reindex",
    "retire_space",
    "retry_run",
    "validate_key",
]
