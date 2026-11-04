"""Composed retrieval-operations read model over the real spaces.

Plan 51 Q3a/Q3c2b1. Every reader composes what already exists — ``jobs`` (the
VECTOR_* run rows), the vector metadata/backends, the two bounded rollups — and
shapes the family contract DTOs. Nothing here carries raw query, prompt or
document text, and coverage is always the latest snapshot of the addressed
real space (``as_of=None`` means never reconciled, never a fake percentage).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.models import AiInteraction, Job, RetrievalQueryRollup, VectorSpace
from ...storage.retrieval_ops import (
    VECTOR_JOB_TYPES,
    GateStatus,
    GoldenQuerySet,
    QualityCompareDTO,
    QueryHealthDTO,
    RunDTO,
    RunResultDTO,
    RunScope,
    RunStatus,
    SpaceDTO,
)
from ...storage.vector_store import backend_label
from . import lifecycle, quality
from .legacy import (
    LEGACY_KIND,
    LEGACY_SPACE_ID,
    LegacyStore,
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
        view=str(payload["view"]) if payload.get("view") else None,
        since=str(payload["since"]) if payload.get("since") else None,
    )
    budget = payload.get("budget")
    return RunDTO(
        run_id=row.id,
        space_id=str(payload.get("space_id") or LEGACY_SPACE_ID),
        job_type=job_type,
        status=status,
        progress=max(0, min(int(row.progress or 0), 100)),
        stage=row.stage,
        scope=scope,
        budget_tokens=(int(str(budget)) if budget is not None else None),
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
    raw = row.result if isinstance(row.result, dict) else {}
    compare = quality.parse_persisted_compare(raw)
    activation_gate = (
        raw.get("activation_gate") if isinstance(raw.get("activation_gate"), dict) else None
    )
    duration: float | None = None
    if row.started_at is not None and row.finished_at is not None:
        duration = max((row.finished_at - row.started_at).total_seconds(), 0.0)
    return {
        "run": dto.to_dict() if dto is not None else None,
        "result": result.to_dict() if result is not None else None,
        "duration_seconds": duration,
        "quality": compare.to_dict() if compare is not None else None,
        "bad_matches": quality.parse_persisted_bad_matches(raw),
        "activation_gate": activation_gate,
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


def _last_reindex(session: Session, space_id: str) -> str | None:
    rows = session.scalars(
        select(Job)
        .where(Job.type == "VECTOR_REINDEX", Job.status == "done")
        .order_by(Job.finished_at.desc(), Job.created_at.desc())
        .limit(RUN_MAX)
    ).all()
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if str(payload.get("space_id") or LEGACY_SPACE_ID) == space_id:
            return iso(row.finished_at or row.created_at)
    return None


def _space(session: Session, store: LegacyStore) -> SpaceDTO:
    return replace(
        space_dto(session, store),
        last_reindex_at=_last_reindex(session, store.space_id),
    )


def _active_space_id(session: Session) -> str | None:
    return lifecycle.active_space_id(session)


def _quality_space(session: Session, ref: str | None) -> VectorSpace | None:
    if ref not in (None, ""):
        row = session.get(VectorSpace, str(ref))
        if row is not None:
            return row
        return session.scalars(
            select(VectorSpace)
            .where(VectorSpace.name == str(ref))
            .order_by(VectorSpace.created_at.desc(), VectorSpace.id)
        ).first()
    return lifecycle.active_space_row(session)


@dataclass(frozen=True)
class _QualityEvidence:
    job: Job
    compare: QualityCompareDTO
    bad_matches: list[dict[str, Any]]


def _quality_evidence_index(session: Session) -> dict[str, _QualityEvidence]:
    """Newest persisted compare per candidate space (ids/scores only)."""
    rows = session.scalars(
        select(Job)
        .where(Job.type == "VECTOR_CUTOVER", Job.status == "done")
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(RUN_MAX)
    ).all()
    index: dict[str, _QualityEvidence] = {}
    for job in rows:
        payload = job.payload if isinstance(job.payload, dict) else {}
        if payload.get("action") not in (
            "quality_compare",
            "activate_space",
            "cutover",
        ):
            continue
        compare = quality.parse_persisted_compare(job.result)
        if compare is None or compare.new_space_id in index:
            continue
        index[compare.new_space_id] = _QualityEvidence(
            job=job,
            compare=compare,
            bad_matches=quality.parse_persisted_bad_matches(job.result),
        )
    return index


def _quality_state(
    space: VectorSpace,
    golden: GoldenQuerySet | None,
    evidence: _QualityEvidence | None,
) -> tuple[str, str]:
    """``(state, gate)`` for one space without claiming an unmeasured pass."""
    if golden is None:
        return "no_golden_set", GateStatus.UNKNOWN.value
    if evidence is None:
        return "not_sampled", GateStatus.UNKNOWN.value
    compare = evidence.compare
    if compare.set_version != golden.set_version or compare.k != golden.k:
        return "stale_compare", GateStatus.UNKNOWN.value
    return "sampled", (GateStatus.PASS if compare.passed else GateStatus.FAIL).value


def quality_evidence(session: Session, *, space: str | None = None) -> dict[str, Any]:
    """The versioned golden set plus the newest compare for one space.

    ``no_golden_set`` and ``not_sampled`` are honest states: the card never
    shows a pass until a compare actually ran for the current set version.
    """
    row = _quality_space(session, space)
    if row is None:
        return {
            "state": "no_such_space" if space not in (None, "") else "no_space",
            "space_id": str(space or ""),
            "name": "",
            "sampled": False,
            "set": None,
            "quality": None,
            "compare": None,
            "bad_matches": [],
            "compare_run_id": None,
            "compare_set_version": None,
            "activation_gate": GateStatus.UNKNOWN.value,
            "reason": "no_space",
            "notes": ["No vector space to score; pass ?space=<id|name>."],
        }
    sets = quality.load_golden_sets()
    golden = quality.select_golden_set(row, sets)
    evidence = _quality_evidence_index(session).get(str(row.id))
    state, gate = _quality_state(row, golden, evidence)
    if golden is None:
        return {
            "state": state,
            "space_id": str(row.id),
            "name": str(row.name),
            "sampled": False,
            "set": None,
            "quality": None,
            "compare": None,
            "bad_matches": [],
            "compare_run_id": None,
            "compare_set_version": None,
            "activation_gate": gate,
            "reason": "no_golden_set",
            "notes": [
                "No versioned golden-query set is recorded for this space; "
                "activation refuses until an admin records one."
            ],
        }
    summary = quality.golden_set_summary(golden)
    if evidence is None:
        return {
            "state": state,
            "space_id": str(row.id),
            "name": str(row.name),
            "sampled": False,
            "set": summary,
            "quality": None,
            "compare": None,
            "bad_matches": [],
            "compare_run_id": None,
            "compare_set_version": None,
            "activation_gate": gate,
            "reason": "compare_not_run",
            "notes": ["The golden set exists; run a quality compare to measure it."],
        }
    compare = evidence.compare
    candidate = quality.quality_from_compare(compare)
    return {
        "state": state,
        "space_id": str(row.id),
        "name": str(row.name),
        "sampled": True,
        "set": summary,
        "quality": candidate.to_dict(),
        "compare": compare.to_dict(),
        "bad_matches": evidence.bad_matches,
        "compare_run_id": evidence.job.id,
        "compare_set_version": compare.set_version,
        "activation_gate": gate,
        "reason": None if state == "sampled" else "stale_compare",
        "notes": (
            ["The stored compare predates the current set version or k."]
            if state != "sampled"
            else []
        ),
    }


def query_health(session: Session, *, window: str | None = None) -> dict[str, Any]:
    start, end, key = _window(window)
    target = _active_space_id(session) or LEGACY_SPACE_ID
    rows = session.scalars(
        select(RetrievalQueryRollup)
        .where(
            RetrievalQueryRollup.space_id == target,
            RetrievalQueryRollup.kind.in_((LEGACY_KIND, "material", "chunk")),
            RetrievalQueryRollup.bucket_start >= start,
            RetrievalQueryRollup.bucket_start < end,
        )
        .order_by(RetrievalQueryRollup.bucket_start)
    ).all()
    metrics = aggregate_rows(list(rows))
    snapshot = latest_coverage(session, target)
    dto = QueryHealthDTO(
        space_id=target,
        window_start=iso(start) or "",
        window_end=iso(end) or "",
        p50_ms=metrics["p50_ms"],
        p95_ms=metrics["p95_ms"],
        candidate_p50=None,
        candidate_p95=None,
        zero_result_rate=metrics["zero_result_rate"],
        degraded_rate=metrics["degraded_rate"],
        degraded_reasons=metrics["degraded_reasons"],
        per_view_hits=metrics["per_view_hits"],
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


def usage(session: Session, *, window: str | None = None) -> dict[str, Any]:
    """Embedding calls/tokens by day, space and kind (no prompt/text selected).

    Study's ledger is ``ai_interactions``; it has no status/error column, so
    ``errors`` is honestly unavailable instead of fabricated. Token counts are
    the recorded estimate/sum and stay ``None`` when the ledger has none.
    """
    start, end, key = _window(window)
    rows = list(
        session.scalars(
            select(AiInteraction)
            .where(
                AiInteraction.task == "embeddings",
                AiInteraction.created_at >= start,
                AiInteraction.created_at < end,
            )
            .order_by(AiInteraction.created_at, AiInteraction.id)
            .limit(10_000)
        )
    )
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    tokens_seen = False
    for row in rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        space_id = str(metadata.get("space_id") or "unattributed")
        kind = str(metadata.get("kind") or "unknown")
        moment = row.created_at or start
        day = (moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment).date().isoformat()
        entry = buckets.setdefault(
            (day, space_id, kind),
            {
                "day": day,
                "space_id": space_id,
                "kind": kind,
                "calls": 0,
                "tokens_in": None,
                "tokens_out": None,
                "reindex_calls": 0,
            },
        )
        entry["calls"] += 1
        if kind not in ("query", "golden_query"):
            entry["reindex_calls"] += 1
        if row.input_tokens is not None:
            tokens_seen = True
            entry["tokens_in"] = int(entry["tokens_in"] or 0) + int(row.input_tokens)
        if row.output_tokens is not None:
            tokens_seen = True
            entry["tokens_out"] = int(entry["tokens_out"] or 0) + int(row.output_tokens)
    ordered = [buckets[item] for item in sorted(buckets)]
    notes: list[str] = []
    if not tokens_seen:
        notes.append(
            "No embedding token counts are recorded in this window — the gap is "
            "reported, not estimated here."
        )
    notes.append(
        "Error counts are unavailable: study's ai_interactions ledger has no "
        "status/error column; failed embed calls are visible in run results."
    )
    if any(entry["space_id"] == "unattributed" for entry in ordered):
        notes.append(
            "Rows without caller tags predate retrieval metadata (plan 51 Q3c3a) "
            "and are reported as unattributed, not guessed."
        )
    notes.append(
        "Study has no token-denominated embed budget; TaskAssignment.monthly_cap_usd "
        "is monetary and is not reported as a token budget."
    )
    return {
        "window": key,
        "window_start": iso(start),
        "window_end": iso(end),
        "rows": ordered,
        "tokens_available": tokens_seen,
        "errors_available": False,
        "budget": None,
        "notes": notes,
    }


def overview(session: Session, *, window: str | None = None) -> dict[str, Any]:
    store = load_store(session)
    target = store.space_id if store is not None else (_active_space_id(session) or LEGACY_SPACE_ID)
    coverage = coverage_dto(session, store, space_id=target)
    runs = list_runs(session, limit=5)
    health = query_health(session, window=window)
    spaces = list_spaces(session)
    notes: list[str] = [
        "Build/activate/retire/drop and cutover are available. Activation and "
        "cutover require physical health, coverage and the golden-query quality "
        "compare; a missing or below-floor set is a structured refusal."
    ]
    if store is not None:
        notes.append(f"Storage: {store.health_detail}.")
        if not store.health_ok:
            notes.append(
                "The provisioned vector backend reports a problem; search falls "
                "back to the legacy store or lexical matching."
            )
        if store.space_id != LEGACY_SPACE_ID and lifecycle.legacy_compat_present(session):
            notes.append(
                "The retired legacy chunk_vecs compatibility store is retained; "
                "drop the retired legacy space to remove it."
            )
    for building in lifecycle.building_spaces(session):
        notes.append(
            f"Building space {building.name!r} ({building.model}, dim {building.dim}); "
            "it is not searchable until it is activated."
        )
    if store is None and coverage.as_of is None:
        state = "empty"
        notes.append("The vector store has no active space yet (nothing embedded).")
    elif coverage.as_of is None:
        state = "cold"
        notes.append("Never reconciled — run a vector reindex to publish coverage.")
    elif (
        store is None
        or coverage.gate == GateStatus.FAIL
        or (coverage.failed or 0) > 0
        or not store.health_ok
    ):
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
        "spaces": spaces["spaces"],
    }


def list_spaces(session: Session) -> dict[str, Any]:
    active_id = _active_space_id(session)
    sets = quality.load_golden_sets()
    evidence = _quality_evidence_index(session)
    rows: list[dict[str, Any]] = []
    for row in session.scalars(
        select(VectorSpace).order_by(VectorSpace.created_at, VectorSpace.id)
    ):
        store = load_store(session, space_id=str(row.id))
        if store is None:
            continue
        entry = _space(session, store).to_dict()
        state, gate = _quality_state(
            row,
            quality.select_golden_set(row, sets),
            evidence.get(str(row.id)),
        )
        entry["quality_state"] = state
        entry["quality_gate"] = gate
        rows.append(entry)
    active = next((entry for entry in rows if entry["space_id"] == active_id), None)
    return {
        "spaces": rows,
        "cold": active is None or active.get("as_of") is None,
        "active_space_id": active_id,
        "notes": [] if rows else ["No vector space is provisioned; spaces is empty."],
    }


def spaces(session: Session) -> dict[str, Any]:
    return list_spaces(session)


def coverage(session: Session, *, space: str | None = None) -> dict[str, Any]:
    target = space
    if target in (None, ""):
        target = _active_space_id(session)
    if target in (None, ""):
        store = load_store(session)
        if store is not None:
            target = store.space_id
    if target in (None, ""):
        dto = coverage_dto(session, space_id=LEGACY_SPACE_ID)
        return {
            "space_id": dto.space_id,
            "cold": True,
            "coverage": dto.to_dict(),
            "notes": ["No vector space is provisioned."],
        }
    row = session.get(VectorSpace, str(target))
    if row is None:
        return {
            "space_id": str(target),
            "cold": True,
            "coverage": None,
            "notes": [f"No such space {target!r}."],
        }
    dto = coverage_dto(session, space_id=str(row.id))
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
    "list_spaces",
    "overview",
    "quality_evidence",
    "query_health",
    "spaces",
    "usage",
]
