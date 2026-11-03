"""Admin-only retrieval-operations read surface (plan 51 Q3a).

A deliberately small first slice over the legacy store: overview, spaces,
coverage, runs and query health. The management/action API, quality surface
and space lifecycle are Q3b — no route here mutates the store.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from nx_auth.deps import get_current_user
from nx_auth.principal import Principal
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..services.retrieval import reads
from .deps import get_session

router = APIRouter(prefix="/admin/retrieval", tags=["retrieval"])


def require_admin(user: Principal = Depends(get_current_user)) -> Principal:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin access required")
    return user


class RetrievalRunScopeOut(BaseModel):
    kind: str | None = None
    view: str | None = None
    since: str | None = None


class RetrievalRunResultOut(BaseModel):
    scanned: int = 0
    embedded: int = 0
    skipped: int = 0
    failed: int = 0
    failed_ids: list[str] = Field(default_factory=list)
    failed_ids_truncated: bool = False
    gate: str = "unknown"


class RetrievalRunOut(BaseModel):
    run_id: str
    space_id: str
    job_type: str
    status: str
    progress: int = 0
    stage: str | None = None
    scope: RetrievalRunScopeOut = Field(default_factory=RetrievalRunScopeOut)
    budget_tokens: int | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    heartbeat_at: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    idempotency_key: str | None = None
    lock_key: str | None = None


class RetrievalRunDetailOut(BaseModel):
    run: RetrievalRunOut
    result: RetrievalRunResultOut | None = None
    duration_seconds: float | None = None


class RetrievalSpaceOut(BaseModel):
    space_id: str
    name: str
    status: str
    provider: str
    model: str
    dim: int
    backend: str
    metric: str = "cosine"
    index_table: str | None = None
    documents: int = 0
    records: int = 0
    coverage: float | None = None
    stale: int | None = None
    failed: int | None = None
    created_at: str | None = None
    activated_at: str | None = None
    retired_at: str | None = None
    last_reindex_at: str | None = None
    last_error: str | None = None
    gate: str = "unknown"
    as_of: str | None = None


class RetrievalCoverageOut(BaseModel):
    space_id: str
    as_of: str | None
    total: int
    missing: int
    stale: int
    failed: int
    embedded: int
    coverage: float | None
    gate: str = "unknown"
    ann_recall: float | None = None
    ann_recall_k: int | None = None
    probe_size: int | None = None


class RetrievalQueryHealthOut(BaseModel):
    space_id: str
    window_start: str
    window_end: str
    p50_ms: float | None = None
    p95_ms: float | None = None
    candidate_p50: float | None = None
    candidate_p95: float | None = None
    zero_result_rate: float | None = None
    degraded_rate: float | None = None
    degraded_reasons: dict[str, int] = Field(default_factory=dict)
    per_view_hits: dict[str, int] = Field(default_factory=dict)
    ann_recall: float | None = None
    ann_recall_k: int | None = None
    probe_size: int | None = None
    sampled: bool = False
    sample_size: int = 0
    query_count: int = 0


class RetrievalQueryHealthEnvelopeOut(BaseModel):
    window: str
    window_start: str | None
    window_end: str | None
    query_count: int
    candidates_avg: float | None = None
    health: RetrievalQueryHealthOut


class RetrievalOverviewOut(BaseModel):
    state: str
    cold: bool
    backend: str | None = None
    backend_label: str | None = None
    space: RetrievalSpaceOut | None = None
    coverage: RetrievalCoverageOut
    recent_runs: list[RetrievalRunDetailOut] = Field(default_factory=list)
    query_health: RetrievalQueryHealthEnvelopeOut
    notes: list[str] = Field(default_factory=list)


class RetrievalSpacesOut(BaseModel):
    spaces: list[RetrievalSpaceOut] = Field(default_factory=list)
    cold: bool = True
    notes: list[str] = Field(default_factory=list)


class RetrievalCoverageEnvelopeOut(BaseModel):
    space_id: str
    cold: bool
    coverage: RetrievalCoverageOut | None = None
    notes: list[str] = Field(default_factory=list)


class RetrievalRunsOut(BaseModel):
    runs: list[RetrievalRunDetailOut] = Field(default_factory=list)


@router.get("/overview", response_model=RetrievalOverviewOut)
def get_overview(
    window: str = Query(default=reads.DEFAULT_WINDOW),
    _admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalOverviewOut:
    payload: dict[str, Any] = reads.overview(session, window=window)
    return RetrievalOverviewOut.model_validate(payload)


@router.get("/spaces", response_model=RetrievalSpacesOut)
def get_spaces(
    _admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalSpacesOut:
    return RetrievalSpacesOut.model_validate(reads.spaces(session))


@router.get("/coverage", response_model=RetrievalCoverageEnvelopeOut)
def get_coverage(
    space: str | None = Query(default=None),
    _admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalCoverageEnvelopeOut:
    return RetrievalCoverageEnvelopeOut.model_validate(
        reads.coverage(session, space=space)
    )


@router.get("/runs", response_model=RetrievalRunsOut)
def get_runs(
    limit: int = Query(default=reads.RUN_LIMIT, ge=1, le=reads.RUN_MAX),
    _admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalRunsOut:
    return RetrievalRunsOut.model_validate({"runs": reads.list_runs(session, limit=limit)})


@router.get("/query-health", response_model=RetrievalQueryHealthEnvelopeOut)
def get_query_health(
    window: str = Query(default=reads.DEFAULT_WINDOW),
    _admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalQueryHealthEnvelopeOut:
    return RetrievalQueryHealthEnvelopeOut.model_validate(
        reads.query_health(session, window=window)
    )
