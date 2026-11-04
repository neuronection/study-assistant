"""Composed retrieval-operations read model over the legacy store.

Plan 51 Q3a. Every reader composes what already exists — ``jobs`` (the
VECTOR_* run rows), ``chunks``/``chunk_vecs`` (the store), the two bounded
rollups — and shapes the family contract DTOs. Nothing here carries raw
query, prompt or document text, and coverage is always the latest snapshot
(``as_of=None`` means never reconciled, never a fake percentage).

Study has no space lifecycle, so the read model exposes exactly one synthetic
legacy space. The management UI, cutover and activation gates are Q3b.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.models import Job, RetrievalQueryRollup
from ...storage.retrieval_ops import (
    VECTOR_JOB_TYPES,
    GateStatus,
    QueryHealthDTO,
    RunDTO,
    RunResultDTO,
    RunScope,
    RunStatus,
    SpaceDTO,
)
from .legacy import (
    LEGACY_KIND,
    LEGACY_SPACE_ID,
    LegacyStore,
    backend_label,
    coverage_dto,
    iso,
    latest_coverage,
    load_store,
    space_dto,
)
from .telemetry import aggregate_rows

READ_WINDOWS = ("24h", "7d", "30d", "90d")
DEFAULT_WINDOW = "24h"
RUN_LIMIT = 50
RUN_MAX = 200

_STATUS_MAP = {
    "queued": RunStatus.QUEUED,
    "running": RunStatus.RUNNING,
    "failed": RunStatus.FAILED,
    "done": RunStatus.SUCCEEDED,
    "cancelled": RunStatus.CANCELLED,
}

_RESULT_FIELDS = {
    "scanned",
    "embedded",
    "skipped",
    "failed",
    "failed_ids",
    "failed_ids_truncated",
    "gate",
}


def _window(value: str | None) -> tuple[datetime, datetime, str]:
    key = value if value in READ_WINDOWS else DEFAULT_WINDOW
    deltas = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "90d": timedelta(days=90),
    }
    end = datetime.now(UTC)
    return (end - deltas[key], end, key)


def _result(row: Job) -> RunResultDTO | None:
    payload = row.result
    if not isinstance(payload, dict):
        return None
    raw = cast(Mapping[str, Any], payload)
    values = {key: raw[key] for key in _RESULT_FIELDS if key in raw}
    try:
        return RunResultDTO(**values)
    except ValueError:
        return None


def _run_dto(row: Job) -> RunDTO | None:
    job_type = str(row.type)
    if job_type not in VECTOR_JOB_TYPES:
        return None
    status = _STATUS_MAP.get(str(row.status), RunStatus.QUEUED)
    payload = row.payload if isinstance(row.payload, dict) else {}
    scope = RunScope(
        kind=str(payload["kind"]) if payload.get("kind") else None,
        view=None,
        since=None,
    )
    budget = payload.get("budget")
    return RunDTO(
        run_id=row.id,
        space_id=LEGACY_SPACE_ID,
        job_type=job_type,
        status=status,
        progress=max(0, min(int(row.progress or 0), 100)),
        stage=row.stage,
        scope=scope,
        budget_tokens=(
            int(str(budget)) if budget is not None else None
        ),
        created_at=iso(row.created_at),
        started_at=iso(row.started_at),
        finished_at=iso(row.finished_at),
        heartbeat_at=iso(row.heartbeat_at),
        error=row.error,
        cancel_requested=bool(row.cancel_requested),
        idempotency_key=row.idempotency_key,
        lock_key=row.lock_key,
    )


def _run_payload(row: Job) -> dict[str, Any]:
    dto = _run_dto(row)
    result = _result(row)
    duration: float | None = None
    if row.started_at is not None and row.finished_at is not None:
        duration = max((row.finished_at - row.started_at).total_seconds(), 0.0)
    return {
        "run": dto.to_dict() if dto is not None else None,
        "result": result.to_dict() if result is not None else None,
        "duration_seconds": duration,
    }


def list_runs(session: Session, *, limit: int = RUN_LIMIT) -> list[dict[str, Any]]:
    capped = max(1, min(limit, RUN_MAX))
    rows = session.scalars(
        select(Job)
        .where(Job.type.in_(VECTOR_JOB_TYPES))
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(capped)
    ).all()
    payloads = [_run_payload(row) for row in rows]
    return [payload for payload in payloads if payload["run"] is not None]


def _last_reindex(session: Session) -> str | None:
    row = session.scalars(
        select(Job)
        .where(Job.type == "VECTOR_REINDEX", Job.status == "done")
        .order_by(Job.finished_at.desc(), Job.created_at.desc())
        .limit(1)
    ).first()
    return iso(row.finished_at or row.created_at) if row is not None else None


def _space(session: Session, store: LegacyStore) -> SpaceDTO:
    return replace(space_dto(session, store), last_reindex_at=_last_reindex(session))


def query_health(session: Session, *, window: str | None = None) -> dict[str, Any]:
    start, end, key = _window(window)
    rows = session.scalars(
        select(RetrievalQueryRollup)
        .where(
            RetrievalQueryRollup.space_id == LEGACY_SPACE_ID,
            RetrievalQueryRollup.kind == LEGACY_KIND,
            RetrievalQueryRollup.bucket_start >= start,
            RetrievalQueryRollup.bucket_start < end,
        )
        .order_by(RetrievalQueryRollup.bucket_start)
    ).all()
    metrics = aggregate_rows(list(rows))
    snapshot = latest_coverage(session)
    dto = QueryHealthDTO(
        space_id=LEGACY_SPACE_ID,
        window_start=iso(start) or "",
        window_end=iso(end) or "",
        p50_ms=metrics["p50_ms"],
        p95_ms=metrics["p95_ms"],
        candidate_p50=None,
        candidate_p95=None,
        zero_result_rate=metrics["zero_result_rate"],
        degraded_rate=metrics["degraded_rate"],
        degraded_reasons=metrics["degraded_reasons"],
        per_view_hits={},
        ann_recall=snapshot.ann_recall if snapshot is not None else None,
        ann_recall_k=snapshot.ann_recall_k if snapshot is not None else None,
        probe_size=snapshot.probe_size if snapshot is not None else None,
        sampled=bool(snapshot is not None and snapshot.ann_recall is not None),
        sample_size=metrics["query_count"],
        query_count=metrics["query_count"],
    )
    return {
        "window": key,
        "window_start": iso(start),
        "window_end": iso(end),
        "query_count": metrics["query_count"],
        "candidates_avg": metrics["candidates_avg"],
        "health": dto.to_dict(),
    }


def overview(session: Session, *, window: str | None = None) -> dict[str, Any]:
    store = load_store(session)
    coverage = coverage_dto(session, store)
    runs = list_runs(session, limit=5)
    health = query_health(session, window=window)
    notes: list[str] = [
        "Space lifecycle management (build/activate/retire/cutover) is not "
        "available in this build — plan 51 Q3b."
    ]
    if store is None and coverage.as_of is None:
        state = "empty"
        notes.append("The legacy vector store has no vec_meta yet (nothing embedded).")
    elif coverage.as_of is None:
        state = "cold"
        notes.append("Never reconciled — run a vector reindex to publish coverage.")
    elif store is None or coverage.gate == GateStatus.FAIL or (coverage.failed or 0) > 0:
        state = "degraded"
    else:
        state = "ready"
    if store is not None and store.provider == "unassigned":
        notes.append(
            "The embeddings task has no provider/model assignment; search falls "
            "back to lexical matching."
        )
    space = _space(session, store) if store is not None else None
    return {
        "state": state,
        "cold": coverage.as_of is None,
        "backend": store.backend if store is not None else None,
        "backend_label": backend_label(store.backend) if store is not None else None,
        "space": space.to_dict() if space is not None else None,
        "coverage": coverage.to_dict(),
        "recent_runs": runs,
        "query_health": health,
        "notes": notes,
    }


def spaces(session: Session) -> dict[str, Any]:
    store = load_store(session)
    rows = [_space(session, store).to_dict()] if store is not None else []
    return {
        "spaces": rows,
        "cold": not rows or coverage_dto(session, store).as_of is None,
        "notes": (
            []
            if store is not None
            else ["No legacy vector store is provisioned; spaces is empty."]
        ),
    }


def coverage(session: Session, *, space: str | None = None) -> dict[str, Any]:
    store = load_store(session)
    if store is not None and space not in (None, "", store.space_id):
        return {
            "space_id": space,
            "cold": True,
            "coverage": None,
            "notes": [f"No such space {space!r}; study exposes one legacy space."],
        }
    dto = coverage_dto(session, store)
    return {
        "space_id": dto.space_id,
        "cold": dto.as_of is None,
        "coverage": dto.to_dict(),
        "notes": (
            ["Never reconciled — no coverage snapshot exists."]
            if dto.as_of is None
            else []
        ),
    }


__all__ = [
    "DEFAULT_WINDOW",
    "READ_WINDOWS",
    "coverage",
    "list_runs",
    "overview",
    "query_health",
    "spaces",
]
