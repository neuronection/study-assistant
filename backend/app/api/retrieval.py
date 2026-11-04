"""Admin-only retrieval-operations read and action surface (plan 51).

Q3a shipped the read slice; Q3b the write seam with idempotency, the
single-active-run lock, the reaper and ``vector.*`` audit; Q3c2b1 wires the
real space lifecycle and cutover. The only thing still refused is the
golden-query quality compare (Q3c2b2) — activation is coverage-gated and
reports ``quality=not_sampled``.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from nx_auth.deps import get_current_user
from nx_auth.principal import Principal
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..services.retrieval import actions, reads
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
    spaces: list[RetrievalSpaceOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RetrievalSpacesOut(BaseModel):
    spaces: list[RetrievalSpaceOut] = Field(default_factory=list)
    cold: bool = True
    active_space_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class RetrievalCoverageEnvelopeOut(BaseModel):
    space_id: str
    cold: bool
    coverage: RetrievalCoverageOut | None = None
    notes: list[str] = Field(default_factory=list)


class RetrievalRunsOut(BaseModel):
    runs: list[RetrievalRunDetailOut] = Field(default_factory=list)


class RetrievalReindexIn(BaseModel):
    """One bounded reindex of the legacy store; the header carries the key."""

    space_id: str | None = None
    limit: int = Field(default=actions.DEFAULT_LIMIT, ge=1, le=actions.MAX_LIMIT)
    batch_size: int = Field(
        default=actions.DEFAULT_BATCH_SIZE, ge=1, le=actions.MAX_BATCH_SIZE
    )
    force: bool = False
    chunk_ids: list[str] | None = Field(default=None, max_length=actions.MAX_CHUNK_IDS)
    kind: str | None = None
    view: str | None = None
    since: str | None = None
    idempotency_key: str | None = None


class RetrievalMaintenanceIn(BaseModel):
    """One typed maintenance action; retry-failed needs chunk_ids."""

    action: Literal["orphan-sweep", "vacuum", "index-rebuild", "retry-failed"]
    dry_run: bool = False
    chunk_ids: list[str] | None = Field(default=None, max_length=actions.MAX_CHUNK_IDS)
    space_id: str | None = None
    idempotency_key: str | None = None


class RetrievalActionKeyIn(BaseModel):
    """Path-addressed action body; the Idempotency-Key header is preferred."""

    idempotency_key: str | None = None


class RetrievalSpaceBuildIn(BaseModel):
    """Build a building space; model/dim default to the current assignment."""

    name: str | None = Field(default=None, max_length=40)
    provider: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=120)
    dim: int | None = Field(default=None, ge=1, le=3072)
    normalize: bool = True
    query_prefix: str | None = Field(default=None, max_length=80)
    document_prefix: str | None = Field(default=None, max_length=80)
    idempotency_key: str | None = None


class RetrievalSpaceConfirmIn(BaseModel):
    """Typed destructive confirmation (the space name) + replay key."""

    confirm_space_name: str = Field(min_length=1, max_length=40)
    force: bool = False
    idempotency_key: str | None = None


class RetrievalCutoverIn(BaseModel):
    """Backfill a building space, enforce coverage, flip active and retire old."""

    space_id: str = Field(min_length=1, max_length=80)
    limit: int = Field(default=actions.DEFAULT_LIMIT, ge=1, le=actions.MAX_LIMIT)
    batch_size: int = Field(
        default=actions.DEFAULT_BATCH_SIZE, ge=1, le=actions.MAX_BATCH_SIZE
    )
    force: bool = False
    idempotency_key: str | None = None


class RetrievalActionOut(BaseModel):
    action: str
    accepted: bool
    audit_event: str
    http_status: int
    deduplicated: bool = False
    run_id: str | None = None
    status: str | None = None
    idempotency_key: str | None = None
    message: str = ""
    space_id: str | None = None
    space: dict[str, Any] | None = None
    quality: str | None = None
    activation_gate: dict[str, Any] | None = None
    already_active: bool | None = None
    model_changed: bool | None = None
    maintenance_action: str | None = None
    retry_of: str | None = None
    cancel_requested: bool | None = None


IDEMPOTENCY_HEADER = Header(
    default=None,
    alias="Idempotency-Key",
    description="Client-generated replay key (8-120 chars); repeats with the same body replay",
)


def _resolve_key(
    header: str | None,
    body: (
        RetrievalReindexIn
        | RetrievalMaintenanceIn
        | RetrievalActionKeyIn
        | RetrievalSpaceBuildIn
        | RetrievalSpaceConfirmIn
        | RetrievalCutoverIn
    ),
    *,
    required: bool,
    action: str,
) -> str | None:
    value = header or body.idempotency_key
    if value is None or str(value).strip() == "":
        if required:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "idempotency_key_required",
                    "message": (
                        "an Idempotency-Key header (or idempotency_key field) "
                        f"is required for {action}"
                    ),
                },
            )
        return None
    try:
        return actions.validate_key(value)
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail={"reason": "invalid_idempotency_key", "message": str(error)},
        ) from error


def _refused(error: actions.RetrievalActionError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={
            "reason": error.reason,
            "message": str(error),
            **error.extra,
        },
    )


def _respond(payload: dict[str, Any], response: Response) -> RetrievalActionOut:
    response.status_code = int(payload.get("http_status") or 202)
    return RetrievalActionOut.model_validate(payload)


def _actor(user: Principal) -> str:
    return str(user.email or user.user_id)


def _wake(request: Request) -> None:
    runner = getattr(request.app.state, "jobs", None)
    if runner is not None:
        runner.wake()


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


@router.post("/reindex", response_model=RetrievalActionOut)
def post_reindex(
    body: RetrievalReindexIn,
    request: Request,
    response: Response,
    idempotency_key: str | None = IDEMPOTENCY_HEADER,
    admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalActionOut:
    key = _resolve_key(idempotency_key, body, required=True, action="reindex")
    assert key is not None
    try:
        payload = actions.reindex(
            session,
            actor=_actor(admin),
            idempotency_key=key,
            limit=body.limit,
            batch_size=body.batch_size,
            force=body.force,
            chunk_ids=body.chunk_ids,
            kind=body.kind,
            space_id=body.space_id,
            view=body.view,
            since=body.since,
        )
    except actions.RetrievalActionError as error:
        raise _refused(error) from error
    _wake(request)
    return _respond(payload, response)


@router.post("/maintenance", response_model=RetrievalActionOut)
def post_maintenance(
    body: RetrievalMaintenanceIn,
    request: Request,
    response: Response,
    idempotency_key: str | None = IDEMPOTENCY_HEADER,
    admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalActionOut:
    key = _resolve_key(idempotency_key, body, required=True, action="maintenance")
    assert key is not None
    try:
        payload = actions.maintenance(
            session,
            actor=_actor(admin),
            idempotency_key=key,
            action=body.action,
            dry_run=body.dry_run,
            chunk_ids=body.chunk_ids,
            space_id=body.space_id,
        )
    except actions.RetrievalActionError as error:
        raise _refused(error) from error
    _wake(request)
    return _respond(payload, response)


@router.post("/runs/{run_id}/cancel", response_model=RetrievalActionOut)
def post_cancel_run(
    run_id: str,
    request: Request,
    response: Response,
    body: RetrievalActionKeyIn | None = None,
    admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalActionOut:
    del body
    try:
        payload = actions.cancel_run(session, actor=_actor(admin), run_id=run_id)
    except actions.RetrievalActionError as error:
        raise _refused(error) from error
    _wake(request)
    return _respond(payload, response)


@router.post("/runs/{run_id}/retry", response_model=RetrievalActionOut)
def post_retry_run(
    run_id: str,
    request: Request,
    response: Response,
    body: RetrievalActionKeyIn | None = None,
    idempotency_key: str | None = IDEMPOTENCY_HEADER,
    admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalActionOut:
    key = _resolve_key(
        idempotency_key,
        body or RetrievalActionKeyIn(),
        required=True,
        action="retry",
    )
    assert key is not None
    try:
        payload = actions.retry_run(
            session,
            actor=_actor(admin),
            run_id=run_id,
            idempotency_key=key,
        )
    except actions.RetrievalActionError as error:
        raise _refused(error) from error
    _wake(request)
    return _respond(payload, response)


@router.post("/spaces", response_model=RetrievalActionOut)
def post_build_space(
    body: RetrievalSpaceBuildIn,
    request: Request,
    response: Response,
    idempotency_key: str | None = IDEMPOTENCY_HEADER,
    admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalActionOut:
    key = _resolve_key(idempotency_key, body, required=True, action="build_space")
    assert key is not None
    try:
        payload = actions.build_space(
            session,
            actor=_actor(admin),
            idempotency_key=key,
            name=body.name,
            provider=body.provider,
            model=body.model,
            dim=body.dim,
            normalize=body.normalize,
            query_prefix=body.query_prefix,
            document_prefix=body.document_prefix,
        )
    except actions.RetrievalActionError as error:
        raise _refused(error) from error
    return _respond(payload, response)


@router.post("/spaces/{space_id}/activate", response_model=RetrievalActionOut)
def post_activate_space(
    space_id: str,
    request: Request,
    response: Response,
    body: RetrievalActionKeyIn | None = None,
    idempotency_key: str | None = IDEMPOTENCY_HEADER,
    admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalActionOut:
    key = _resolve_key(
        idempotency_key,
        body or RetrievalActionKeyIn(),
        required=True,
        action="activate_space",
    )
    assert key is not None
    try:
        payload = actions.activate_space(
            session, actor=_actor(admin), space_id=space_id, idempotency_key=key
        )
    except actions.RetrievalActionError as error:
        raise _refused(error) from error
    return _respond(payload, response)


@router.post("/spaces/{space_id}/retire", response_model=RetrievalActionOut)
def post_retire_space(
    space_id: str,
    body: RetrievalSpaceConfirmIn,
    request: Request,
    response: Response,
    idempotency_key: str | None = IDEMPOTENCY_HEADER,
    admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalActionOut:
    key = _resolve_key(idempotency_key, body, required=True, action="retire_space")
    assert key is not None
    try:
        payload = actions.retire_space(
            session,
            actor=_actor(admin),
            space_id=space_id,
            confirm_space_name=body.confirm_space_name,
            idempotency_key=key,
        )
    except actions.RetrievalActionError as error:
        raise _refused(error) from error
    return _respond(payload, response)


@router.post("/spaces/{space_id}/drop", response_model=RetrievalActionOut)
def post_drop_space(
    space_id: str,
    body: RetrievalSpaceConfirmIn,
    request: Request,
    response: Response,
    idempotency_key: str | None = IDEMPOTENCY_HEADER,
    admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalActionOut:
    key = _resolve_key(idempotency_key, body, required=True, action="drop_space")
    assert key is not None
    try:
        payload = actions.drop_space(
            session,
            actor=_actor(admin),
            space_id=space_id,
            confirm_space_name=body.confirm_space_name,
            force=body.force,
            idempotency_key=key,
        )
    except actions.RetrievalActionError as error:
        raise _refused(error) from error
    return _respond(payload, response)


@router.post("/cutover", response_model=RetrievalActionOut)
def post_cutover(
    body: RetrievalCutoverIn,
    request: Request,
    response: Response,
    idempotency_key: str | None = IDEMPOTENCY_HEADER,
    admin: Principal = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RetrievalActionOut:
    key = _resolve_key(idempotency_key, body, required=True, action="cutover")
    assert key is not None
    try:
        payload = actions.cutover(
            session,
            actor=_actor(admin),
            space_id=body.space_id,
            idempotency_key=key,
            limit=body.limit,
            batch_size=body.batch_size,
            force=body.force,
        )
    except actions.RetrievalActionError as error:
        raise _refused(error) from error
    _wake(request)
    return _respond(payload, response)


@router.post("/quality/compare", response_model=RetrievalActionOut)
def post_quality_compare(
    _admin: Principal = Depends(require_admin),
) -> RetrievalActionOut:
    raise _refused(actions.unsupported_lifecycle("quality_compare"))
