"""The legacy `chunk_vecs` store read as one synthetic retrieval space.

Study has no vector-space lifecycle table (plan 50's ``vector_spaces`` never
landed here). Q3a therefore reports the **active legacy configuration**
honestly: ``vec_meta`` decides the model/dim, the dialect decides the
backend, ``chunk_vecs`` is the index table, and coverage comes only from the
latest ``retrieval_coverage_snapshots`` row. A store with no ``vec_meta`` dim
is cold — never a fabricated 0 %/100 % number.

Everything below is the adapter boundary: no retrieval DTO or route builds
raw vector SQL itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...ai.embeddings import EMBEDDINGS_TASK
from ...domain.models import (
    AiModel,
    Chunk,
    DefaultTaskAssignment,
    Extraction,
    Material,
    Provider,
    RetrievalCoverageSnapshot,
    TaskAssignment,
)
from ...storage import vectors
from ...storage.retrieval_ops import (
    COVERAGE_GATE,
    CoverageDTO,
    GateStatus,
    SpaceDTO,
    SpaceStatus,
)

LEGACY_SPACE_ID = "legacy-chunk-vecs"
LEGACY_SPACE_NAME = "content (legacy chunk_vecs)"
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


@dataclass(frozen=True)
class EmbeddingAssignment:
    provider: str
    model: str
    dim: int | None


def backend_for(session: Session) -> str:
    return "pgvector" if session.get_bind().dialect.name == "postgresql" else "sqlite_vec"


def backend_label(backend: str) -> str:
    if backend == "pgvector":
        return "PostgreSQL pgvector/HNSW"
    if backend == "sqlite_vec":
        return "SQLite sqlite-vec"
    return "Linear fallback — desktop scale"


def embedding_assignment(session: Session) -> EmbeddingAssignment:
    assignment = session.get(TaskAssignment, EMBEDDINGS_TASK)
    model_id = assignment.model_id if assignment is not None else None
    if model_id is None:
        default = session.get(DefaultTaskAssignment, "embeddings")
        model_id = default.model_id if default is not None else None
    if model_id is None:
        return EmbeddingAssignment(provider="unassigned", model="unassigned", dim=None)
    model = session.get(AiModel, model_id)
    if model is None:
        return EmbeddingAssignment(provider="unassigned", model="unassigned", dim=None)
    provider = session.get(Provider, model.provider_id)
    label = provider.name if provider is not None else "unknown"
    return EmbeddingAssignment(provider=label, model=model.external_id, dim=None)


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
    """The active legacy store, or ``None`` when it was never provisioned."""
    meta = vectors.read_meta(session)
    raw_dim = meta.get("dim")
    if raw_dim is None:
        return None
    try:
        dim = int(raw_dim)
    except ValueError:
        return None
    if dim <= 0:
        return None
    assignment = embedding_assignment(session)
    model = meta.get("model") or assignment.model
    return LegacyStore(
        space_id=LEGACY_SPACE_ID,
        name=LEGACY_SPACE_NAME,
        provider=assignment.provider,
        model=model,
        dim=dim,
        backend=backend_for(session),
        index_table=vectors.VEC_TABLE,
        documents=_distinct_documents(session),
        records=vectors.vector_count(session),
        chunk_total=_chunk_total(session),
        meta=meta,
    )


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


def coverage_dto(
    session: Session, store: LegacyStore | None = None
) -> CoverageDTO:
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
    coverage = (
        snapshot.embedded / snapshot.total
        if snapshot.total > 0
        else None
    )
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
        status=SpaceStatus.ACTIVE,
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
        created_at=None,
        activated_at=None,
        retired_at=None,
        last_reindex_at=None,
        last_error=None,
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
        select(RetrievalCoverageSnapshot).where(
            RetrievalCoverageSnapshot.as_of < cutoff_dt
        )
    ).all()
    for row in rows:
        session.delete(row)
    return len(rows)
