# VENDORED FILE — family canonical (ADR-0031 / ADR-0051). Source of truth:
# dev/contracts/retrieval_ops.py; vendored byte-identical into
# career-assistant in plan 51 Q1 (backend/app/storage/retrieval_ops.py) and
# study-assistant in Q3 by scripts/sync-retrieval-ops.sh, sha-checked by
# scripts/verify-wiring.sh, accepted by the shared fixture table
# (dev/contracts/retrieval-ops.fixtures.json — vendored alongside, loaded by
# every repo's retrieval-ops contract test). NEVER edit the vendored copy
# in-repo — change the dev canonical, then re-run the sync (contract changes
# = one dev commit + one sync run, never per-repo edits).
"""Family retrieval-operations contract (plan 51 Q0) — read/action vocabulary.

This module is the companion to :mod:`vector_contract` (ADR-0051). The
vector contract owns the store, the backends and the retrieval math; this
module owns the **administration vocabulary**: the read DTOs for the
Audit -> Retrieval tab, the action request/response shapes for
Tools -> Retrieval, the `vector.*` audit events, the `VECTOR_*` job types,
the run result contract, and the two bounded rollup schemas.

Pure stdlib — no SQLAlchemy, FastAPI, numpy or network. SQL adapters,
composers and HTTP routers stay app-side (ADR-0031); this module is the
shared shapes and the closed vocabularies every implementation must use.

**No raw text in DTOs.** Retrieval payloads and exports carry counts, ids,
scores, reasons, latencies and token usage only. They never select or carry
prompt text, document text, query text or generated output. The one lawful
raw text is the admin-authored golden-query fixture *input*
(:class:`GoldenQueryFixture`), which is never serialized through
:meth:`_DTO.to_dict`; the fixture wall pins that distinction. Raw embed
text already exists in ``ai_generations.prompt`` for the admin AI tab — the
Retrieval DTOs must not select that column (Q1 pins the payload keys).

**Compose, do not duplicate.** The surface reads ``ai_generations``
(embed calls), ``background_jobs`` (every run), ``audit_events`` (admin
actions), the vector tables (spaces/documents/records) and two bounded,
TTL-retained aggregate stores — ``retrieval_query_rollups`` and
``retrieval_coverage_snapshots``. There is no ``vector_events`` ledger and
no ``vector_index_failures`` table in v1: failures travel in the bounded
run-result ``failed_ids`` list.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

RETRIEVAL_CONTRACT_VERSION = "1"
RETRIEVAL_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# closed vocabularies
# ---------------------------------------------------------------------------


class SpaceStatus(StrEnum):
    """Space lifecycle; mirrors ``vector_contract.SpaceStatus`` (fixture-pinned)."""

    ACTIVE = "active"
    BUILDING = "building"
    RETIRED = "retired"


class DegradedReason(StrEnum):
    """Structured lexical-fallback reasons; mirrors ``vector_contract``."""

    PROVIDER_UNASSIGNED = "provider_unassigned"
    EMBED_FAILED = "embed_failed"
    INDEX_MISSING = "index_missing"
    SPACE_MISMATCH = "space_mismatch"
    OVER_CAP = "over_cap"


class RunStatus(StrEnum):
    """The ``background_jobs.status`` values a VECTOR_* run can carry."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GateStatus(StrEnum):
    """Coverage/quality gate result — ``unknown`` is the cold/never-reconciled state."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class FailureKind(StrEnum):
    """Failure groups; no separate failures table exists in v1."""

    EMBED_PROVIDER = "embed_provider"
    INDEXING = "indexing"
    CUTOVER_GATE = "cutover_gate"
    MAINTENANCE = "maintenance"


class MaintenanceAction(StrEnum):
    INDEX_REBUILD = "index-rebuild"
    VACUUM = "vacuum"
    ORPHAN_SWEEP = "orphan-sweep"
    RETRY_FAILED = "retry-failed"


class RetrievalAction(StrEnum):
    """Every action the one HTTP management surface exposes (§3)."""

    REINDEX = "reindex"
    CANCEL_RUN = "cancel_run"
    RETRY_RUN = "retry_run"
    BUILD_SPACE = "build_space"
    ACTIVATE_SPACE = "activate_space"
    RETIRE_SPACE = "retire_space"
    DROP_SPACE = "drop_space"
    MAINTENANCE = "maintenance"
    QUALITY_COMPARE = "quality_compare"


V1_VIEWS = ("summary", "requirements", "responsibilities", "skills", "body")
BACKENDS = ("pgvector", "sqlite_vec", "linear")

VECTOR_JOB_TYPES = (
    "VECTOR_REINDEX",
    "VECTOR_CUTOVER",
    "VECTOR_MAINTENANCE",
)
VECTOR_RUN_ACTIVE_STATUSES = (RunStatus.QUEUED, RunStatus.RUNNING)
VECTOR_RUN_TERMINAL_STATUSES = (
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
)

# ``audit_events.group`` for every vector action; the audit read filter's
# group enum grows to include this token in Q1.
VECTOR_AUDIT_GROUP = "vector"
VECTOR_AUDIT_EVENTS = (
    "vector.space.provisioned",
    "vector.space.activated",
    "vector.space.retired",
    "vector.space.dropped",
    "vector.space.reset",
    "vector.reindex.started",
    "vector.reindex.cancelled",
    "vector.reindex.retried",
    "vector.maintenance.started",
    "vector.model.changed",
    "vector.gate.failed",
    "vector.run.stalled",
    "vector.document.indexed",
)

FAILED_IDS_LIMIT = 500
COVERAGE_GATE = 0.995
QUALITY_K_DEFAULT = 5
QUALITY_FLOOR_RECALL = 0.80
QUALITY_FLOOR_PRECISION = 0.50

# Single-active-run and idempotency machinery (net-new in Q1; Q0 pins it).
VECTOR_LOCK_KEY_PREFIX = "vector_space:"
HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_STALE_SECONDS = 900  # stall N: 15 minutes without a heartbeat
REAPER_INTERVAL_SECONDS = 60
IDEMPOTENCY_KEY_MIN_LENGTH = 8
IDEMPOTENCY_KEY_MAX_LENGTH = 120
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
IDEMPOTENCY_UNIQUE_FIELDS = ("job_type", "idempotency_key")

# Alert defaults pinned at Q0 (§2C); Q1 emits through NotificationService.
QUERY_SLO_WINDOW_MINUTES = 15
QUERY_SLO_P95_MS = 1500
DEGRADED_RATE_THRESHOLD = 0.05
DEGRADED_RATE_WINDOW_MINUTES = 15
STALL_MINUTES = HEARTBEAT_STALE_SECONDS // 60
DAILY_CAP_DEFAULT = 3
SPACE_DROP_GRACE_DAYS = 7


# ---------------------------------------------------------------------------
# validation helpers
# ---------------------------------------------------------------------------


def _bad(field_name: str, message: str) -> ValueError:
    return ValueError(f"{field_name}: {message}")


def _int(value: Any, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _bad(field_name, f"must be an integer >= {minimum}")
    return value


def _optional_int(value: Any, field_name: str, *, minimum: int = 0) -> int | None:
    if value is None:
        return None
    return _int(value, field_name, minimum=minimum)


def _rate(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad(field_name, "must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise _bad(field_name, "must be between 0 and 1")
    return number


def _optional_rate(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _rate(value, field_name)


def _positive_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad(field_name, "must be a number")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise _bad(field_name, "must be > 0")
    return number


def _optional_positive_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _positive_float(value, field_name)


def _text(
    value: Any, field_name: str, *, required: bool = False, maximum: int = 200
) -> str:
    if value is None:
        if required:
            raise _bad(field_name, "must be non-empty")
        return ""
    text = str(value).strip()
    if required and not text:
        raise _bad(field_name, "must be non-empty")
    if len(text) > maximum:
        raise _bad(field_name, f"must be <= {maximum} characters")
    return text


def _optional_text(value: Any, field_name: str, *, maximum: int = 1000) -> str | None:
    if value is None:
        return None
    return _text(value, field_name, maximum=maximum) or None


def _enum(value: Any, enum_type: type[StrEnum], field_name: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as exc:
        raise _bad(
            field_name, f"must be one of {tuple(member.value for member in enum_type)}"
        ) from exc


def _enum_or_none(value: Any, enum_type: type[StrEnum], field_name: str) -> Any:
    if value is None:
        return None
    return _enum(value, enum_type, field_name)


def _strings(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _bad(field_name, "must be a sequence of ids")
    return tuple(_text(item, field_name) for item in value)


# ---------------------------------------------------------------------------
# no-raw-text rule
# ---------------------------------------------------------------------------

# Keys a Retrieval DTO/export may never carry. ``text_ref`` is deliberately
# absent: it is a reference/hash, not text. Golden-query input is the one
# exception and never passes through _DTO.to_dict.
FORBIDDEN_DTO_KEYS = frozenset(
    {
        "prompt",
        "prompt_text",
        "document",
        "document_text",
        "content",
        "body",
        "query",
        "query_text",
        "raw_text",
        "text",
        "output",
    }
)


def assert_no_raw_text(payload: Any, *, view_dimension_keys: bool = False) -> Any:
    """Raise when a payload carries a forbidden raw-text key (recursive).

    ``view_dimension_keys`` exempts the direct keys of a ``per_view_hits``
    map: ``body`` there is a view name, not document text. The exemption is
    deliberately local — a bare ``{"body": ...}`` payload still fails.
    """
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if not view_dimension_keys and str(key) in FORBIDDEN_DTO_KEYS:
                raise ValueError(f"retrieval DTO may not carry raw text key {key!r}")
            assert_no_raw_text(value, view_dimension_keys=str(key) == "per_view_hits")
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        for item in payload:
            assert_no_raw_text(item)
    return payload


def _plain(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


class _DTO:
    """Shared serializer: enums -> strings, tuples -> lists, raw text forbidden."""

    def to_dict(self) -> dict[str, Any]:
        return assert_no_raw_text(_plain(asdict(self)))


# ---------------------------------------------------------------------------
# read DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunScope(_DTO):
    kind: str | None = None
    view: str | None = None
    since: str | None = None

    def __post_init__(self) -> None:
        if self.view is not None and self.view not in V1_VIEWS:
            raise _bad("scope.view", f"must be one of {V1_VIEWS}")
        object.__setattr__(self, "kind", _optional_text(self.kind, "scope.kind"))
        object.__setattr__(self, "since", _optional_text(self.since, "scope.since"))


@dataclass(frozen=True)
class SpaceDTO(_DTO):
    """One row of the Spaces section / active-space card."""

    space_id: str
    name: str
    status: SpaceStatus
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
    gate: GateStatus = GateStatus.UNKNOWN
    as_of: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "space_id",
            _text(self.space_id, "space_id", required=True, maximum=80),
        )
        object.__setattr__(
            self, "name", _text(self.name, "name", required=True, maximum=120)
        )
        object.__setattr__(self, "status", _enum(self.status, SpaceStatus, "status"))
        object.__setattr__(
            self,
            "provider",
            _text(self.provider, "provider", required=True, maximum=40),
        )
        object.__setattr__(
            self, "model", _text(self.model, "model", required=True, maximum=120)
        )
        object.__setattr__(self, "dim", _int(self.dim, "dim", minimum=1))
        if self.backend not in BACKENDS:
            raise _bad("backend", f"must be one of {BACKENDS}")
        if self.metric != "cosine":
            raise _bad("metric", "must be 'cosine'")
        object.__setattr__(self, "documents", _int(self.documents, "documents"))
        object.__setattr__(self, "records", _int(self.records, "records"))
        object.__setattr__(self, "coverage", _optional_rate(self.coverage, "coverage"))
        object.__setattr__(self, "stale", _optional_int(self.stale, "stale"))
        object.__setattr__(self, "failed", _optional_int(self.failed, "failed"))
        object.__setattr__(self, "gate", _enum(self.gate, GateStatus, "gate"))
        for name in (
            "index_table",
            "created_at",
            "activated_at",
            "retired_at",
            "last_reindex_at",
            "last_error",
            "as_of",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))

    @property
    def cold(self) -> bool:
        """True when coverage was never reconciled — never a fake number."""
        return self.as_of is None and self.coverage is None

    @property
    def coverage_gate(self) -> GateStatus:
        if self.coverage is None:
            return GateStatus.UNKNOWN
        return GateStatus.PASS if self.coverage >= COVERAGE_GATE else GateStatus.FAIL


@dataclass(frozen=True)
class CoverageDTO(_DTO):
    """Latest ``retrieval_coverage_snapshots`` row; ``as_of=None`` is cold."""

    space_id: str
    as_of: str | None
    total: int
    missing: int
    stale: int
    failed: int
    embedded: int
    coverage: float | None
    gate: GateStatus = GateStatus.UNKNOWN
    ann_recall: float | None = None
    ann_recall_k: int | None = None
    probe_size: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "space_id",
            _text(self.space_id, "space_id", required=True, maximum=80),
        )
        object.__setattr__(self, "as_of", _optional_text(self.as_of, "as_of"))
        for name in ("total", "missing", "stale", "failed", "embedded"):
            object.__setattr__(self, name, _int(getattr(self, name), name))
        coverage = self.coverage
        if coverage is None and self.total > 0:
            coverage = self.embedded / self.total
        object.__setattr__(self, "coverage", _optional_rate(coverage, "coverage"))
        object.__setattr__(self, "gate", _enum(self.gate, GateStatus, "gate"))
        object.__setattr__(
            self, "ann_recall", _optional_rate(self.ann_recall, "ann_recall")
        )
        object.__setattr__(
            self,
            "ann_recall_k",
            _optional_int(self.ann_recall_k, "ann_recall_k", minimum=1),
        )
        object.__setattr__(
            self, "probe_size", _optional_int(self.probe_size, "probe_size")
        )

    @property
    def sampled(self) -> bool:
        return self.ann_recall is not None and self.probe_size is not None

    @property
    def cold(self) -> bool:
        return self.as_of is None


@dataclass(frozen=True)
class RunResultDTO(_DTO):
    """The VECTOR_* handler result contract (§3.2)."""

    scanned: int = 0
    embedded: int = 0
    skipped: int = 0
    failed: int = 0
    failed_ids: tuple[str, ...] = ()
    failed_ids_truncated: bool = False
    gate: GateStatus = GateStatus.UNKNOWN

    def __post_init__(self) -> None:
        for name in ("scanned", "embedded", "skipped", "failed"):
            object.__setattr__(self, name, _int(getattr(self, name), name))
        ids = _strings(self.failed_ids, "failed_ids")
        if len(ids) > FAILED_IDS_LIMIT:
            raise _bad("failed_ids", f"may carry at most {FAILED_IDS_LIMIT} ids")
        truncated = bool(self.failed_ids_truncated)
        if truncated and len(ids) != FAILED_IDS_LIMIT:
            raise _bad(
                "failed_ids",
                f"truncated result must carry exactly {FAILED_IDS_LIMIT} ids (got {len(ids)})",
            )
        if self.failed == 0 and (ids or truncated):
            raise _bad("failed_ids", "must be empty when failed == 0")
        if self.failed < len(ids):
            raise _bad("failed", "must be >= the number of listed failed_ids")
        object.__setattr__(self, "failed_ids", ids)
        object.__setattr__(self, "failed_ids_truncated", truncated)
        object.__setattr__(self, "gate", _enum(self.gate, GateStatus, "gate"))


@dataclass(frozen=True)
class RunDTO(_DTO):
    """One row of the Runs section (result only on the detail read)."""

    run_id: str
    space_id: str
    job_type: str
    status: RunStatus
    progress: int = 0
    stage: str | None = None
    scope: RunScope = RunScope()
    budget_tokens: int | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    heartbeat_at: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    idempotency_key: str | None = None
    lock_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "run_id", _text(self.run_id, "run_id", required=True, maximum=80)
        )
        object.__setattr__(
            self,
            "space_id",
            _text(self.space_id, "space_id", required=True, maximum=80),
        )
        if self.job_type not in VECTOR_JOB_TYPES:
            raise _bad("job_type", f"must be one of {VECTOR_JOB_TYPES}")
        object.__setattr__(self, "status", _enum(self.status, RunStatus, "status"))
        progress = _int(self.progress, "progress")
        if progress > 100:
            raise _bad("progress", "must be <= 100")
        object.__setattr__(self, "progress", progress)
        scope = (
            self.scope
            if isinstance(self.scope, RunScope)
            else RunScope(**dict(self.scope or {}))
        )
        object.__setattr__(self, "scope", scope)
        object.__setattr__(
            self,
            "budget_tokens",
            _optional_int(self.budget_tokens, "budget_tokens", minimum=1),
        )
        for name in (
            "stage",
            "created_at",
            "started_at",
            "finished_at",
            "heartbeat_at",
            "error",
            "idempotency_key",
            "lock_key",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        object.__setattr__(self, "cancel_requested", bool(self.cancel_requested))

    @property
    def active(self) -> bool:
        return self.status in VECTOR_RUN_ACTIVE_STATUSES

    @property
    def terminal(self) -> bool:
        return self.status in VECTOR_RUN_TERMINAL_STATUSES


@dataclass(frozen=True)
class RunDetailDTO(_DTO):
    run: RunDTO
    result: RunResultDTO | None = None
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run, RunDTO):
            raise _bad("run", "must be a RunDTO")
        if self.result is not None and not isinstance(self.result, RunResultDTO):
            raise _bad("result", "must be a RunResultDTO")
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise _bad("duration_seconds", "must be >= 0")


@dataclass(frozen=True)
class FailureGroupDTO(_DTO):
    """A Failures-section group; document ids are a bounded sample, never text."""

    kind: FailureKind
    space_id: str
    count: int
    last_seen: str | None = None
    document_ids: tuple[str, ...] = ()
    reason: DegradedReason | None = None
    retryable: bool = True
    run_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum(self.kind, FailureKind, "kind"))
        object.__setattr__(
            self,
            "space_id",
            _text(self.space_id, "space_id", required=True, maximum=80),
        )
        object.__setattr__(self, "count", _int(self.count, "count", minimum=1))
        object.__setattr__(
            self, "last_seen", _optional_text(self.last_seen, "last_seen")
        )
        object.__setattr__(
            self, "document_ids", _strings(self.document_ids, "document_ids")
        )
        object.__setattr__(
            self, "reason", _enum_or_none(self.reason, DegradedReason, "reason")
        )
        object.__setattr__(self, "retryable", bool(self.retryable))
        object.__setattr__(self, "run_id", _optional_text(self.run_id, "run_id"))


@dataclass(frozen=True)
class QueryHealthDTO(_DTO):
    """Query-health section: aggregates only, never query strings."""

    space_id: str
    window_start: str
    window_end: str
    p50_ms: float | None = None
    p95_ms: float | None = None
    candidate_p50: float | None = None
    candidate_p95: float | None = None
    zero_result_rate: float | None = None
    degraded_rate: float | None = None
    degraded_reasons: Mapping[str, int] = None  # type: ignore[assignment]
    per_view_hits: Mapping[str, int] = None  # type: ignore[assignment]
    ann_recall: float | None = None
    ann_recall_k: int | None = None
    probe_size: int | None = None
    sampled: bool = False
    sample_size: int = 0
    query_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "space_id",
            _text(self.space_id, "space_id", required=True, maximum=80),
        )
        object.__setattr__(
            self,
            "window_start",
            _text(self.window_start, "window_start", required=True),
        )
        object.__setattr__(
            self, "window_end", _text(self.window_end, "window_end", required=True)
        )
        for name in ("p50_ms", "p95_ms", "candidate_p50", "candidate_p95"):
            object.__setattr__(
                self, name, _optional_positive_float(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "zero_result_rate",
            _optional_rate(self.zero_result_rate, "zero_result_rate"),
        )
        object.__setattr__(
            self, "degraded_rate", _optional_rate(self.degraded_rate, "degraded_rate")
        )
        reasons = {
            str(key): _int(value, f"degraded_reasons.{key}")
            for key, value in dict(self.degraded_reasons or {}).items()
        }
        for reason in reasons:
            if reason not in {member.value for member in DegradedReason}:
                raise _bad("degraded_reasons", f"unknown reason {reason!r}")
        views = {
            str(key): _int(value, f"per_view_hits.{key}")
            for key, value in dict(self.per_view_hits or {}).items()
        }
        for view in views:
            if view not in V1_VIEWS:
                raise _bad("per_view_hits", f"unknown view {view!r}")
        object.__setattr__(self, "degraded_reasons", reasons)
        object.__setattr__(self, "per_view_hits", views)
        object.__setattr__(
            self, "ann_recall", _optional_rate(self.ann_recall, "ann_recall")
        )
        object.__setattr__(
            self,
            "ann_recall_k",
            _optional_int(self.ann_recall_k, "ann_recall_k", minimum=1),
        )
        object.__setattr__(
            self, "probe_size", _optional_int(self.probe_size, "probe_size")
        )
        object.__setattr__(self, "sampled", bool(self.sampled))
        object.__setattr__(self, "sample_size", _int(self.sample_size, "sample_size"))
        object.__setattr__(self, "query_count", _int(self.query_count, "query_count"))


@dataclass(frozen=True)
class UsageRowDTO(_DTO):
    day: str
    space_id: str
    kind: str
    calls: int
    tokens_in: int = 0
    tokens_out: int = 0
    reindex_calls: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "day", _text(self.day, "day", required=True, maximum=40)
        )
        object.__setattr__(
            self,
            "space_id",
            _text(self.space_id, "space_id", required=True, maximum=80),
        )
        object.__setattr__(
            self, "kind", _text(self.kind, "kind", required=True, maximum=80)
        )
        for name in ("calls", "tokens_in", "tokens_out", "reindex_calls"):
            object.__setattr__(self, name, _int(getattr(self, name), name))

    @property
    def tokens_total(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass(frozen=True)
class BudgetDTO(_DTO):
    window: str
    max_tokens: int
    used_tokens: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "window", _text(self.window, "window", required=True, maximum=20)
        )
        object.__setattr__(
            self, "max_tokens", _int(self.max_tokens, "max_tokens", minimum=1)
        )
        object.__setattr__(self, "used_tokens", _int(self.used_tokens, "used_tokens"))

    @property
    def exhausted(self) -> bool:
        return self.used_tokens >= self.max_tokens

    @property
    def remaining_tokens(self) -> int:
        return max(self.max_tokens - self.used_tokens, 0)


@dataclass(frozen=True)
class UsageDTO(_DTO):
    window_start: str
    window_end: str
    rows: tuple[UsageRowDTO, ...] = ()
    budget: BudgetDTO | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "window_start",
            _text(self.window_start, "window_start", required=True),
        )
        object.__setattr__(
            self, "window_end", _text(self.window_end, "window_end", required=True)
        )
        rows = tuple(
            row if isinstance(row, UsageRowDTO) else UsageRowDTO(**dict(row))
            for row in (self.rows or ())
        )
        object.__setattr__(self, "rows", rows)
        if self.budget is not None and not isinstance(self.budget, BudgetDTO):
            object.__setattr__(self, "budget", BudgetDTO(**dict(self.budget)))


# ---------------------------------------------------------------------------
# quality
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenQueryFixture:
    """Admin-authored golden query **input** — never a Retrieval DTO.

    ``query`` is lawful here (admin fixtures, not user traffic) and is
    deliberately not exposed by :class:`QualityDTO`; the fixture wall pins
    that a Quality DTO may not carry the query text.
    """

    query_id: str
    query: str
    expected_document_ids: tuple[str, ...]
    k: int = QUALITY_K_DEFAULT

    def __post_init__(self) -> None:
        _text(self.query_id, "query_id", required=True, maximum=120)
        _text(self.query, "query", required=True, maximum=2000)
        ids = _strings(self.expected_document_ids, "expected_document_ids")
        if not ids:
            raise _bad("expected_document_ids", "must be non-empty")
        if _int(self.k, "k", minimum=1) > 100:
            raise _bad("k", "must be <= 100")
        object.__setattr__(self, "expected_document_ids", ids)
        object.__setattr__(self, "k", int(self.k))

    @classmethod
    def from_fixture(cls, row: Mapping[str, Any]) -> GoldenQueryFixture:
        """Build from the admin fixture JSON shape (camelCase, one place)."""
        return cls(
            query_id=row["queryId"],
            query=row["query"],
            expected_document_ids=tuple(row["expectedDocumentIds"]),
            k=row.get("k", QUALITY_K_DEFAULT),
        )

    def to_runner_dict(self) -> dict[str, Any]:
        """Fixture-runner shape (the only place query text is serialized)."""
        return {
            "queryId": self.query_id,
            "query": self.query,
            "expectedDocumentIds": list(self.expected_document_ids),
            "k": self.k,
        }


@dataclass(frozen=True)
class GoldenQuerySet:
    """A versioned golden-query set for one space (admin fixture input)."""

    space_id: str
    set_version: int
    queries: tuple[GoldenQueryFixture, ...]
    k: int = QUALITY_K_DEFAULT
    floor_recall: float = QUALITY_FLOOR_RECALL
    floor_precision: float = QUALITY_FLOOR_PRECISION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "space_id",
            _text(self.space_id, "space_id", required=True, maximum=80),
        )
        object.__setattr__(
            self, "set_version", _int(self.set_version, "set_version", minimum=1)
        )
        object.__setattr__(self, "k", _int(self.k, "k", minimum=1))
        queries = tuple(
            query
            if isinstance(query, GoldenQueryFixture)
            else GoldenQueryFixture(**dict(query))
            for query in (self.queries or ())
        )
        if not queries:
            raise _bad("queries", "a golden set must be non-empty")
        if any(query.k != self.k for query in queries):
            raise _bad("queries", "every golden query must use the set's k")
        object.__setattr__(self, "queries", queries)
        object.__setattr__(
            self, "floor_recall", _rate(self.floor_recall, "floor_recall")
        )
        object.__setattr__(
            self, "floor_precision", _rate(self.floor_precision, "floor_precision")
        )

    @classmethod
    def from_fixture(cls, row: Mapping[str, Any]) -> GoldenQuerySet:
        """Build from the admin fixture JSON shape (camelCase, one place)."""
        floor = row.get("floor", {})
        return cls(
            space_id=row["spaceId"],
            set_version=row["setVersion"],
            k=row.get("k", QUALITY_K_DEFAULT),
            floor_recall=floor.get("recall", QUALITY_FLOOR_RECALL),
            floor_precision=floor.get("precision", QUALITY_FLOOR_PRECISION),
            queries=tuple(
                GoldenQueryFixture.from_fixture(item) for item in row["queries"]
            ),
        )

    @property
    def revision_key(self) -> str:
        return f"{self.space_id}:v{self.set_version}"

    def to_runner_dict(self) -> dict[str, Any]:
        return {
            "spaceId": self.space_id,
            "setVersion": self.set_version,
            "k": self.k,
            "floor": {
                "recall": self.floor_recall,
                "precision": self.floor_precision,
            },
            "queries": [query.to_runner_dict() for query in self.queries],
        }


def _quality_query(
    golden: GoldenQueryFixture,
    retrieved: Sequence[str],
    *,
    k: int | None = None,
) -> QualityQueryResultDTO:
    top_k = list(retrieved)[: (k or golden.k)]
    expected = list(golden.expected_document_ids)
    expected_set = set(expected)
    hits = len(expected_set.intersection(top_k))
    recall = hits / len(expected_set) if expected_set else 0.0
    # Precision over the required set, not empty padding: a perfect hit of
    # a two-id golden set at k=5 scores 1.0, not 0.4.
    precision_denominator = max(1, min(k or golden.k, len(expected_set)))
    precision = hits / precision_denominator
    missing = tuple(doc_id for doc_id in expected if doc_id not in top_k)
    return QualityQueryResultDTO(
        query_id=golden.query_id,
        expected_document_ids=tuple(expected),
        retrieved_document_ids=tuple(top_k),
        recall_at_k=recall,
        precision_at_k=precision,
        missing_document_ids=missing,
        passed=recall >= QUALITY_FLOOR_RECALL and precision >= QUALITY_FLOOR_PRECISION,
    )


@dataclass(frozen=True)
class QualityQueryResultDTO(_DTO):
    query_id: str
    expected_document_ids: tuple[str, ...]
    retrieved_document_ids: tuple[str, ...]
    recall_at_k: float
    precision_at_k: float
    missing_document_ids: tuple[str, ...] = ()
    passed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "query_id",
            _text(self.query_id, "query_id", required=True, maximum=120),
        )
        for name in (
            "expected_document_ids",
            "retrieved_document_ids",
            "missing_document_ids",
        ):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        object.__setattr__(self, "recall_at_k", _rate(self.recall_at_k, "recall_at_k"))
        object.__setattr__(
            self, "precision_at_k", _rate(self.precision_at_k, "precision_at_k")
        )
        object.__setattr__(self, "passed", bool(self.passed))


@dataclass(frozen=True)
class QualityDTO(_DTO):
    space_id: str
    set_version: int
    k: int
    recall_at_k: float
    precision_at_k: float
    passed: bool
    queries: tuple[QualityQueryResultDTO, ...] = ()
    floor_recall: float = QUALITY_FLOOR_RECALL
    floor_precision: float = QUALITY_FLOOR_PRECISION
    generated_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "space_id",
            _text(self.space_id, "space_id", required=True, maximum=80),
        )
        object.__setattr__(
            self, "set_version", _int(self.set_version, "set_version", minimum=1)
        )
        object.__setattr__(self, "k", _int(self.k, "k", minimum=1))
        object.__setattr__(self, "recall_at_k", _rate(self.recall_at_k, "recall_at_k"))
        object.__setattr__(
            self, "precision_at_k", _rate(self.precision_at_k, "precision_at_k")
        )
        object.__setattr__(self, "passed", bool(self.passed))
        queries = tuple(
            query
            if isinstance(query, QualityQueryResultDTO)
            else QualityQueryResultDTO(**dict(query))
            for query in (self.queries or ())
        )
        object.__setattr__(self, "queries", queries)
        object.__setattr__(
            self, "floor_recall", _rate(self.floor_recall, "floor_recall")
        )
        object.__setattr__(
            self, "floor_precision", _rate(self.floor_precision, "floor_precision")
        )
        object.__setattr__(
            self, "generated_at", _optional_text(self.generated_at, "generated_at")
        )

    @property
    def activation_gate(self) -> GateStatus:
        return GateStatus.PASS if self.passed else GateStatus.FAIL


def evaluate_quality(
    space_id: str,
    set_version: int,
    golden_queries: Sequence[GoldenQueryFixture],
    retrieved_by_query: Mapping[str, Sequence[str]],
    *,
    k: int = QUALITY_K_DEFAULT,
    generated_at: str | None = None,
) -> QualityDTO:
    """Score a golden set; returns the quality DTO with no query text."""
    if not golden_queries:
        raise _bad("golden_queries", "must be non-empty")
    results = tuple(
        _quality_query(row, retrieved_by_query.get(row.query_id, ()), k=k)
        for row in golden_queries
    )
    recall = sum(row.recall_at_k for row in results) / len(results)
    precision = sum(row.precision_at_k for row in results) / len(results)
    return QualityDTO(
        space_id=space_id,
        set_version=set_version,
        k=k,
        recall_at_k=recall,
        precision_at_k=precision,
        passed=recall >= QUALITY_FLOOR_RECALL and precision >= QUALITY_FLOOR_PRECISION,
        queries=results,
        generated_at=generated_at,
    )


def evaluate_quality_set(
    golden_set: GoldenQuerySet,
    retrieved_by_query: Mapping[str, Sequence[str]],
    *,
    generated_at: str | None = None,
) -> QualityDTO:
    """Score a versioned per-space golden set (query text stays fixture-only)."""
    return evaluate_quality(
        golden_set.space_id,
        golden_set.set_version,
        golden_set.queries,
        retrieved_by_query,
        k=golden_set.k,
        generated_at=generated_at,
    )


@dataclass(frozen=True)
class QualityCompareDTO(_DTO):
    """Pre-cutover compare: old vs new space over the same golden set."""

    old_space_id: str
    new_space_id: str
    set_version: int
    k: int
    old_recall_at_k: float
    old_precision_at_k: float
    new_recall_at_k: float
    new_precision_at_k: float
    passed: bool
    floor_recall: float = QUALITY_FLOOR_RECALL
    floor_precision: float = QUALITY_FLOOR_PRECISION
    required_for_activation: bool = True
    queries: tuple[QualityQueryResultDTO, ...] = ()
    generated_at: str | None = None

    def __post_init__(self) -> None:
        for name in ("old_space_id", "new_space_id"):
            object.__setattr__(
                self, name, _text(getattr(self, name), name, required=True, maximum=80)
            )
        object.__setattr__(
            self, "set_version", _int(self.set_version, "set_version", minimum=1)
        )
        object.__setattr__(self, "k", _int(self.k, "k", minimum=1))
        for name in (
            "old_recall_at_k",
            "old_precision_at_k",
            "new_recall_at_k",
            "new_precision_at_k",
            "floor_recall",
            "floor_precision",
        ):
            object.__setattr__(self, name, _rate(getattr(self, name), name))
        object.__setattr__(self, "passed", bool(self.passed))
        object.__setattr__(
            self, "required_for_activation", bool(self.required_for_activation)
        )
        queries = tuple(
            query
            if isinstance(query, QualityQueryResultDTO)
            else QualityQueryResultDTO(**dict(query))
            for query in (self.queries or ())
        )
        object.__setattr__(self, "queries", queries)
        object.__setattr__(
            self, "generated_at", _optional_text(self.generated_at, "generated_at")
        )

    @property
    def recall_delta(self) -> float:
        return self.new_recall_at_k - self.old_recall_at_k

    @property
    def precision_delta(self) -> float:
        return self.new_precision_at_k - self.old_precision_at_k


def evaluate_quality_compare(
    old_space_id: str,
    new_space_id: str,
    set_version: int,
    golden_queries: Sequence[GoldenQueryFixture],
    old_retrieved: Mapping[str, Sequence[str]],
    new_retrieved: Mapping[str, Sequence[str]],
    *,
    k: int = QUALITY_K_DEFAULT,
    generated_at: str | None = None,
) -> QualityCompareDTO:
    old = evaluate_quality(
        old_space_id,
        set_version,
        golden_queries,
        old_retrieved,
        k=k,
        generated_at=generated_at,
    )
    new = evaluate_quality(
        new_space_id,
        set_version,
        golden_queries,
        new_retrieved,
        k=k,
        generated_at=generated_at,
    )
    return QualityCompareDTO(
        old_space_id=old_space_id,
        new_space_id=new_space_id,
        set_version=set_version,
        k=k,
        old_recall_at_k=old.recall_at_k,
        old_precision_at_k=old.precision_at_k,
        new_recall_at_k=new.recall_at_k,
        new_precision_at_k=new.precision_at_k,
        passed=new.passed,
        queries=new.queries,
        generated_at=generated_at,
    )


@dataclass(frozen=True)
class ActivationGateDTO(_DTO):
    """Activation needs coverage **and** the pre-cutover quality compare."""

    space_id: str
    coverage: GateStatus
    quality: GateStatus
    allowed: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "space_id",
            _text(self.space_id, "space_id", required=True, maximum=80),
        )
        object.__setattr__(
            self, "coverage", _enum(self.coverage, GateStatus, "coverage")
        )
        object.__setattr__(self, "quality", _enum(self.quality, GateStatus, "quality"))
        object.__setattr__(self, "allowed", bool(self.allowed))
        object.__setattr__(self, "reasons", _strings(self.reasons, "reasons"))


# ---------------------------------------------------------------------------
# action request / response
# ---------------------------------------------------------------------------

_MUTATING_ACTIONS = frozenset(
    {
        RetrievalAction.REINDEX,
        RetrievalAction.CANCEL_RUN,
        RetrievalAction.RETRY_RUN,
        RetrievalAction.BUILD_SPACE,
        RetrievalAction.ACTIVATE_SPACE,
        RetrievalAction.RETIRE_SPACE,
        RetrievalAction.DROP_SPACE,
        RetrievalAction.MAINTENANCE,
    }
)
_SPACE_ACTIONS = frozenset(
    {
        RetrievalAction.REINDEX,
        RetrievalAction.BUILD_SPACE,
        RetrievalAction.ACTIVATE_SPACE,
        RetrievalAction.RETIRE_SPACE,
        RetrievalAction.DROP_SPACE,
        RetrievalAction.MAINTENANCE,
    }
)


def validate_idempotency_key(value: Any) -> str:
    key = _text(
        value, "idempotency_key", required=True, maximum=IDEMPOTENCY_KEY_MAX_LENGTH
    )
    if len(key) < IDEMPOTENCY_KEY_MIN_LENGTH:
        raise _bad(
            "idempotency_key",
            f"must be at least {IDEMPOTENCY_KEY_MIN_LENGTH} characters",
        )
    return key


@dataclass(frozen=True)
class RetrievalActionRequest(_DTO):
    action: RetrievalAction
    idempotency_key: str | None = None
    space_id: str | None = None
    run_id: str | None = None
    compare_space_id: str | None = None
    kind: str | None = None
    view: str | None = None
    since: str | None = None
    maintenance_action: MaintenanceAction | None = None
    confirm_space_name: str | None = None
    dry_run: bool = False

    def __post_init__(self) -> None:
        action = _enum(self.action, RetrievalAction, "action")
        object.__setattr__(self, "action", action)
        object.__setattr__(
            self, "space_id", _optional_text(self.space_id, "space_id", maximum=80)
        )
        object.__setattr__(
            self, "run_id", _optional_text(self.run_id, "run_id", maximum=80)
        )
        object.__setattr__(
            self,
            "compare_space_id",
            _optional_text(self.compare_space_id, "compare_space_id", maximum=80),
        )
        object.__setattr__(self, "kind", _optional_text(self.kind, "kind", maximum=80))
        object.__setattr__(self, "view", _optional_text(self.view, "view", maximum=40))
        object.__setattr__(self, "since", _optional_text(self.since, "since"))
        object.__setattr__(
            self,
            "maintenance_action",
            _enum_or_none(
                self.maintenance_action, MaintenanceAction, "maintenance_action"
            ),
        )
        object.__setattr__(
            self,
            "confirm_space_name",
            _optional_text(self.confirm_space_name, "confirm_space_name"),
        )
        object.__setattr__(self, "dry_run", bool(self.dry_run))

        if self.view is not None and self.view not in V1_VIEWS:
            raise _bad("view", f"must be one of {V1_VIEWS}")
        if action in _SPACE_ACTIONS and not self.space_id:
            raise _bad("space_id", f"required for {action}")
        if (
            action in (RetrievalAction.CANCEL_RUN, RetrievalAction.RETRY_RUN)
            and not self.run_id
        ):
            raise _bad("run_id", f"required for {action}")
        if action == RetrievalAction.QUALITY_COMPARE:
            if not self.space_id or not self.compare_space_id:
                raise _bad(
                    "compare_space_id",
                    "quality_compare requires space_id and compare_space_id",
                )
            if self.space_id == self.compare_space_id:
                raise _bad("compare_space_id", "must differ from space_id")
        if action == RetrievalAction.MAINTENANCE and self.maintenance_action is None:
            raise _bad("maintenance_action", "required for maintenance")
        if (
            action != RetrievalAction.MAINTENANCE
            and self.maintenance_action is not None
        ):
            raise _bad("maintenance_action", "only valid for maintenance")
        if action in (RetrievalAction.DROP_SPACE, RetrievalAction.RETIRE_SPACE):
            if not self.confirm_space_name:
                raise _bad(
                    "confirm_space_name", f"typed confirmation required for {action}"
                )
            if self.confirm_space_name != self.space_id:
                raise _bad("confirm_space_name", "must equal space_id")
        if action in _MUTATING_ACTIONS:
            if not self.idempotency_key:
                raise _bad("idempotency_key", f"required for {action}")
            object.__setattr__(
                self, "idempotency_key", validate_idempotency_key(self.idempotency_key)
            )


@dataclass(frozen=True)
class RetrievalActionResponse(_DTO):
    action: RetrievalAction
    accepted: bool
    audit_event: str
    http_status: int = 202
    deduplicated: bool = False
    run_id: str | None = None
    status: RunStatus | None = None
    idempotency_key: str | None = None
    message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "action", _enum(self.action, RetrievalAction, "action")
        )
        object.__setattr__(self, "accepted", bool(self.accepted))
        if self.audit_event not in VECTOR_AUDIT_EVENTS:
            raise _bad("audit_event", f"must be one of {VECTOR_AUDIT_EVENTS}")
        if self.http_status not in (200, 202, 409):
            raise _bad("http_status", "must be 200, 202 or 409")
        object.__setattr__(self, "deduplicated", bool(self.deduplicated))
        object.__setattr__(self, "run_id", _optional_text(self.run_id, "run_id"))
        object.__setattr__(
            self, "status", _enum_or_none(self.status, RunStatus, "status")
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _optional_text(self.idempotency_key, "idempotency_key"),
        )
        object.__setattr__(self, "message", _text(self.message, "message", maximum=500))


# ---------------------------------------------------------------------------
# alert defaults (§2C) — pinned at Q0, emitted by Q1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlertDefault:
    kind: str
    condition: str
    threshold: str
    window_minutes: int
    dedup_key: str
    recovery: str
    manage_url: str
    daily_cap: int


ALERT_DEFAULTS = (
    AlertDefault(
        kind="retrieval.coverage_low",
        condition="coverage below the gate with no active building run",
        threshold=f"coverage < {COVERAGE_GATE}",
        window_minutes=0,
        dedup_key="space",
        recovery="coverage gate clears",
        manage_url="/settings/tools?section=retrieval",
        daily_cap=3,
    ),
    AlertDefault(
        kind="retrieval.reindex_failed",
        condition="a VECTOR_* run reaches terminal failed",
        threshold="status == failed",
        window_minutes=0,
        dedup_key="space+kind",
        recovery="next successful run",
        manage_url="/settings/audit?tab=retrieval&section=runs&detail=<run_id>",
        daily_cap=5,
    ),
    AlertDefault(
        kind="retrieval.reindex_stalled",
        condition="a non-terminal run makes no progress past the stall window",
        threshold=f"no heartbeat/progress > {STALL_MINUTES} min",
        window_minutes=STALL_MINUTES,
        dedup_key="run_id",
        recovery="progress resumes or the run is cancelled/reaped",
        manage_url="/settings/audit?tab=retrieval&section=runs&detail=<run_id>",
        daily_cap=3,
    ),
    AlertDefault(
        kind="retrieval.quality_gate",
        condition="the pre-cutover golden-query compare misses the floor",
        threshold=f"recall < {QUALITY_FLOOR_RECALL} or precision < {QUALITY_FLOOR_PRECISION}",
        window_minutes=0,
        dedup_key="space",
        recovery="the compare passes",
        manage_url="/settings/audit?tab=retrieval&section=quality",
        daily_cap=3,
    ),
    AlertDefault(
        kind="retrieval.query_slo",
        condition="query p95 exceeds the budget for the SLO window",
        threshold=f"p95 > {QUERY_SLO_P95_MS} ms for {QUERY_SLO_WINDOW_MINUTES} min",
        window_minutes=QUERY_SLO_WINDOW_MINUTES,
        dedup_key="space",
        recovery="p95 returns below budget",
        manage_url="/settings/audit?tab=retrieval&section=query-health",
        daily_cap=2,
    ),
    AlertDefault(
        kind="retrieval.degraded_rate",
        condition="the lexical-fallback share exceeds the threshold",
        threshold=f"degraded > {DEGRADED_RATE_THRESHOLD:.0%} over {DEGRADED_RATE_WINDOW_MINUTES} min",
        window_minutes=DEGRADED_RATE_WINDOW_MINUTES,
        dedup_key="space+reason",
        recovery="the share returns below threshold",
        manage_url="/settings/audit?tab=retrieval&section=query-health",
        daily_cap=3,
    ),
    AlertDefault(
        kind="retrieval.provider_unassigned",
        condition="the embeddings task has no provider/model assignment",
        threshold="ai.tasks embeddings slot unassigned",
        window_minutes=0,
        dedup_key="singleton",
        recovery="an embeddings assignment is saved",
        manage_url="/settings/tools?section=retrieval",
        daily_cap=1,
    ),
    AlertDefault(
        kind="retrieval.index_missing",
        condition="the pgvector extension/index is absent on web",
        threshold="extension or index absent",
        window_minutes=0,
        dedup_key="space",
        recovery="provision/maintenance recreates it",
        manage_url="/settings/tools?section=retrieval",
        daily_cap=2,
    ),
    AlertDefault(
        kind="retrieval.budget_exhausted",
        condition="the token-denominated embed budget is exhausted",
        threshold="AIBudget(task_type='embed') exhausted",
        window_minutes=0,
        dedup_key="window",
        recovery="the next budget window opens",
        manage_url="/settings/audit?tab=retrieval&section=usage",
        daily_cap=1,
    ),
    AlertDefault(
        kind="retrieval.space_drop_pending",
        condition="a retired space is past the drop grace period",
        threshold=f"retired > {SPACE_DROP_GRACE_DAYS} days",
        window_minutes=0,
        dedup_key="space",
        recovery="the space is dropped",
        manage_url="/settings/tools?section=retrieval",
        daily_cap=2,
    ),
)


# ---------------------------------------------------------------------------
# data seams (§3.2) — Q0 schema decisions; Q1 creates, plan 50 P1/P2 writes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnSpec:
    table: str
    column: str
    sql_type: str
    nullable: bool
    default: str
    note: str


@dataclass(frozen=True)
class RollupSpec:
    table: str
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]
    latency_buckets_ms: tuple[int, ...]
    ttl_days: int
    lifecycle: str
    inventory_rows: tuple[str, ...]
    written_by: str


@dataclass(frozen=True)
class BackgroundJobSeams:
    idempotency_column: str
    idempotency_unique_fields: tuple[str, ...]
    idempotency_ttl_seconds: int
    lock_key_column: str
    lock_key_prefix: str
    active_statuses: tuple[str, ...]
    heartbeat_interval_seconds: int
    heartbeat_stale_seconds: int
    reaper_interval_seconds: int
    reaper_action: str


AI_GENERATIONS_METADATA = ColumnSpec(
    table="ai_generations",
    column="metadata",
    sql_type="JSONB (JSON on SQLite)",
    nullable=False,
    default="'{}'",
    note=(
        "caller-supplied embedding tags: space_id, kind, view, chunk_index — "
        "passed through the gateway call like run_id/run_stage, never written "
        "by the gateway itself; no prompt/document text"
    ),
)
AI_GENERATIONS_METADATA_SCHEMA_VERSION = ColumnSpec(
    table="ai_generations",
    column="metadata_schema_version",
    sql_type="SMALLINT",
    nullable=False,
    default="1",
    note="sibling version pin for the metadata document; bump on an incompatible shape change",
)

RETRIEVAL_QUERY_ROLLUPS = RollupSpec(
    table="retrieval_query_rollups",
    dimensions=(
        "space_id",
        "kind",
        "view",
        "degraded_reason",
        "bucket_start",
        "bucket_width",
    ),
    measures=("count", "zero_results", "candidates_sum", "latency_histogram"),
    latency_buckets_ms=(25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
    ttl_days=30,
    lifecycle="operational",
    inventory_rows=(
        "retrieval_query_rollups :: operational",
        "retrieval_query_rollups.latency_histogram :: keep-open bounded latency histogram (le buckets + overflow; TTL 30d)",
    ),
    written_by="plan 50 P2 telemetry hooks (batched off the request hot path)",
)

RETRIEVAL_COVERAGE_SNAPSHOTS = RollupSpec(
    table="retrieval_coverage_snapshots",
    dimensions=("space_id", "kind", "as_of"),
    measures=(
        "total",
        "missing",
        "stale",
        "failed",
        "embedded",
        "ann_recall",
        "ann_recall_k",
        "probe_size",
    ),
    latency_buckets_ms=(),
    ttl_days=90,
    lifecycle="operational",
    inventory_rows=("retrieval_coverage_snapshots :: operational",),
    written_by="reconcile pass + periodic maintenance ANN-recall probe (never a dashboard request)",
)

BACKGROUND_JOB_SEAMS = BackgroundJobSeams(
    idempotency_column="idempotency_key",
    idempotency_unique_fields=IDEMPOTENCY_UNIQUE_FIELDS,
    idempotency_ttl_seconds=IDEMPOTENCY_TTL_SECONDS,
    lock_key_column="lock_key",
    lock_key_prefix=VECTOR_LOCK_KEY_PREFIX,
    active_statuses=tuple(member.value for member in VECTOR_RUN_ACTIVE_STATUSES),
    heartbeat_interval_seconds=HEARTBEAT_INTERVAL_SECONDS,
    heartbeat_stale_seconds=HEARTBEAT_STALE_SECONDS,
    reaper_interval_seconds=REAPER_INTERVAL_SECONDS,
    reaper_action=(
        "running row with heartbeat_at older than the stale window -> failed "
        "(error='stalled: no heartbeat for 15m'), emit vector.run.stalled, release lock_key"
    ),
)

DATA_SEAM_INVENTORY = (
    "ai_generations.metadata :: keep-open caller-supplied embedding tags (space_id/kind/view/chunk_index; schema version sibling; never text)",
    "retrieval_query_rollups :: operational (TTL 30d — aggregate, not an audit ledger)",
    "retrieval_coverage_snapshots :: operational (TTL 90d — latest snapshot wins; cold means never reconciled)",
    "background_jobs.idempotency_key :: indexed request replay key (partial unique on job_type+idempotency_key; 24h TTL)",
    "background_jobs.lock_key :: partial unique active-run lock (vector_space:<space_id>; queued/running only)",
)


def run_lock_key(space_id: str) -> str:
    """The DB-level single-active-run key for a space."""
    return f"{VECTOR_LOCK_KEY_PREFIX}{_text(space_id, 'space_id', required=True, maximum=80)}"


def idempotency_scope(job_type: str, key: str) -> tuple[str, str]:
    """The unique scope of a request/replay key (never app-enforced only)."""
    if job_type not in VECTOR_JOB_TYPES:
        raise _bad("job_type", f"must be one of {VECTOR_JOB_TYPES}")
    return (job_type, validate_idempotency_key(key))


def coverage_ratio(embedded: int, total: int) -> float | None:
    """Coverage fraction; zero total is the cold state, not 0%."""
    embedded = _int(embedded, "embedded")
    total = _int(total, "total")
    if total == 0:
        return None
    return embedded / total


def truncate_failed_ids(
    ids: Sequence[str], limit: int = FAILED_IDS_LIMIT
) -> tuple[tuple[str, ...], bool]:
    """Bound a run's failed ids; the flag says whether more existed."""
    if limit < 1:
        raise _bad("limit", "must be >= 1")
    values = _strings(ids, "ids")
    return (values[:limit], len(values) > limit)


__all__ = [
    "AI_GENERATIONS_METADATA",
    "AI_GENERATIONS_METADATA_SCHEMA_VERSION",
    "ALERT_DEFAULTS",
    "BACKENDS",
    "BACKGROUND_JOB_SEAMS",
    "COVERAGE_GATE",
    "DAILY_CAP_DEFAULT",
    "DATA_SEAM_INVENTORY",
    "DEGRADED_RATE_THRESHOLD",
    "DEGRADED_RATE_WINDOW_MINUTES",
    "FAILED_IDS_LIMIT",
    "FORBIDDEN_DTO_KEYS",
    "HEARTBEAT_INTERVAL_SECONDS",
    "HEARTBEAT_STALE_SECONDS",
    "IDEMPOTENCY_KEY_MAX_LENGTH",
    "IDEMPOTENCY_KEY_MIN_LENGTH",
    "IDEMPOTENCY_TTL_SECONDS",
    "IDEMPOTENCY_UNIQUE_FIELDS",
    "QUALITY_FLOOR_PRECISION",
    "QUALITY_FLOOR_RECALL",
    "QUALITY_K_DEFAULT",
    "QUERY_SLO_P95_MS",
    "QUERY_SLO_WINDOW_MINUTES",
    "REAPER_INTERVAL_SECONDS",
    "RETRIEVAL_CONTRACT_VERSION",
    "RETRIEVAL_COVERAGE_SNAPSHOTS",
    "RETRIEVAL_QUERY_ROLLUPS",
    "RETRIEVAL_SCHEMA_VERSION",
    "SPACE_DROP_GRACE_DAYS",
    "STALL_MINUTES",
    "V1_VIEWS",
    "VECTOR_AUDIT_EVENTS",
    "VECTOR_AUDIT_GROUP",
    "VECTOR_JOB_TYPES",
    "VECTOR_LOCK_KEY_PREFIX",
    "VECTOR_RUN_ACTIVE_STATUSES",
    "VECTOR_RUN_TERMINAL_STATUSES",
    "ActivationGateDTO",
    "AlertDefault",
    "BackgroundJobSeams",
    "BudgetDTO",
    "ColumnSpec",
    "CoverageDTO",
    "DegradedReason",
    "FailureGroupDTO",
    "FailureKind",
    "GateStatus",
    "GoldenQueryFixture",
    "GoldenQuerySet",
    "MaintenanceAction",
    "QualityCompareDTO",
    "QualityDTO",
    "QualityQueryResultDTO",
    "QueryHealthDTO",
    "RollupSpec",
    "RunDTO",
    "RunDetailDTO",
    "RunResultDTO",
    "RunScope",
    "RunStatus",
    "SpaceDTO",
    "SpaceStatus",
    "UsageDTO",
    "UsageRowDTO",
    "assert_no_raw_text",
    "coverage_ratio",
    "evaluate_quality",
    "evaluate_quality_compare",
    "evaluate_quality_set",
    "idempotency_scope",
    "run_lock_key",
    "truncate_failed_ids",
    "validate_idempotency_key",
]
