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
Activation/cutover require physical health, coverage **and** the golden-query
quality compare (Q3c2b2); a missing or below-floor set is a structured refusal
with the compare persisted on the run result.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..ai.embeddings import embed_with_tags
from ..ai.tokenizers.accounting import TokenAccounting, embedding_accounting
from ..core.vocab import JobType
from ..domain.models import Chunk, Job, VectorSpace
from ..jobs.payloads import JobResult
from ..jobs.runner import JobError
from ..pipelines.chunking import InputTooLong
from ..services.progress import parse_progress_carry
from ..services.retrieval import lifecycle, quality
from ..services.retrieval.audit import build_vector_event
from ..services.retrieval.chunk_profile import (
    ChunkProfile,
    batch_window_specs,
    profile_from_row,
    window_specs_for_chunk,
)
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
from ..storage.vector_store import CONTENT_SPACE_ID, StudyVectorStore, VectorRecordSpec

logger = structlog.get_logger(__name__)

EmbedFn = Callable[[list[str]], tuple[str, list[list[float]]] | None]
Progress = Callable[[int, str, dict[str, Any] | None], None]

DEFAULT_LIMIT = 500
MAX_LIMIT = 5_000
DEFAULT_BATCH_SIZE = 32
MAX_BATCH_SIZE = 256
MAINTENANCE_ACTIONS = ("orphan-sweep", "vacuum", "index-rebuild", "retry-failed")


@dataclass
class _ProgressMeter:
    """Cumulative live counters for one reindex run (plan 52 T5c).

    ``total_documents`` is exact at scan start (or carried by a continuation).
    Chunk totals are exact only for the v1 one-record-per-chunk path; the v2
    window count is estimated from the running average, and the detail always
    says which it is. The meter never stores ids or text.
    """

    total_documents: int
    processed_documents: int = 0
    processed_chunks: int = 0
    embedded_chunks: int = 0
    skipped_chunks: int = 0
    failed_chunks: int = 0
    embedded_documents: int = 0
    skipped_documents: int = 0
    failed_documents: int = 0
    tokens: int | None = 0
    tokens_exact: bool = False
    embed_calls: int = 0
    chunks_estimated: bool = True

    @classmethod
    def from_carry(cls, carry: Mapping[str, Any], total_documents: int) -> _ProgressMeter:
        carried_total = int(carry.get("total_documents") or 0)
        tokens = carry.get("tokens")
        return cls(
            total_documents=carried_total or total_documents,
            processed_documents=int(carry.get("processed_documents") or 0),
            processed_chunks=int(carry.get("processed_chunks") or 0),
            embedded_chunks=int(carry.get("embedded_chunks") or 0),
            skipped_chunks=int(carry.get("skipped_chunks") or 0),
            failed_chunks=int(carry.get("failed_chunks") or 0),
            embedded_documents=int(carry.get("embedded_documents") or 0),
            skipped_documents=int(carry.get("skipped_documents") or 0),
            failed_documents=int(carry.get("failed_documents") or 0),
            tokens=tokens if isinstance(tokens, int) and not isinstance(tokens, bool) else 0,
            tokens_exact=bool(carry.get("tokens_exact")),
            embed_calls=int(carry.get("embed_calls") or 0),
        )

    @property
    def pending_documents(self) -> int:
        return max(self.total_documents - self.processed_documents, 0)

    def detail(self, phase: str, *, done: bool = False) -> dict[str, Any]:
        """The bounded detail for one progress write (counts only)."""
        pending_documents = self.pending_documents
        if self.processed_documents > 0:
            average = self.processed_chunks / self.processed_documents
            pending_chunks = max(round(average * pending_documents), 0)
        elif not self.chunks_estimated:
            pending_chunks = pending_documents
        else:
            pending_chunks = 0
        return {
            "phase": phase,
            "processed_documents": self.processed_documents,
            "total_documents": self.total_documents,
            "processed_chunks": self.processed_chunks,
            "pending_chunks": pending_chunks,
            "total_chunks": self.processed_chunks + pending_chunks,
            "chunks_estimated": self.chunks_estimated,
            "embedded_chunks": self.embedded_chunks,
            "skipped_chunks": self.skipped_chunks,
            "failed_chunks": self.failed_chunks,
            "embedded_documents": self.embedded_documents,
            "skipped_documents": self.skipped_documents,
            "failed_documents": self.failed_documents,
            "tokens": self.tokens,
            "tokens_estimated": self.tokens is not None and not self.tokens_exact,
            "embed_calls": self.embed_calls,
            "exact_tokenizer": self.tokens is not None and self.tokens_exact,
            "done": done,
        }

    def carry(self) -> dict[str, Any]:
        return {
            "processed_documents": self.processed_documents,
            "total_documents": self.total_documents,
            "processed_chunks": self.processed_chunks,
            "embedded_chunks": self.embedded_chunks,
            "skipped_chunks": self.skipped_chunks,
            "failed_chunks": self.failed_chunks,
            "embedded_documents": self.embedded_documents,
            "skipped_documents": self.skipped_documents,
            "failed_documents": self.failed_documents,
            "tokens": self.tokens,
            "tokens_exact": self.tokens_exact,
            "embed_calls": self.embed_calls,
        }


def _report(
    report: Progress,
    value: int,
    stage: str,
    detail: Mapping[str, Any] | None = None,
) -> None:
    report(value, stage, dict(detail) if detail is not None else None)


def _percent(processed: int, total: int) -> int:
    return max(1, min(99, int(processed * 100 / max(total, 1))))


def _carry_for(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return parse_progress_carry(payload.get("progress_carry"))
    except ValueError as error:
        raise JobError(str(error)) from error


def _count_v1_tokens(accounting: TokenAccounting, texts: Sequence[str]) -> tuple[int, bool]:
    """The local tokenizer count for one v1 batch (never provider-billed)."""
    total = 0
    exact = True
    for value in texts:
        count = accounting.count(value)
        total += count.tokens
        exact = exact and count.exact
    return total, exact


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
    carry = _carry_for(payload)
    store = StudyVectorStore(session, space_id=target)
    profile = profile_from_row(session.get(VectorSpace, target))
    if profile is not None:
        return _reindex_tokens(
            session,
            job,
            report,
            embed,
            payload,
            target=target,
            store=store,
            profile=profile,
            chunks=chunks,
            total=total,
            limited=limited,
            only_ids=only_ids,
            batch_size=batch_size,
            carry=carry,
        )
    stored_hashes = store.stored_chunk_hashes()
    stored_ids = set(store.stored_chunk_ids().values())
    accounting = embedding_accounting(session)
    meter = _ProgressMeter.from_carry(carry, total)
    meter.chunks_estimated = False
    if carry.get("tokens") is None:
        meter.tokens = 0
        meter.tokens_exact = accounting.exact

    scanned = 0
    embedded = 0
    skipped = 0
    failed = 0
    failed_ids: list[str] = []
    pending: list[Chunk] = []
    _report(
        report,
        _percent(meter.processed_documents, meter.total_documents),
        "scanning chunks",
        meter.detail("scanning"),
    )

    def mark_failed(ids: Sequence[str]) -> None:
        nonlocal failed, failed_ids
        failed += len(ids)
        failed_ids.extend(ids)
        meter.failed_documents += len(ids)
        meter.failed_chunks += len(ids)
        meter.processed_chunks += len(ids)

    def flush_pending() -> None:
        nonlocal embedded
        if not pending:
            return
        texts = [chunk.text for chunk in pending]
        ids = [chunk.id for chunk in pending]
        tags: dict[str, Any] = {
            "space_id": target,
            "kind": str(payload.get("kind") or "material"),
            "view": str(payload.get("view") or "body"),
        }
        if len(pending) == 1:
            tags["chunk_index"] = int(pending[0].ordinal)
        pending.clear()
        meter.embed_calls += 1
        try:
            result = embed_with_tags(embed, texts, tags)
        except Exception as error:
            logger.warning(
                "vector_reindex_embed_failed",
                job_id=job.id,
                count=len(ids),
                error=str(error)[:300],
            )
            mark_failed(ids)
            return
        if result is None:
            mark_failed(ids)
            return
        model, batch = result
        if len(batch) != len(ids):
            mark_failed(ids)
            return
        store.store(ids, batch, model)
        session.commit()
        embedded += len(ids)
        meter.embedded_documents += len(ids)
        meter.embedded_chunks += len(ids)
        meter.processed_chunks += len(ids)
        tokens, exact = _count_v1_tokens(accounting, texts)
        meter.tokens = (meter.tokens or 0) + tokens
        meter.tokens_exact = meter.tokens_exact and exact

    for chunk in chunks:
        _report(
            report,
            _percent(meter.processed_documents, meter.total_documents),
            f"reindex {scanned}/{len(chunks)}",
            meter.detail("scanning"),
        )
        scanned += 1
        meter.processed_documents += 1
        if not force:
            current = stored_hashes.get(str(chunk.id))
            if current is not None and current == content_hash(chunk.text):
                skipped += 1
                meter.skipped_documents += 1
                meter.skipped_chunks += 1
                meter.processed_chunks += 1
                continue
            if current is None and target == CONTENT_SPACE_ID and chunk.id in stored_ids:
                skipped += 1
                meter.skipped_documents += 1
                meter.skipped_chunks += 1
                meter.processed_chunks += 1
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
                coverage=(coverage.embedded / coverage.total if coverage.total > 0 else None),
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
    terminal = str(job.type) == JobType.VECTOR_REINDEX.value
    _report(
        report,
        100,
        "reindex complete",
        meter.detail(
            "done" if terminal and not limited else "writing", done=terminal and not limited
        ),
    )
    return RunResultDTO(
        scanned=scanned,
        embedded=embedded,
        skipped=skipped,
        failed=failed,
        failed_ids=tuple(failed_ids[:FAILED_IDS_LIMIT]),
        failed_ids_truncated=len(failed_ids) > FAILED_IDS_LIMIT,
        gate=gate,
    )


def _reindex_tokens(
    session: Session,
    job: Job,
    report: Progress,
    embed: EmbedFn,
    payload: dict[str, Any],
    *,
    target: str,
    store: StudyVectorStore,
    profile: ChunkProfile,
    chunks: Sequence[Chunk],
    total: int,
    limited: bool,
    only_ids: set[str] | None,
    batch_size: int,
    carry: Mapping[str, Any],
) -> RunResultDTO:
    """Token-aware reindex: windows are the write unit, chunks the coverage unit."""
    force = bool(payload.get("force"))
    stored = store.stored_record_hashes()
    meter = _ProgressMeter.from_carry(carry, total)
    meter.chunks_estimated = True
    if carry.get("tokens") is None:
        meter.tokens = 0
        meter.tokens_exact = profile.exact
    scanned = 0
    embedded = 0
    skipped = 0
    failed = 0
    failed_ids: list[str] = []
    embedded_chunks: set[str] = set()
    too_long = 0
    _report(
        report,
        _percent(meter.processed_documents, meter.total_documents),
        "scanning chunks",
        meter.detail("scanning"),
    )

    def write(specs: list[Any]) -> None:
        nonlocal embedded, failed, failed_ids
        if not specs:
            return
        chunk_ids = {str(spec.chunk_id) for spec in specs}
        tags: dict[str, Any] = {
            "space_id": target,
            "kind": str(payload.get("kind") or "material"),
            "view": str(payload.get("view") or "body"),
        }
        if len(chunk_ids) == 1:
            tags["chunk_index"] = int(specs[0].window_index)
        meter.embed_calls += 1
        try:
            result = embed_with_tags(embed, [str(spec.text) for spec in specs], tags)
        except Exception as error:
            logger.warning(
                "vector_reindex_embed_failed",
                job_id=job.id,
                count=len(specs),
                error=str(error)[:300],
            )
            failed += len(chunk_ids)
            failed_ids.extend(sorted(chunk_ids))
            meter.failed_documents += len(chunk_ids)
            meter.failed_chunks += len(specs)
            return
        if result is None:
            failed += len(chunk_ids)
            failed_ids.extend(sorted(chunk_ids))
            meter.failed_documents += len(chunk_ids)
            meter.failed_chunks += len(specs)
            return
        model, batch = result
        if len(batch) != len(specs):
            failed += len(chunk_ids)
            failed_ids.extend(sorted(chunk_ids))
            meter.failed_documents += len(chunk_ids)
            meter.failed_chunks += len(specs)
            return
        store.store_specs(
            [
                VectorRecordSpec(
                    chunk_id=str(spec.chunk_id),
                    text=str(spec.text),
                    chunk_index=int(spec.window_index),
                    char_start=spec.char_start,
                    char_end=spec.char_end,
                    token_count=spec.token_count,
                    token_start=spec.token_start,
                    token_end=spec.token_end,
                )
                for spec in specs
            ],
            batch,
            model,
        )
        session.commit()
        embedded_chunks.update(chunk_ids)
        embedded = len(embedded_chunks)
        meter.embedded_documents += len(chunk_ids)
        meter.embedded_chunks += len(specs)
        meter.tokens = (meter.tokens or 0) + sum(int(spec.token_count) for spec in specs)
        meter.tokens_exact = meter.tokens_exact and profile.exact

    for chunk in chunks:
        _report(
            report,
            _percent(meter.processed_documents, meter.total_documents),
            f"reindex {scanned}/{len(chunks)}",
            meter.detail("scanning"),
        )
        scanned += 1
        meter.processed_documents += 1
        try:
            specs = window_specs_for_chunk(chunk, profile)
        except InputTooLong as error:
            logger.warning(
                "vector_reindex_input_too_long",
                job_id=job.id,
                chunk_id=str(chunk.id),
                tokens=error.tokens,
                limit=error.limit,
            )
            failed += 1
            failed_ids.append(str(chunk.id))
            meter.failed_documents += 1
            meter.failed_chunks += 1
            too_long += 1
            continue
        meter.processed_chunks += len(specs)
        changed = [
            spec
            for spec in specs
            if force or stored.get((spec.chunk_id, spec.window_index)) != spec.content_hash
        ]
        if not changed:
            skipped += 1
            meter.skipped_documents += 1
            meter.skipped_chunks += len(specs)
            continue
        for batch in batch_window_specs(changed, profile, max_items=batch_size):
            write(batch)

    gate = GateStatus.UNKNOWN
    if not limited and only_ids is None:
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
                coverage=(coverage.embedded / coverage.total if coverage.total > 0 else None),
            )
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
        extra={"failed_reason": "input_too_long"} if too_long else None,
    )
    terminal = str(job.type) == JobType.VECTOR_REINDEX.value
    _report(
        report,
        100,
        "reindex complete",
        meter.detail(
            "done" if terminal and not limited else "writing", done=terminal and not limited
        ),
    )
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
        _report(report, 1, action)
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
            _report(report, 100, "vacuum complete")
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
            _report(report, 100, "index rebuild complete")
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
            _report(report, 100, "orphan sweep dry-run complete")
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
        _report(report, 100, "orphan sweep complete")

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
                    "quality": None,
                    "quality_state": "already_active",
                    "bad_matches": [],
                    "message": "space is already active; nothing to cut over",
                    "space": lifecycle.ActivationResult(
                        space_id=str(row.id),
                        name=str(row.name),
                        space_key=lifecycle.space_key_for(row),
                        already_active=True,
                    ).as_dict(),
                },
            )
            session.commit()
            _report(report, 100, "space already active")
            return
        if row.status != "building":
            raise JobError(
                f"space {row.name!r} is {row.status}; only a building space can be cut over"
            )
        _report(report, 5, "backfilling candidate space")
        result = _reindex(session, job, report, embed, payload)
        if result.gate is not GateStatus.PASS:
            raise JobError(
                f"cutover refused: space {row.name!r} is not fully covered "
                f"(gate={result.gate.value}); backfill it before cutover"
            )
        _report(report, 85, "coverage gate passed; evaluating golden-query quality")
        active = lifecycle.active_space_row(session)
        baseline = (
            active
            if active is not None and str(active.id) != str(row.id)
            else None
        )
        try:
            outcome = quality.compare_spaces(
                session, baseline, row, embed=embed
            )
        except quality.GoldenSetMissing as error:
            _finish(
                session,
                job,
                scanned=result.scanned,
                embedded=result.embedded,
                skipped=result.skipped,
                failed=result.failed,
                failed_ids=list(result.failed_ids),
                gate=GateStatus.FAIL,
                space_id=target,
                extra={
                    "action": "cutover",
                    "quality": None,
                    "quality_state": "not_sampled",
                    "bad_matches": [],
                    "gate_reasons": ["quality_no_golden_set"],
                },
            )
            raise JobError(f"cutover refused: {error}") from error
        except quality.QualitySetupBlocked as error:
            _finish(
                session,
                job,
                scanned=result.scanned,
                embedded=result.embedded,
                skipped=result.skipped,
                failed=result.failed,
                failed_ids=list(result.failed_ids),
                gate=GateStatus.FAIL,
                space_id=target,
                extra={
                    "action": "cutover",
                    "quality": None,
                    "quality_state": "blocked",
                    "bad_matches": [],
                    "gate_reasons": ["quality_blocked"],
                },
            )
            raise JobError(f"cutover refused: {error}") from error
        if not outcome.passed:
            _finish(
                session,
                job,
                scanned=result.scanned,
                embedded=result.embedded,
                skipped=result.skipped,
                failed=result.failed,
                failed_ids=list(result.failed_ids),
                gate=GateStatus.FAIL,
                space_id=target,
                extra={
                    "action": "cutover",
                    "quality": outcome.compare.to_dict(),
                    "quality_state": "sampled",
                    "bad_matches": list(outcome.bad_matches),
                    "gate_reasons": ["quality_below_floor"],
                },
            )
            raise JobError(
                f"cutover refused: space {row.name!r} is below the golden-query "
                f"quality floor (recall={outcome.compare.new_recall_at_k:.4f}, "
                f"precision={outcome.compare.new_precision_at_k:.4f})"
            )
        _report(report, 90, "coverage and quality gates passed; activating")
        try:
            activated = lifecycle.activate_space(
                session,
                target,
                quality=GateStatus.PASS,
                quality_state="sampled",
                quality_compare=outcome.compare.to_dict(),
            )
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
                "quality": outcome.compare.to_dict(),
                "quality_state": "sampled",
                "bad_matches": list(outcome.bad_matches),
                "activation_gate": (
                    activated.gate.as_dict() if activated.gate is not None else None
                ),
                "legacy_compat_retained": activated.legacy_compat_retained,
            },
        )
        session.commit()
        _report(report, 100, "cutover complete")

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
