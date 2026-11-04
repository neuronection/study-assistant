"""VECTOR_* foundation handlers over the legacy `chunk_vecs` store.

Plan 51 Q3a: a bounded reconcile/re-embed pass, a maintenance pass and an
honest refusal for the cutover that study cannot perform yet (there is no
space lifecycle). Every handler writes the contract's
``scanned/embedded/skipped/failed/failed_ids/truncated/gate`` result to
``jobs.result`` and reports through the runner's cancel checkpoint.

The scan is bounded by ``limit`` (default 500) and embeds in batches
(default 32); a run never loads the whole corpus into memory. A coverage
snapshot is written only when the pass actually covered the full corpus — a
partial or cancelled run never publishes a misleading coverage point.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..core.vocab import JobType
from ..domain.models import Chunk, Job
from ..jobs.payloads import JobResult
from ..jobs.runner import JobError
from ..services.retrieval.audit import build_vector_event, space_resource
from ..services.retrieval.legacy import (
    load_store,
    write_coverage_snapshot,
)
from ..services.retrieval.telemetry import degraded_reason_for_warning
from ..storage.retrieval_ops import (
    COVERAGE_GATE,
    FAILED_IDS_LIMIT,
    CoverageDTO,
    GateStatus,
    RunResultDTO,
    truncate_failed_ids,
)
from ..storage.vector_store import StudyVectorStore

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
    job.result = cast(JobResult, result.to_dict())
    if gate == GateStatus.FAIL:
        session.add(
            build_vector_event(
                actor="system",
                action="vector.gate.failed",
                outcome="fail",
                resource=space_resource(),
            )
        )
    session.commit()
    return result


def make_vector_reindex_handler(embed: EmbedFn) -> Callable[[Session, Job, Progress], None]:
    def handler(session: Session, job: Job, report: Progress) -> None:
        payload = _payload(job)
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
                )
                return
            statement = statement.where(Chunk.id.in_(only_ids))
            count_statement = count_statement.where(Chunk.id.in_(only_ids))
        total = int(session.execute(count_statement).scalar() or 0)
        chunks = session.scalars(statement.limit(limit)).all()
        limited = len(chunks) < total
        store = StudyVectorStore(session)
        stored = set(store.stored_chunk_ids().values())

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
            if not force and chunk.id in stored:
                skipped += 1
                continue
            pending.append(chunk)
            if len(pending) >= batch_size:
                flush_pending()
        flush_pending()

        gate = GateStatus.UNKNOWN
        if not limited and only_ids is None:
            legacy_store = load_store(session)
            embedded_total = max(total - failed, 0)
            coverage = write_coverage_snapshot(
                session,
                total=total,
                embedded=embedded_total,
                missing=failed,
                failed=failed,
                stale=0,
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
                        coverage.embedded / coverage.total
                        if coverage.total > 0
                        else None
                    ),
                )
            )
            if legacy_store is not None and legacy_store.chunk_total != coverage.total:
                logger.warning(
                    "vector_reindex_coverage_mismatch",
                    job_id=job.id,
                    store_chunks=legacy_store.chunk_total,
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
        )
        report(100, "reindex complete")

    return handler


def _engine(session: Session) -> Engine:
    bind = session.get_bind()
    return bind if isinstance(bind, Engine) else bind.engine


def _vacuum(session: Session, table: str) -> None:
    statement = "VACUUM" if session.get_bind().dialect.name != "postgresql" else f"VACUUM {table}"
    with _engine(session).connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text(statement))


def _rebuild_index(session: Session) -> str:
    if session.get_bind().dialect.name != "postgresql":
        return "sqlite-vec has no online index rebuild; run a full VECTOR_REINDEX instead"
    exists = session.execute(
        text("SELECT to_regclass(:name)"), {"name": "ix_chunk_vecs_embedding"}
    ).scalar()
    if exists is None:
        raise JobError("chunk_vecs has no HNSW index to rebuild")
    with _engine(session).connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text("REINDEX INDEX CONCURRENTLY ix_chunk_vecs_embedding"))
    return "rebuilt ix_chunk_vecs_embedding concurrently"


def make_vector_maintenance_handler(
    embed: EmbedFn,
) -> Callable[[Session, Job, Progress], None]:
    reindex = make_vector_reindex_handler(embed)

    def handler(session: Session, job: Job, report: Progress) -> None:
        payload = _payload(job)
        action = str(payload.get("action") or "")
        dry_run = bool(payload.get("dry_run"))
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
            reindex(session, job, report)
            return

        if action == "vacuum":
            _vacuum(session, StudyVectorStore(session).index_table)
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
                    "note": "vacuumed the legacy vector table",
                },
            )
            session.commit()
            report(100, "vacuum complete")
            return

        if action == "index-rebuild":
            note = _rebuild_index(session)
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
                },
            )
            session.commit()
            report(100, "index rebuild complete")
            return

        live_ids = {str(chunk_id) for chunk_id in session.scalars(select(Chunk.id)).all()}
        store = StudyVectorStore(session)
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
            },
        )
        session.commit()
        report(100, "orphan sweep complete")

    return handler


def make_vector_cutover_handler() -> Callable[[Session, Job, Progress], None]:
    def handler(session: Session, job: Job, report: Progress) -> None:
        del session, job, report
        raise JobError(
            "vector cutover is unavailable: study has no vector-space lifecycle "
            "cutover target yet (plan 51 Q3c); the legacy content space remains "
            "readable"
        )

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
