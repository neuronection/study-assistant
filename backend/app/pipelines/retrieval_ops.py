"""VECTOR_* handlers over the active or a building vector space.

Plan 51 Q3a introduced the bounded reconcile/re-embed and maintenance pass;
Q3c2b1 makes them space-aware and replaces the honest cutover refusal with a
real handler: backfill the candidate through the same writer, enforce the
coverage gate, flip the active pointer and retire the previous space.

Every handler writes the contract's
``scanned/embedded/skipped/failed/failed_ids/truncated/gate`` result to
``jobs.result`` and reports through the runner's cancel checkpoint. A coverage
snapshot is written only when the pass actually covered the full corpus — a
partial or cancelled run never publishes a misleading coverage point.
Activation in this slice is coverage-gated only; quality is reported as
``not_sampled`` until Q3c2b2.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..core.vocab import JobType
from ..domain.models import Chunk, Job, VectorSpace
from ..jobs.payloads import JobResult
from ..jobs.runner import JobError
from ..services.retrieval import lifecycle
from ..services.retrieval.audit import build_vector_event
from ..services.retrieval.legacy import load_store, write_coverage_snapshot
from ..services.retrieval.telemetry import degraded_reason_for_warning
from ..storage.retrieval_ops import (
    COVERAGE_GATE,
    FAILED_IDS_LIMIT,
    CoverageDTO,
    GateStatus,
    RunResultDTO,
    truncate_failed_ids,
)
from ..storage.vector_contract import content_hash
from ..storage.vector_store import CONTENT_SPACE_ID, StudyVectorStore

logger = structlog.get_logger(__name__)

EmbedFn = Callable[[list[str]], tuple[str, list[list[float]]] | None]
Progress = Callable[[int, str], None]

DEFAULT_LIMIT = 500
MAX_LIMIT = 5_000
DEFAULT_BATCH_SIZE = 32
MAX_BATCH_SIZE = 256
MAINTENANCE_ACTIONS = ("orphan-sweep", "vacuum", "index-rebuild", "retry-failed")


def _payload(job: Job) -> dict[str, Any]:
    return cast(dict[str, Any], job.payload or {})


def _bounded_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _gate_for(coverage: CoverageDTO) -> GateStatus:
    if coverage.coverage is None:
        return GateStatus.UNKNOWN
    return GateStatus.PASS if coverage.coverage >= COVERAGE_GATE else GateStatus.FAIL


def _space_ref(session: Session, payload: dict[str, Any]) -> str | None:
    raw = payload.get("space_id")
    if raw in (None, ""):
        space = StudyVectorStore(session).content_space()
        return space.space_id if space is not None else CONTENT_SPACE_ID
    return str(raw)


def _finish(
    session: Session,
    job: Job,
    *,
    scanned: int,
    embedded: int,
    skipped: int,
    failed: int,
    failed_ids: list[str],
    gate: GateStatus,
    space_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> RunResultDTO:
    ids, truncated = truncate_failed_ids(failed_ids, FAILED_IDS_LIMIT)
    result = RunResultDTO(
        scanned=scanned,
        embedded=embedded,
        skipped=skipped,
        failed=failed,
        failed_ids=ids,
        failed_ids_truncated=truncated,
        gate=gate,
    )
    payload = result.to_dict()
    if extra:
        payload.update(extra)
    job.result = cast(JobResult, payload)
    target = space_id
    if gate == GateStatus.FAIL:
        session.add(
            build_vector_event(
                actor="system",
                action="vector.gate.failed",
                outcome="fail",
                resource=f"space:{target}"[:500] if target else "space:unknown",
            )
        )
    session.commit()
    return result


def _reindex(
    session: Session,
    job: Job,
    report: Progress,
    embed: EmbedFn,
    payload: dict[str, Any],
) -> RunResultDTO:
    force = bool(payload.get("force"))
    limit = _bounded_int(payload.get("limit"), DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT)
    batch_size = _bounded_int(
        payload.get("batch_size"),
        DEFAULT_BATCH_SIZE,
        minimum=1,
        maximum=MAX_BATCH_SIZE,
    )
    only = payload.get("chunk_ids")
    only_ids = {str(item) for item in only} if isinstance(only, list) else None
    target = _space_ref(session, payload)
    if target is None:
        _finish(
            session,
            job,
            scanned=0,
            embedded=0,
            skipped=0,
            failed=0,
            failed_ids=[],
            gate=GateStatus.UNKNOWN,
        )
        raise JobError("no active vector space to reindex")

    statement = select(Chunk).order_by(Chunk.id)
    count_statement = select(func.count()).select_from(Chunk)
    if only_ids is not None:
        if not only_ids:
            _finish(
                session,
                job,
                scanned=0,
                embedded=0,
                skipped=0,
                failed=0,
                failed_ids=[],
                gate=GateStatus.UNKNOWN,
                space_id=target,
            )
            return RunResultDTO()
        statement = statement.where(Chunk.id.in_(only_ids))
        count_statement = count_statement.where(Chunk.id.in_(only_ids))
    total = int(session.execute(count_statement).scalar() or 0)
    chunks = session.scalars(statement.limit(limit)).all()
    limited = len(chunks) < total
    store = StudyVectorStore(session, space_id=target)
    stored_hashes = store.stored_chunk_hashes()
    stored_ids = set(store.stored_chunk_ids().values())

    scanned = 0
    embedded = 0
    skipped = 0
    failed = 0
    failed_ids: list[str] = []
    pending: list[Chunk] = []
    report(1, "scanning chunks")

    def flush_pending() -> None:
        nonlocal embedded, failed, failed_ids
        if not pending:
            return
        texts = [chunk.text for chunk in pending]
        ids = [chunk.id for chunk in pending]
        pending.clear()
        try:
            result = embed(texts)
        except Exception as error:
            logger.warning(
                "vector_reindex_embed_failed",
                job_id=job.id,
                count=len(ids),
                error=str(error)[:300],
            )
            failed += len(ids)
            failed_ids.extend(ids)
            return
        if result is None:
            failed += len(ids)
            failed_ids.extend(ids)
            return
        model, batch = result
        if len(batch) != len(ids):
            failed += len(ids)
            failed_ids.extend(ids)
            return
        store.store(ids, batch, model)
        session.commit()
        embedded += len(ids)

    for chunk in chunks:
        report(
            max(1, min(99, int(scanned * 100 / max(total, 1)))),
            f"reindex {scanned}/{len(chunks)}",
        )
        scanned += 1
        if not force:
            current = stored_hashes.get(str(chunk.id))
            if current is not None and current == content_hash(chunk.text):
                skipped += 1
                continue
            if current is None and target == CONTENT_SPACE_ID and chunk.id in stored_ids:
                skipped += 1
                continue
        pending.append(chunk)
        if len(pending) >= batch_size:
            flush_pending()
    flush_pending()

    gate = GateStatus.UNKNOWN
    if not limited and only_ids is None:
        space = store.content_space()
        store_chunks = load_store(session, space_id=target)
        embedded_total = max(total - failed, 0)
        coverage = write_coverage_snapshot(
            session,
            total=total,
            embedded=embedded_total,
            missing=failed,
            failed=failed,
            stale=0,
            space_id=target,
        )
        gate = _gate_for(
            CoverageDTO(
                space_id=coverage.space_id,
                as_of=None,
                total=coverage.total,
                missing=coverage.missing,
                stale=coverage.stale,
                failed=coverage.failed,
                embedded=coverage.embedded,
                coverage=(
                    coverage.embedded / coverage.total if coverage.total > 0 else None
                ),
            )
        )
        if (
            store_chunks is not None
            and space is not None
            and store_chunks.chunk_total != coverage.total
        ):
            logger.warning(
                "vector_reindex_coverage_mismatch",
                job_id=job.id,
                space_id=target,
                store_chunks=store_chunks.chunk_total,
                snapshot_total=coverage.total,
            )
    _finish(
        session,
        job,
        scanned=scanned,
        embedded=embedded,
        skipped=skipped,
        failed=failed,
        failed_ids=failed_ids,
        gate=gate,
        space_id=target,
    )
    report(100, "reindex complete")
    return RunResultDTO(
        scanned=scanned,
        embedded=embedded,
        skipped=skipped,
        failed=failed,
        failed_ids=tuple(failed_ids[:FAILED_IDS_LIMIT]),
        failed_ids_truncated=len(failed_ids) > FAILED_IDS_LIMIT,
        gate=gate,
    )


def make_vector_reindex_handler(embed: EmbedFn) -> Callable[[Session, Job, Progress], None]:
    def handler(session: Session, job: Job, report: Progress) -> None:
        _reindex(session, job, report, embed, _payload(job))

    return handler


def _engine(session: Session) -> Engine:
    bind = session.get_bind()
    return bind if isinstance(bind, Engine) else bind.engine


def _vacuum(session: Session, table: str) -> None:
    statement = "VACUUM" if session.get_bind().dialect.name != "postgresql" else f"VACUUM {table}"
    with _engine(session).connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text(statement))


def _rebuild_index(session: Session, space_id: str | None) -> str:
    if session.get_bind().dialect.name != "postgresql":
        return "sqlite-vec has no online index rebuild; run a full VECTOR_REINDEX instead"
    store = StudyVectorStore(session, space_id=space_id)
    index_name = store.index_name
    if index_name is None:
        return (
            f"{store.index_table} has no provisioned HNSW index; run a full "
            "VECTOR_REINDEX to move the space onto its vec_ table"
        )
    exists = session.execute(text("SELECT to_regclass(:name)"), {"name": index_name}).scalar()
    if exists is None:
        raise JobError(f"{store.index_table} has no HNSW index to rebuild")
    with _engine(session).connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text(f"REINDEX INDEX CONCURRENTLY {index_name}"))
    return f"rebuilt {index_name} concurrently"


def make_vector_maintenance_handler(
    embed: EmbedFn,
) -> Callable[[Session, Job, Progress], None]:
    def handler(session: Session, job: Job, report: Progress) -> None:
        payload = _payload(job)
        action = str(payload.get("action") or "")
        dry_run = bool(payload.get("dry_run"))
        target = _space_ref(session, payload)
        if action not in MAINTENANCE_ACTIONS:
            raise JobError(
                f"unknown maintenance action {action!r}; expected one of {MAINTENANCE_ACTIONS}"
            )
        if dry_run and action != "orphan-sweep":
            raise JobError("dry-run is only supported for orphan-sweep")
        report(1, action)
        if action == "retry-failed":
            ids = payload.get("chunk_ids")
            if not isinstance(ids, list) or not ids:
                raise JobError("retry-failed needs a non-empty chunk_ids list")
            _reindex(session, job, report, embed, payload)
            return

        if action == "vacuum":
            table = StudyVectorStore(session, space_id=target).index_table
            _vacuum(session, table)
            job.result = cast(
                JobResult,
                {
                    "scanned": 0,
                    "embedded": 0,
                    "skipped": 1,
                    "failed": 0,
                    "failed_ids": [],
                    "failed_ids_truncated": False,
                    "gate": GateStatus.UNKNOWN.value,
                    "action": action,
                    "note": f"vacuumed {table}",
                    "space_id": target,
                },
            )
            session.commit()
            report(100, "vacuum complete")
            return

        if action == "index-rebuild":
            note = _rebuild_index(session, target)
            job.result = cast(
                JobResult,
                {
                    "scanned": 0,
                    "embedded": 0,
                    "skipped": 1,
                    "failed": 0,
                    "failed_ids": [],
                    "failed_ids_truncated": False,
                    "gate": GateStatus.UNKNOWN.value,
                    "action": action,
                    "note": note,
                    "space_id": target,
                },
            )
            session.commit()
            report(100, "index rebuild complete")
            return

        live_ids = {str(chunk_id) for chunk_id in session.scalars(select(Chunk.id)).all()}
        store = StudyVectorStore(session, space_id=target)
        dangling, orphan = store.orphan_rowids(live_ids)
        if dry_run:
            job.result = cast(
                JobResult,
                {
                    "scanned": len(live_ids) + len(dangling) + len(orphan),
                    "embedded": 0,
                    "skipped": len(live_ids),
                    "failed": 0,
                    "failed_ids": [],
                    "failed_ids_truncated": False,
                    "gate": GateStatus.UNKNOWN.value,
                    "action": action,
                    "dry_run": True,
                    "removed": 0,
                    "would_remove": len(dangling) + len(orphan),
                    "space_id": target,
                },
            )
            session.commit()
            report(100, "orphan sweep dry-run complete")
            return
        removed = store.delete_rowids([*dangling, *orphan])
        session.commit()
        job.result = cast(
            JobResult,
            {
                "scanned": len(live_ids) + len(dangling) + len(orphan),
                "embedded": 0,
                "skipped": len(live_ids),
                "failed": 0,
                "failed_ids": [],
                "failed_ids_truncated": False,
                "gate": GateStatus.UNKNOWN.value,
                "action": action,
                "removed": removed,
                "space_id": target,
            },
        )
        session.commit()
        report(100, "orphan sweep complete")

    return handler


def make_vector_cutover_handler(
    embed: EmbedFn,
) -> Callable[[Session, Job, Progress], None]:
    """Backfill a candidate space, enforce coverage and flip the active pointer."""

    def handler(session: Session, job: Job, report: Progress) -> None:
        payload = _payload(job)
        target = _space_ref(session, payload)
        if target is None:
            raise JobError("cutover needs a candidate space_id")
        row = session.get(VectorSpace, target)
        if row is None:
            raise JobError(f"no vector space {target!r}")
        if row.status == "active":
            job.result = cast(
                JobResult,
                {
                    "scanned": 0,
                    "embedded": 0,
                    "skipped": 1,
                    "failed": 0,
                    "failed_ids": [],
                    "failed_ids_truncated": False,
                    "gate": GateStatus.PASS.value,
                    "action": "cutover",
                    "space_id": target,
                    "already_active": True,
                    "quality": "not_sampled",
                    "message": "space is already active; nothing to cut over",
                    "space": lifecycle.ActivationResult(
                        space_id=str(row.id),
                        name=str(row.name),
                        space_key=lifecycle._space_key(row),
                        already_active=True,
                    ).as_dict(),
                },
            )
            session.commit()
            report(100, "space already active")
            return
        if row.status != "building":
            raise JobError(
                f"space {row.name!r} is {row.status}; only a building space can be cut over"
            )
        report(5, "backfilling candidate space")
        result = _reindex(session, job, report, embed, payload)
        if result.gate is not GateStatus.PASS:
            raise JobError(
                f"cutover refused: space {row.name!r} is not fully covered "
                f"(gate={result.gate.value}); backfill it before cutover"
            )
        report(90, "coverage gate passed; activating")
        try:
            activated = lifecycle.activate_space(session, target)
        except lifecycle.SpaceLifecycleError as error:
            raise JobError(f"cutover refused: {error}") from error
        session.commit()
        job.result = cast(
            JobResult,
            {
                "scanned": result.scanned,
                "embedded": result.embedded,
                "skipped": result.skipped,
                "failed": result.failed,
                "failed_ids": list(result.failed_ids),
                "failed_ids_truncated": result.failed_ids_truncated,
                "gate": GateStatus.PASS.value,
                "action": "cutover",
                "space_id": target,
                "space": activated.as_dict(),
                "quality": "not_sampled",
                "legacy_compat_retained": activated.legacy_compat_retained,
            },
        )
        session.commit()
        report(100, "cutover complete")

    return handler


VECTOR_HANDLERS = (
    JobType.VECTOR_REINDEX,
    JobType.VECTOR_MAINTENANCE,
    JobType.VECTOR_CUTOVER,
)


__all__ = [
    "VECTOR_HANDLERS",
    "degraded_reason_for_warning",
    "make_vector_cutover_handler",
    "make_vector_maintenance_handler",
    "make_vector_reindex_handler",
]
