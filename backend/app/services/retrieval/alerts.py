"""Bounded retrieval-operations alerts (plan 51 Q3c3a).

One evaluator pass reads only the Q3a/Q3b/Q3c read model: the latest coverage
snapshot per live space, the recent ``VECTOR_*`` runs, the persisted quality
compare, the 15-minute query rollups, the embeddings assignment, the physical
pgvector state and — when a token-denominated budget exists — its usage. It
never scans the corpus or the full history, and every emission goes through
:class:`app.services.platform.notifications.NotificationService`; there is no
second delivery path.

Dedup and recovery are one operation: a kind's active keys are the keys whose
condition currently holds; any older notification carrying that kind but no
longer active (or past its TTL) has its ``dedup_key`` released, so a later
recurrence is a new alert. The event history is kept.

Study has **no token-denominated embed budget** yet (its only budget is the
monetary `TaskAssignment.params.monthly_cap_usd`). ``retrieval.budget_exhausted``
therefore reports ``unavailable`` rather than inventing a token budget; the
kind is still boot-seeded so adoption only needs the real budget later.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ...core.vocab import JobStatus, NotificationKind
from ...domain.models import (
    Job,
    Notification,
    RetrievalCoverageSnapshot,
    RetrievalQueryRollup,
    VectorSpace,
)
from ...storage.retrieval_ops import (
    COVERAGE_GATE,
    DEGRADED_RATE_THRESHOLD,
    DEGRADED_RATE_WINDOW_MINUTES,
    HEARTBEAT_STALE_SECONDS,
    QUERY_SLO_P95_MS,
    QUERY_SLO_WINDOW_MINUTES,
    SPACE_DROP_GRACE_DAYS,
    STALL_MINUTES,
    VECTOR_JOB_TYPES,
    assert_no_raw_text,
)
from ...storage.vector_store import embedding_assignment
from ..platform.notifications import (
    KIND_DEFAULTS,
    KIND_TITLES,
    NotificationService,
    admin_recipients,
    manage_url,
)
from . import jobs as retrieval_jobs
from . import lifecycle, reads
from .legacy import LEGACY_KIND, LEGACY_SPACE_ID, iso
from .telemetry import aggregate_rows

logger = logging.getLogger(__name__)

ALERT_KINDS: tuple[str, ...] = tuple(default.kind for default in KIND_DEFAULTS.values())
RUN_WINDOW_DAYS = 30
RUN_SCAN_LIMIT = 200
DEDUP_ROW_LIMIT = 500
TERMINAL_STATUSES = (
    JobStatus.DONE.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
)
RUN_BASED_KINDS = {
    NotificationKind.RETRIEVAL_REINDEX_FAILED.value,
    NotificationKind.RETRIEVAL_REINDEX_STALLED.value,
}
TOKEN_BUDGET_AVAILABLE = False


@dataclass(frozen=True)
class AlertCandidate:
    """One condition that currently holds and should be in the inbox."""

    kind: str
    dedup_key: str
    title: str
    body: str
    payload: dict[str, Any]
    source_ref: dict[str, Any] | None = None


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _dedup(kind: str, *parts: Any) -> str:
    return ":".join([kind, *(str(part) for part in parts)])


def _is_postgres(session: Session) -> bool:
    return str(session.get_bind().dialect.name) == "postgresql"


def pg_index_state(session: Session, index_table: str) -> tuple[bool, bool]:
    """``(extension_present, table_present)`` for one pgvector index table."""
    extension = session.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    present = session.scalar(text("SELECT to_regclass(:table) IS NOT NULL"), {"table": index_table})
    return bool(extension), bool(present)


def _run_result_counts(job: Job) -> dict[str, int]:
    result = job.result if isinstance(job.result, Mapping) else {}
    counts: dict[str, int] = {}
    for key in ("scanned", "embedded", "skipped", "failed"):
        value = result.get(key)
        if isinstance(value, int):
            counts[key] = max(value, 0)
    return counts


def _run_kind(job: Job) -> str:
    payload = job.payload if isinstance(job.payload, Mapping) else {}
    raw = payload.get("kind")
    return str(raw) if raw else str(job.type).lower()


def _run_space(job: Job) -> str:
    payload = job.payload if isinstance(job.payload, Mapping) else {}
    raw = payload.get("space_id")
    return str(raw) if raw else LEGACY_SPACE_ID


class RetrievalAlertService:
    """Evaluate the ten contract alerts once and reconcile their dedup keys."""

    def __init__(self, session: Session, *, now: datetime | None = None):
        self.session = session
        self.now = _as_utc(now) or _utcnow()
        self._spaces: list[VectorSpace] | None = None
        self._runs_truncated = False

    def evaluate(self, *, commit: bool = True) -> dict[str, Any]:
        recipients = admin_recipients(self.session)
        service = NotificationService(self.session)
        summary: dict[str, Any] = {}
        emitted_total = 0
        evaluators = (
            (NotificationKind.RETRIEVAL_COVERAGE_LOW.value, self._coverage_low),
            (NotificationKind.RETRIEVAL_REINDEX_FAILED.value, self._reindex_failed),
            (NotificationKind.RETRIEVAL_REINDEX_STALLED.value, self._reindex_stalled),
            (NotificationKind.RETRIEVAL_QUALITY_GATE.value, self._quality_gate),
            (NotificationKind.RETRIEVAL_QUERY_SLO.value, self._query_slo),
            (NotificationKind.RETRIEVAL_DEGRADED_RATE.value, self._degraded_rate),
            (NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value, self._provider_unassigned),
            (NotificationKind.RETRIEVAL_INDEX_MISSING.value, self._index_missing),
            (NotificationKind.RETRIEVAL_BUDGET_EXHAUSTED.value, self._budget_exhausted),
            (NotificationKind.RETRIEVAL_SPACE_DROP_PENDING.value, self._space_drop_pending),
        )
        for kind, evaluator in evaluators:
            if (
                kind == NotificationKind.RETRIEVAL_BUDGET_EXHAUSTED.value
                and not TOKEN_BUDGET_AVAILABLE
            ):
                summary[kind] = {
                    "state": "unavailable",
                    "active": 0,
                    "emitted": 0,
                    "released": 0,
                    "reason": "no_token_budget",
                }
                continue
            try:
                candidates = evaluator()
                result = self._sync(kind, candidates, recipients, service=service)
            except Exception:
                logger.warning("retrieval alert evaluator %s failed", kind, exc_info=True)
                summary[kind] = {"state": "error", "active": 0, "emitted": 0, "released": 0}
                continue
            emitted_total += result["emitted"]
            summary[kind] = {"state": "ok", **result}
        if commit:
            self.session.commit()
        return {
            "state": "ok",
            "checked_at": iso(self.now),
            "kinds": summary,
            "emitted": emitted_total,
            "recipients": len(recipients),
            "token_budget": TOKEN_BUDGET_AVAILABLE,
        }

    # ----------------------------------------------------------- helpers

    def _all_spaces(self) -> list[VectorSpace]:
        if self._spaces is None:
            self._spaces = list(
                self.session.scalars(
                    select(VectorSpace).order_by(VectorSpace.created_at, VectorSpace.id)
                )
            )
        return self._spaces

    def _live_spaces(self) -> list[VectorSpace]:
        return [space for space in self._all_spaces() if space.status != "retired"]

    def _latest_snapshot(self, space_id: str) -> RetrievalCoverageSnapshot | None:
        return lifecycle.latest_coverage(self.session, space_id)

    def _runs_in_window(self) -> list[Job]:
        start = self.now - timedelta(days=RUN_WINDOW_DAYS)
        rows = list(
            self.session.scalars(
                select(Job)
                .where(Job.type.in_(VECTOR_JOB_TYPES), Job.created_at >= start)
                .order_by(Job.created_at.desc(), Job.id.desc())
                .limit(RUN_SCAN_LIMIT)
            )
        )
        self._runs_truncated = len(rows) >= RUN_SCAN_LIMIT
        return rows

    def _window_rollups(self) -> list[tuple[VectorSpace, dict[str, Any]]]:
        start = self.now - timedelta(minutes=QUERY_SLO_WINDOW_MINUTES)
        result: list[tuple[VectorSpace, dict[str, Any]]] = []
        for space in self._live_spaces():
            rows = list(
                self.session.scalars(
                    select(RetrievalQueryRollup)
                    .where(
                        RetrievalQueryRollup.space_id == str(space.id),
                        RetrievalQueryRollup.kind.in_((LEGACY_KIND, "material", "chunk")),
                        RetrievalQueryRollup.bucket_start >= start,
                        RetrievalQueryRollup.bucket_start < self.now,
                    )
                    .order_by(RetrievalQueryRollup.bucket_start)
                )
            )
            result.append((space, aggregate_rows(rows)))
        return result

    def _sync(
        self,
        kind: str,
        candidates: Sequence[AlertCandidate],
        recipients: Sequence[str],
        *,
        service: NotificationService,
    ) -> dict[str, int]:
        default = KIND_DEFAULTS[kind]
        active = {candidate.dedup_key for candidate in candidates}
        released = 0
        rows = self.session.scalars(
            select(Notification)
            .where(Notification.kind == kind, Notification.dedup_key.is_not(None))
            .order_by(Notification.created_at.desc())
            .limit(DEDUP_ROW_LIMIT)
        ).all()
        allow_release = not (self._runs_truncated and kind in RUN_BASED_KINDS)
        for row in rows:
            expires = _as_utc(row.dedup_expires_at)
            expired = expires is not None and expires <= self.now
            if row.dedup_key in active and not expired:
                continue
            if row.dedup_key not in active and not allow_release:
                continue
            row.dedup_key = None
            row.dedup_expires_at = None
            released += 1
        if released:
            self.session.flush()

        emitted = 0
        for candidate in candidates:
            event = service.emit(
                kind,
                list(recipients),
                title=candidate.title,
                body=candidate.body,
                payload=assert_no_raw_text(dict(candidate.payload)),
                source_ref=candidate.source_ref,
                dedup_key=candidate.dedup_key,
                max_per_day=default.daily_cap,
                now=self.now,
            )
            if event is not None:
                emitted += 1
        return {"active": len(candidates), "emitted": emitted, "released": released}

    # --------------------------------------------------------- evaluators

    def _coverage_low(self) -> list[AlertCandidate]:
        candidates: list[AlertCandidate] = []
        for space in self._live_spaces():
            snapshot = self._latest_snapshot(str(space.id))
            if snapshot is None:
                continue
            total = int(snapshot.total or 0)
            coverage = int(snapshot.embedded or 0) / total if total > 0 else None
            if coverage is None or coverage >= COVERAGE_GATE:
                continue
            if retrieval_jobs.active_run_for_space(self.session, str(space.id)) is not None:
                continue
            link = manage_url(NotificationKind.RETRIEVAL_COVERAGE_LOW.value)
            candidates.append(
                AlertCandidate(
                    kind=NotificationKind.RETRIEVAL_COVERAGE_LOW.value,
                    dedup_key=_dedup(NotificationKind.RETRIEVAL_COVERAGE_LOW.value, space.id),
                    title=KIND_TITLES[NotificationKind.RETRIEVAL_COVERAGE_LOW.value],
                    body=(
                        f"{space.name} is at {coverage:.2%} coverage "
                        f"(gate {COVERAGE_GATE:.1%}) with no run building it."
                    ),
                    payload={
                        "link": link,
                        "space_id": str(space.id),
                        "space": str(space.name),
                        "coverage": round(coverage, 6),
                        "gate": COVERAGE_GATE,
                        "total": total,
                        "embedded": int(snapshot.embedded or 0),
                        "missing": int(snapshot.missing or 0),
                        "as_of": iso(snapshot.as_of),
                    },
                    source_ref={"kind": "retrieval_space", "space_id": str(space.id)},
                )
            )
        return candidates

    def _reindex_failed(self) -> list[AlertCandidate]:
        latest: dict[tuple[str, str], Job] = {}
        for job in self._runs_in_window():
            if job.status not in TERMINAL_STATUSES:
                continue
            latest.setdefault((_run_space(job), _run_kind(job)), job)
        candidates: list[AlertCandidate] = []
        for (space_id, alert_scope), job in latest.items():
            if job.status != JobStatus.FAILED.value:
                continue
            space_name = self._space_name(space_id)
            detail = manage_url(NotificationKind.RETRIEVAL_REINDEX_FAILED.value, run_id=str(job.id))
            candidates.append(
                AlertCandidate(
                    kind=NotificationKind.RETRIEVAL_REINDEX_FAILED.value,
                    dedup_key=_dedup(
                        NotificationKind.RETRIEVAL_REINDEX_FAILED.value, space_id, alert_scope
                    ),
                    title=KIND_TITLES[NotificationKind.RETRIEVAL_REINDEX_FAILED.value],
                    body=(f"A {job.type} run for {space_name} failed (run {job.id})."),
                    payload={
                        "link": detail,
                        "run_id": str(job.id),
                        "space_id": space_id,
                        "space": space_name,
                        "job_type": str(job.type),
                        "scope_kind": alert_scope,
                        "status": str(job.status),
                        **_run_result_counts(job),
                    },
                    source_ref={"kind": "retrieval_run", "run_id": str(job.id)},
                )
            )
        return candidates

    def _reindex_stalled(self) -> list[AlertCandidate]:
        cutoff = self.now - timedelta(seconds=HEARTBEAT_STALE_SECONDS)
        candidates: list[AlertCandidate] = []
        for job in self._runs_in_window():
            if job.status != JobStatus.RUNNING.value:
                continue
            beat = _as_utc(job.heartbeat_at) or _as_utc(job.started_at) or _as_utc(job.created_at)
            if beat is None or beat >= cutoff:
                continue
            space_id = _run_space(job)
            space_name = self._space_name(space_id)
            detail = manage_url(
                NotificationKind.RETRIEVAL_REINDEX_STALLED.value, run_id=str(job.id)
            )
            candidates.append(
                AlertCandidate(
                    kind=NotificationKind.RETRIEVAL_REINDEX_STALLED.value,
                    dedup_key=_dedup(NotificationKind.RETRIEVAL_REINDEX_STALLED.value, job.id),
                    title=KIND_TITLES[NotificationKind.RETRIEVAL_REINDEX_STALLED.value],
                    body=(
                        f"A {job.type} run for {space_name} has not reported progress for "
                        f"{STALL_MINUTES} minutes (run {job.id})."
                    ),
                    payload={
                        "link": detail,
                        "run_id": str(job.id),
                        "space_id": space_id,
                        "space": space_name,
                        "job_type": str(job.type),
                        "stage": job.stage,
                        "progress": int(job.progress or 0),
                        "heartbeat_at": iso(beat),
                        "stale_minutes": STALL_MINUTES,
                    },
                    source_ref={"kind": "retrieval_run", "run_id": str(job.id)},
                )
            )
        return candidates

    def _quality_gate(self) -> list[AlertCandidate]:
        evidence = reads._quality_evidence_index(self.session)
        candidates: list[AlertCandidate] = []
        for space in self._live_spaces():
            persisted = evidence.get(str(space.id))
            if persisted is None or persisted.compare.passed:
                continue
            compare = persisted.compare
            candidates.append(
                AlertCandidate(
                    kind=NotificationKind.RETRIEVAL_QUALITY_GATE.value,
                    dedup_key=_dedup(NotificationKind.RETRIEVAL_QUALITY_GATE.value, space.id),
                    title=KIND_TITLES[NotificationKind.RETRIEVAL_QUALITY_GATE.value],
                    body=(
                        f"The golden-query compare for {space.name} missed the floor "
                        f"(recall {compare.new_recall_at_k:.2f}, "
                        f"precision {compare.new_precision_at_k:.2f})."
                    ),
                    payload={
                        "link": manage_url(NotificationKind.RETRIEVAL_QUALITY_GATE.value),
                        "space_id": str(space.id),
                        "space": str(space.name),
                        "run_id": str(persisted.job.id),
                        "set_version": compare.set_version,
                        "k": compare.k,
                        "recall_at_k": compare.new_recall_at_k,
                        "precision_at_k": compare.new_precision_at_k,
                        "floor_recall": compare.floor_recall,
                        "floor_precision": compare.floor_precision,
                    },
                    source_ref={
                        "kind": "retrieval_quality",
                        "run_id": str(persisted.job.id),
                    },
                )
            )
        return candidates

    def _query_slo(self) -> list[AlertCandidate]:
        candidates: list[AlertCandidate] = []
        for space, metrics in self._window_rollups():
            p95 = metrics["p95_ms"]
            if not metrics["query_count"] or p95 is None or p95 <= QUERY_SLO_P95_MS:
                continue
            candidates.append(
                AlertCandidate(
                    kind=NotificationKind.RETRIEVAL_QUERY_SLO.value,
                    dedup_key=_dedup(NotificationKind.RETRIEVAL_QUERY_SLO.value, space.id),
                    title=KIND_TITLES[NotificationKind.RETRIEVAL_QUERY_SLO.value],
                    body=(
                        f"Query p95 for {space.name} is {p95:.0f} ms over the last "
                        f"{QUERY_SLO_WINDOW_MINUTES} minutes "
                        f"(budget {QUERY_SLO_P95_MS} ms)."
                    ),
                    payload={
                        "link": manage_url(NotificationKind.RETRIEVAL_QUERY_SLO.value),
                        "space_id": str(space.id),
                        "space": str(space.name),
                        "p95_ms": p95,
                        "budget_ms": QUERY_SLO_P95_MS,
                        "window_minutes": QUERY_SLO_WINDOW_MINUTES,
                        "query_count": metrics["query_count"],
                    },
                    source_ref={"kind": "retrieval_space", "space_id": str(space.id)},
                )
            )
        return candidates

    def _degraded_rate(self) -> list[AlertCandidate]:
        candidates: list[AlertCandidate] = []
        for space, metrics in self._window_rollups():
            total = metrics["query_count"]
            if not total:
                continue
            for reason, count in metrics["degraded_reasons"].items():
                rate = count / total
                if rate <= DEGRADED_RATE_THRESHOLD:
                    continue
                candidates.append(
                    AlertCandidate(
                        kind=NotificationKind.RETRIEVAL_DEGRADED_RATE.value,
                        dedup_key=_dedup(
                            NotificationKind.RETRIEVAL_DEGRADED_RATE.value, space.id, reason
                        ),
                        title=KIND_TITLES[NotificationKind.RETRIEVAL_DEGRADED_RATE.value],
                        body=(
                            f"{reason} affected {rate:.1%} of queries for {space.name} "
                            f"over the last {DEGRADED_RATE_WINDOW_MINUTES} minutes "
                            f"(threshold {DEGRADED_RATE_THRESHOLD:.0%})."
                        ),
                        payload={
                            "link": manage_url(NotificationKind.RETRIEVAL_DEGRADED_RATE.value),
                            "space_id": str(space.id),
                            "space": str(space.name),
                            "reason": reason,
                            "rate": round(rate, 6),
                            "count": count,
                            "query_count": total,
                            "threshold": DEGRADED_RATE_THRESHOLD,
                            "window_minutes": DEGRADED_RATE_WINDOW_MINUTES,
                        },
                        source_ref={
                            "kind": "retrieval_space",
                            "space_id": str(space.id),
                        },
                    )
                )
        return candidates

    def _provider_unassigned(self) -> list[AlertCandidate]:
        assignment = embedding_assignment(self.session)
        if assignment.provider != "unassigned":
            return []
        kind = NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value
        return [
            AlertCandidate(
                kind=kind,
                dedup_key=_dedup(kind, "singleton"),
                title=KIND_TITLES[kind],
                body=(
                    "Semantic indexing cannot run until an embeddings model is assigned "
                    "in Settings → AI Configuration."
                ),
                payload={
                    "link": manage_url(kind),
                    "slot": "embeddings",
                    "task_type": "embeddings",
                    "assigned": False,
                },
                source_ref={"kind": "retrieval_provider", "slot": "embeddings"},
            )
        ]

    def _index_missing(self) -> list[AlertCandidate]:
        if not _is_postgres(self.session):
            return []
        states: dict[str, tuple[bool, bool]] = {}
        candidates: list[AlertCandidate] = []
        for space in self._live_spaces():
            if not space.index_table:
                continue
            state = states.get(str(space.index_table))
            if state is None:
                state = pg_index_state(self.session, str(space.index_table))
                states[str(space.index_table)] = state
            extension, table_present = state
            if extension and table_present:
                continue
            kind = NotificationKind.RETRIEVAL_INDEX_MISSING.value
            candidates.append(
                AlertCandidate(
                    kind=kind,
                    dedup_key=_dedup(kind, space.id),
                    title=KIND_TITLES[kind],
                    body=(
                        f"{space.name} declares index table {space.index_table}, but the "
                        "physical pgvector index is absent."
                    ),
                    payload={
                        "link": manage_url(kind),
                        "space_id": str(space.id),
                        "space": str(space.name),
                        "index_table": str(space.index_table),
                        "extension_present": extension,
                        "table_present": table_present,
                    },
                    source_ref={"kind": "retrieval_space", "space_id": str(space.id)},
                )
            )
        return candidates

    def _budget_exhausted(self) -> list[AlertCandidate]:
        """Honest no-op: study has no token-denominated embed budget yet."""
        return []

    def _space_drop_pending(self) -> list[AlertCandidate]:
        cutoff = self.now - timedelta(days=SPACE_DROP_GRACE_DAYS)
        candidates: list[AlertCandidate] = []
        for space in self._all_spaces():
            if space.status != "retired":
                continue
            retired = _as_utc(space.retired_at)
            if retired is None or retired > cutoff:
                continue
            days = max((self.now - retired).days, 0)
            kind = NotificationKind.RETRIEVAL_SPACE_DROP_PENDING.value
            candidates.append(
                AlertCandidate(
                    kind=kind,
                    dedup_key=_dedup(kind, space.id),
                    title=KIND_TITLES[kind],
                    body=(
                        f"{space.name} was retired {days} days ago and is past the "
                        f"{SPACE_DROP_GRACE_DAYS}-day drop grace."
                    ),
                    payload={
                        "link": manage_url(kind),
                        "space_id": str(space.id),
                        "space": str(space.name),
                        "retired_at": iso(retired),
                        "days_retired": days,
                        "grace_days": SPACE_DROP_GRACE_DAYS,
                    },
                    source_ref={"kind": "retrieval_space", "space_id": str(space.id)},
                )
            )
        return candidates

    def _space_name(self, space_id: str) -> str:
        for space in self._all_spaces():
            if str(space.id) == str(space_id):
                return str(space.name)
        return str(space_id)


def evaluate_retrieval_alerts(
    session: Session, *, now: datetime | None = None, commit: bool = True
) -> dict[str, Any]:
    """Convenience entry point for the scheduler seam and tests."""
    return RetrievalAlertService(session, now=now).evaluate(commit=commit)


__all__ = [
    "ALERT_KINDS",
    "RUN_SCAN_LIMIT",
    "TOKEN_BUDGET_AVAILABLE",
    "AlertCandidate",
    "RetrievalAlertService",
    "evaluate_retrieval_alerts",
    "pg_index_state",
]
