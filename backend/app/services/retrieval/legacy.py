"""The one retrieval space, read through the study vector-store adapter.

Plan 50 P3a added the ``vector_spaces``/``vector_documents``/
``vector_records`` metadata layer, but the physical backend is still the
legacy `chunk_vecs` store. This module therefore reports the **active
configuration** honestly: the adapter resolves the ``content`` space
(``legacy-chunk-vecs``) and its ``vec_meta`` model/dim, the dialect decides
the backend, and coverage comes only from the latest
``retrieval_coverage_snapshots`` row. A store with no ``vec_meta`` dim is
cold — never a fabricated 0 %/100 % number.

Everything below is the adapter boundary: no retrieval DTO or route builds
raw vector SQL itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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
    SpaceDTO,
    SpaceStatus,
)
from ...storage.vector_store import (
    CONTENT_SPACE_ID,
    CONTENT_SPACE_NAME,
    StudyVectorStore,
    embedding_assignment,
)

LEGACY_SPACE_ID = CONTENT_SPACE_ID
LEGACY_SPACE_NAME = CONTENT_SPACE_NAME
LEGACY_KIND = "chunk"
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


def load_store(session: Session) -> LegacyStore | None:
    """The active store through the adapter, or ``None`` when unprovisioned."""
    store = StudyVectorStore(session)
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
        created_at=_row_time(session, "created_at"),
        activated_at=_row_time(session, "activated_at"),
        retired_at=_row_time(session, "retired_at"),
    )


def _row_time(session: Session, field: str) -> str | None:
    row = session.get(VectorSpace, CONTENT_SPACE_ID)
    if row is None:
        return None
    return iso(getattr(row, field))


def latest_coverage(session: Session) -> RetrievalCoverageSnapshot | None:
    return session.scalars(
        select(RetrievalCoverageSnapshot)
        .where(
            RetrievalCoverageSnapshot.space_id == LEGACY_SPACE_ID,
            RetrievalCoverageSnapshot.kind == LEGACY_KIND,
        )
        .order_by(RetrievalCoverageSnapshot.as_of.desc())
        .limit(1)
    ).first()


def coverage_dto(session: Session, store: LegacyStore | None = None) -> CoverageDTO:
    snapshot = latest_coverage(session)
    if snapshot is None:
        return CoverageDTO(
            space_id=store.space_id if store is not None else LEGACY_SPACE_ID,
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
    coverage = coverage_dto(session, store)
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
) -> RetrievalCoverageSnapshot:
    """Append the reconcile pass's one honest coverage point."""
    moment = utcnow()
    row = RetrievalCoverageSnapshot(
        space_id=LEGACY_SPACE_ID,
        kind=LEGACY_KIND,
        as_of=moment,
        total=max(total, 0),
        missing=max(missing, 0),
        stale=max(stale, 0),
        failed=max(failed, 0),
        embedded=max(embedded, 0),
        ann_recall=ann_recall,
        ann_recall_k=ann_recall_k,
        probe_size=probe_size,
        created_at=moment,
        updated_at=moment,
    )
    session.add(row)
    session.flush()
    prune_coverage(session, now=moment)
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
