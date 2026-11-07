"""The one active retrieval space, read through the study vector-store adapter.

Plan 50 P3a added the ``vector_spaces``/``vector_documents``/
``vector_records`` metadata layer, Q3c2a moved the content space onto a real
family backend, and Q3c2b1 added the lifecycle. This module therefore reports
the **active** configuration honestly: the adapter resolves the one active
space row (or the pre-migration ``vec_meta`` fallback), the dialect decides
the backend, and coverage comes only from the latest
``retrieval_coverage_snapshots`` row for that real space id.

Everything below is the adapter boundary: no retrieval DTO or route builds
raw vector SQL itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...domain.models import (
    Chunk,
    Extraction,
    Material,
    RetrievalCoverageSnapshot,
    VectorSpace,
)
from ...storage import vectors
from ...storage.retrieval_ops import (
    COVERAGE_GATE,
    CoverageDTO,
    GateStatus,
    SpaceChunkDTO,
    SpaceDTO,
    SpaceStatus,
    SpaceTokenizerDTO,
)
from ...storage.vector_store import (
    CONTENT_SPACE_ID,
    CONTENT_SPACE_NAME,
    StudyVectorStore,
    embedding_assignment,
)
from . import lifecycle

V1_SPACE_ID = CONTENT_SPACE_ID
V1_SPACE_NAME = CONTENT_SPACE_NAME
V1_KIND = lifecycle.V1_KIND
COVERAGE_TTL_DAYS = 90


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    moment = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return moment.isoformat().replace("+00:00", "Z")


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class LegacyStore:
    space_id: str
    name: str
    provider: str
    model: str
    dim: int
    backend: str
    index_table: str
    documents: int
    records: int
    chunk_total: int
    meta: dict[str, str]
    key: str = ""
    metadata_row: bool = False
    status: str = "active"
    health_ok: bool = True
    health_detail: str = ""
    created_at: str | None = None
    activated_at: str | None = None
    retired_at: str | None = None
    token_aware: bool = False
    tokenizer: SpaceTokenizerDTO | None = None
    chunk: SpaceChunkDTO | None = None


def _distinct_documents(session: Session) -> int:
    value = session.execute(
        select(func.count(func.distinct(Material.id)))
        .select_from(Chunk)
        .join(Extraction, Extraction.id == Chunk.extraction_id)
        .join(Material, Material.id == Extraction.material_id)
    ).scalar()
    return int(value or 0)


def _chunk_total(session: Session) -> int:
    value = session.execute(select(func.count()).select_from(Chunk)).scalar()
    return int(value or 0)


def load_store(session: Session, space_id: str | None = None) -> LegacyStore | None:
    """One store through the adapter, or ``None`` when unprovisioned."""
    store = StudyVectorStore(session, space_id=space_id)
    space = store.content_space()
    if space is None:
        return None
    assignment = embedding_assignment(session)
    physical_records = store.vector_count()
    metadata_ready = store.metadata_complete()
    health = store.health()
    return LegacyStore(
        space_id=space.space_id,
        name=space.name,
        provider=assignment.provider if assignment.provider else space.provider,
        model=space.model,
        dim=space.dim,
        backend=health.backend,
        index_table=space.index_table,
        documents=(store.document_count() if metadata_ready else _distinct_documents(session)),
        records=physical_records,
        chunk_total=_chunk_total(session),
        meta=vectors.read_meta(session),
        key=space.key,
        metadata_row=space.metadata_row,
        status=space.status,
        health_ok=health.ok,
        health_detail=health.detail,
        created_at=_row_time(session, space.space_id, "created_at"),
        activated_at=_row_time(session, space.space_id, "activated_at"),
        retired_at=_row_time(session, space.space_id, "retired_at"),
        token_aware=space.token_aware,
        tokenizer=_tokenizer_payload(space),
        chunk=_chunk_payload(space),
    )


def _tokenizer_payload(space: Any) -> SpaceTokenizerDTO | None:
    tokenizer = getattr(space, "tokenizer", None)
    if tokenizer is None:
        return None
    return SpaceTokenizerDTO(
        kind=str(tokenizer.kind),
        identifier=tokenizer.identifier,
        revision=tokenizer.revision,
        artifact_sha256=tokenizer.artifact_sha256,
        exact=bool(tokenizer.exact),
        max_input_tokens=int(tokenizer.max_input_tokens),
        source=str(tokenizer.source),
    )


def _chunk_payload(space: Any) -> SpaceChunkDTO | None:
    chunk = getattr(space, "chunk", None)
    if chunk is None:
        return None
    return SpaceChunkDTO(
        max_chunk_tokens=int(chunk.max_chunk_tokens),
        overlap_tokens=int(chunk.overlap_tokens),
        max_chars=int(chunk.max_chars),
    )


def _row_time(session: Session, space_id: str, field: str) -> str | None:
    row = session.get(VectorSpace, space_id)
    if row is None:
        return None
    return iso(getattr(row, field))


def latest_coverage(
    session: Session, space_id: str | None = None
) -> RetrievalCoverageSnapshot | None:
    if space_id is None:
        store = StudyVectorStore(session)
        space = store.content_space()
        if space is None:
            return None
        space_id = space.space_id
    return lifecycle.latest_coverage(session, space_id)


def coverage_dto(
    session: Session, store: LegacyStore | None = None, *, space_id: str | None = None
) -> CoverageDTO:
    target = space_id or (store.space_id if store is not None else None)
    if target is None:
        space = StudyVectorStore(session).content_space()
        target = space.space_id if space is not None else V1_SPACE_ID
    snapshot = latest_coverage(session, target)
    if snapshot is None:
        return CoverageDTO(
            space_id=target,
            as_of=None,
            total=0,
            missing=0,
            stale=0,
            failed=0,
            embedded=0,
            coverage=None,
            gate=GateStatus.UNKNOWN,
        )
    coverage = snapshot.embedded / snapshot.total if snapshot.total > 0 else None
    gate = (
        GateStatus.UNKNOWN
        if coverage is None
        else (GateStatus.PASS if coverage >= COVERAGE_GATE else GateStatus.FAIL)
    )
    return CoverageDTO(
        space_id=snapshot.space_id,
        as_of=iso(snapshot.as_of),
        total=snapshot.total,
        missing=snapshot.missing,
        stale=snapshot.stale,
        failed=snapshot.failed,
        embedded=snapshot.embedded,
        coverage=coverage,
        gate=gate,
        ann_recall=snapshot.ann_recall,
        ann_recall_k=snapshot.ann_recall_k,
        probe_size=snapshot.probe_size,
    )


def space_dto(session: Session, store: LegacyStore) -> SpaceDTO:
    coverage = coverage_dto(session, store, space_id=store.space_id)
    return SpaceDTO(
        space_id=store.space_id,
        name=store.name,
        status=SpaceStatus(store.status),
        provider=store.provider,
        model=store.model,
        dim=store.dim,
        backend=store.backend,
        index_table=store.index_table,
        documents=store.documents,
        records=store.records,
        coverage=coverage.coverage,
        stale=None,
        failed=coverage.failed if coverage.as_of is not None else None,
        created_at=store.created_at,
        activated_at=store.activated_at,
        retired_at=store.retired_at,
        last_reindex_at=None,
        last_error=None if store.health_ok else store.health_detail,
        gate=coverage.gate,
        as_of=coverage.as_of,
        token_aware=store.token_aware,
        tokenizer=store.tokenizer,
        chunk=store.chunk,
    )


def write_coverage_snapshot(
    session: Session,
    *,
    total: int,
    embedded: int,
    missing: int,
    failed: int = 0,
    stale: int = 0,
    ann_recall: float | None = None,
    ann_recall_k: int | None = None,
    probe_size: int | None = None,
    space_id: str | None = None,
) -> RetrievalCoverageSnapshot:
    """Append the reconcile pass's one honest coverage point for its space."""
    target = space_id
    if target is None:
        space = StudyVectorStore(session).content_space()
        target = space.space_id if space is not None else V1_SPACE_ID
    row = lifecycle.write_coverage_snapshot(
        session,
        space_id=target,
        total=total,
        embedded=embedded,
        missing=missing,
        failed=failed,
        stale=stale,
    )
    row.ann_recall = ann_recall
    row.ann_recall_k = ann_recall_k
    row.probe_size = probe_size
    prune_coverage(session, now=row.as_of)
    return row


def prune_coverage(session: Session, *, now: datetime | None = None) -> int:
    """Drop snapshots past the 90-day operational TTL (not an audit ledger)."""
    moment = now or utcnow()
    cutoff = moment.timestamp() - COVERAGE_TTL_DAYS * 86_400
    cutoff_dt = datetime.fromtimestamp(cutoff, UTC)
    rows = session.scalars(
        select(RetrievalCoverageSnapshot).where(RetrievalCoverageSnapshot.as_of < cutoff_dt)
    ).all()
    for row in rows:
        session.delete(row)
    return len(rows)
