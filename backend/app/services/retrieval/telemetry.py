"""Off-hot-path query-health telemetry for the v1 vector search.

The request path only appends one bounded sample to an in-memory deque; a
daemon flusher (started by the app lifespan) aggregates samples into
``retrieval_query_rollups`` in a 5-minute bucket. **No query text ever enters
this module** — the sample is latency, candidate count, the zero-result flag,
the optional view and a structured degraded reason.

The rollup table is an operational aggregate with a 30-day TTL, not an audit
ledger.
"""

from __future__ import annotations

import contextlib
import threading
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ...domain.models import RetrievalQueryRollup
from ...storage.retrieval_ops import (
    RETRIEVAL_QUERY_ROLLUPS,
    DegradedReason,
)
from .v1_store import V1_KIND, V1_SPACE_ID

logger = structlog.get_logger(__name__)

BUCKET_WIDTH_SECONDS = 300
ROLLUP_TTL_DAYS = RETRIEVAL_QUERY_ROLLUPS.ttl_days
MAX_PENDING = 512
FLUSH_INTERVAL_SECONDS = 60.0
LATENCY_BUCKETS_MS = RETRIEVAL_QUERY_ROLLUPS.latency_buckets_ms
OVERFLOW_KEY = "inf"

_VALID_REASONS = frozenset(member.value for member in DegradedReason)


def _iso(value: datetime) -> str:
    moment = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return moment.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class QuerySample:
    latency_ms: int
    candidates: int
    zero_results: bool
    kind: str = V1_KIND
    space_id: str = V1_SPACE_ID
    view: str | None = None
    degraded_reason: str | None = None
    at: datetime | None = None


@dataclass
class _Bucket:
    count: int = 0
    zero_results: int = 0
    candidates_sum: int = 0
    histogram: dict[str, int] | None = None


def _empty_histogram() -> dict[str, int]:
    return {str(bound): 0 for bound in LATENCY_BUCKETS_MS} | {OVERFLOW_KEY: 0}


def _merged_histogram(left: dict[str, int] | None, right: dict[str, int]) -> dict[str, int]:
    merged = {str(bound): 0 for bound in LATENCY_BUCKETS_MS} | {OVERFLOW_KEY: 0}
    for source in (left or {}, right):
        for key, value in source.items():
            try:
                merged[str(key)] = int(merged.get(str(key), 0)) + int(value)
            except (TypeError, ValueError):
                continue
    return merged


def _histogram_for(latency_ms: int) -> dict[str, int]:
    """One cumulative ``le`` histogram point plus a true >max overflow.

    The finite buckets are cumulative counts (a 120 ms sample increments
    250/500/.../10000); the overflow bucket is only the samples above the
    largest finite bound. Counting a normal sample in both the last finite
    bucket and overflow double-counted the total and made every p95 look
    like 10000 ms.
    """
    histogram = _empty_histogram()
    for bound in LATENCY_BUCKETS_MS:
        if latency_ms <= bound:
            histogram[str(bound)] = 1
    if latency_ms > LATENCY_BUCKETS_MS[-1]:
        histogram[OVERFLOW_KEY] = 1
    return histogram


def _floor_bucket(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    epoch = int(moment.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % BUCKET_WIDTH_SECONDS), UTC)


def merge_histograms(payloads: list[dict[str, int] | None]) -> dict[str, int]:
    merged = _empty_histogram()
    for payload in payloads:
        if not payload:
            continue
        for key, value in payload.items():
            merged[str(key)] = merged.get(str(key), 0) + int(value)
    return merged


def histogram_percentile(histogram: dict[str, int], fraction: float) -> float | None:
    """Bucket upper bound at ``fraction`` (histogram resolution, not exact)."""
    if not histogram:
        return None
    finite = sorted(float(bound) for bound in histogram if bound != OVERFLOW_KEY)
    overflow = int(histogram.get(OVERFLOW_KEY, 0))
    total = (int(histogram.get(str(int(finite[-1])), 0)) if finite else 0) + overflow
    if total <= 0:
        return None
    target = total * fraction
    for bound in finite:
        if int(histogram.get(str(int(bound)), 0)) >= target:
            return bound
    return finite[-1] if finite else None


class QueryRollupRecorder:
    """Bounded buffer + daemon flusher; safe to call from request threads."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
        max_pending: int = MAX_PENDING,
    ) -> None:
        self._session_factory = session_factory
        self._flush_interval = max(flush_interval, 0.5)
        self._pending: deque[QuerySample] = deque(maxlen=max(1, max_pending))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.dropped = 0

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def record(
        self,
        *,
        latency_ms: int,
        candidates: int,
        zero_results: bool,
        kind: str = V1_KIND,
        space_id: str = V1_SPACE_ID,
        view: str | None = None,
        degraded_reason: str | None = None,
    ) -> None:
        reason = degraded_reason if degraded_reason in _VALID_REASONS else None
        sample = QuerySample(
            latency_ms=max(int(latency_ms), 1),
            candidates=max(int(candidates), 0),
            zero_results=bool(zero_results),
            kind=kind or V1_KIND,
            space_id=space_id or V1_SPACE_ID,
            view=view or None,
            degraded_reason=reason,
            at=datetime.now(UTC),
        )
        with self._lock:
            if len(self._pending) == self._pending.maxlen:
                self.dropped += 1
            self._pending.append(sample)

    def _drain(self) -> list[QuerySample]:
        with self._lock:
            samples = list(self._pending)
            self._pending.clear()
        return samples

    def flush(self, session: Session) -> int:
        samples = self._drain()
        if not samples:
            return 0
        buckets: dict[tuple[str, str, str | None, str | None, datetime, int], _Bucket] = {}
        for sample in samples:
            width = BUCKET_WIDTH_SECONDS
            start = _floor_bucket(sample.at or datetime.now(UTC))
            key = (
                sample.space_id,
                sample.kind,
                sample.view,
                sample.degraded_reason,
                start,
                width,
            )
            bucket = buckets.setdefault(key, _Bucket())
            bucket.count += 1
            bucket.zero_results += int(sample.zero_results)
            bucket.candidates_sum += sample.candidates
            bucket.histogram = _merged_histogram(
                bucket.histogram, _histogram_for(sample.latency_ms)
            )
        for (space_id, kind, view, reason, start, width), bucket in buckets.items():
            statement = select(RetrievalQueryRollup).where(
                RetrievalQueryRollup.space_id == space_id,
                RetrievalQueryRollup.kind == kind,
                RetrievalQueryRollup.bucket_start == start,
                RetrievalQueryRollup.bucket_width == width,
            )
            statement = (
                statement.where(RetrievalQueryRollup.view.is_(None))
                if view is None
                else statement.where(RetrievalQueryRollup.view == view)
            )
            statement = (
                statement.where(RetrievalQueryRollup.degraded_reason.is_(None))
                if reason is None
                else statement.where(RetrievalQueryRollup.degraded_reason == reason)
            )
            row = session.scalars(statement.limit(1)).first()
            if row is None:
                row = RetrievalQueryRollup(
                    space_id=space_id,
                    kind=kind,
                    view=view,
                    degraded_reason=reason,
                    bucket_start=start,
                    bucket_width=width,
                    count=bucket.count,
                    zero_results=bucket.zero_results,
                    candidates_sum=bucket.candidates_sum,
                    latency_histogram=bucket.histogram,
                )
                session.add(row)
            else:
                row.count = int(row.count) + bucket.count
                row.zero_results = int(row.zero_results) + bucket.zero_results
                row.candidates_sum = int(row.candidates_sum) + bucket.candidates_sum
                row.latency_histogram = _merged_histogram(
                    row.latency_histogram, bucket.histogram or {}
                )
                row.updated_at = datetime.now(UTC)
        prune_rollups(session)
        session.commit()
        return len(samples)

    def flush_now(self) -> int:
        with self._session_factory() as session:
            return self.flush(session)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="retrieval-telemetry", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        try:
            self.flush_now()
        except Exception as error:  # pragma: no cover - shutdown best effort
            logger.warning("retrieval_telemetry_final_flush_failed", error=str(error)[:300])

    def _run(self) -> None:
        while not self._stop.wait(self._flush_interval):
            try:
                self.flush_now()
            except Exception as error:
                logger.warning("retrieval_telemetry_flush_failed", error=str(error)[:300])


def prune_rollups(session: Session, *, now: datetime | None = None) -> int:
    """Drop rollups past the 30-day operational TTL (not an audit ledger)."""
    moment = now or datetime.now(UTC)
    cutoff = moment - timedelta(days=ROLLUP_TTL_DAYS)
    rows = session.scalars(
        select(RetrievalQueryRollup).where(RetrievalQueryRollup.bucket_start < cutoff)
    ).all()
    for row in rows:
        session.delete(row)
    return len(rows)


_recorder: QueryRollupRecorder | None = None


def configure_recorder(recorder: QueryRollupRecorder | None) -> None:
    global _recorder
    _recorder = recorder


def record_query(
    *,
    latency_ms: int,
    candidates: int,
    zero_results: bool,
    kind: str = V1_KIND,
    space_id: str | None = None,
    view: str | None = None,
    degraded_reason: str | None = None,
) -> None:
    """Never raises and never blocks the request on the database."""
    recorder = _recorder
    if recorder is None:
        return
    with contextlib.suppress(Exception):
        recorder.record(
            latency_ms=latency_ms,
            candidates=candidates,
            zero_results=zero_results,
            kind=kind,
            space_id=space_id or V1_SPACE_ID,
            view=view,
            degraded_reason=degraded_reason,
        )


def degraded_reason_for_warning(warning: str | None) -> str | None:
    """Map the search layer's existing warning text to a contract reason."""
    if not warning:
        return None
    if "no embeddings model" in warning or "not assigned" in warning:
        return DegradedReason.PROVIDER_UNASSIGNED.value
    if "failed" in warning:
        return DegradedReason.EMBED_FAILED.value
    return None


def aggregate_rows(rows: Sequence[RetrievalQueryRollup]) -> dict[str, Any]:
    total = sum(int(row.count) for row in rows)
    zero = sum(int(row.zero_results) for row in rows)
    degraded = sum(int(row.count) for row in rows if row.degraded_reason is not None)
    reasons: dict[str, int] = {}
    views: dict[str, int] = {}
    for row in rows:
        if row.degraded_reason is not None:
            reasons[row.degraded_reason] = reasons.get(row.degraded_reason, 0) + int(row.count)
        if row.view is not None:
            views[row.view] = views.get(row.view, 0) + int(row.count)
    histogram = merge_histograms([row.latency_histogram for row in rows])
    candidates = sum(int(row.candidates_sum) for row in rows)
    return {
        "query_count": total,
        "zero_result_rate": zero / total if total else None,
        "degraded_rate": degraded / total if total else None,
        "degraded_reasons": reasons,
        "per_view_hits": views,
        "p50_ms": histogram_percentile(histogram, 0.50),
        "p95_ms": histogram_percentile(histogram, 0.95),
        "candidates_avg": candidates / total if total else None,
        "histogram": histogram,
    }


__all__ = [
    "BUCKET_WIDTH_SECONDS",
    "QueryRollupRecorder",
    "QuerySample",
    "aggregate_rows",
    "configure_recorder",
    "histogram_percentile",
    "merge_histograms",
    "prune_rollups",
    "record_query",
]
