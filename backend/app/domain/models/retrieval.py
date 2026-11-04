"""Retrieval-operations aggregates and the vector-space metadata layer.

Plan 51 Q0/Q3a added the two bounded aggregates; plan 50 P3a adds the
portable vector metadata (``vector_spaces``, ``vector_documents``,
``vector_records``) that plan 51 Q3c's lifecycle/cutover and coverage reads
address.

The aggregates are **operational, not audit ledgers**: they are TTL-pruned
(query rollups 30 days, coverage snapshots 90 days), so losing a row loses a
measurement, never a record. They are written off the request hot path (the
telemetry flusher and the reconcile handler), never by a dashboard read.

Study's physical index is still the legacy `chunk_vecs` table, so the one
``content`` space keeps the synthetic id ``legacy-chunk-vecs`` (a string, not
a UUID) that Q3a/Q3b already stamp into the rollups. The metadata rows are a
mapping over that physical store; the space-scoped document/record identity
is the adapter's business (``storage/vector_store.py``), not a source-table
foreign key.
"""

from sqlalchemy import BigInteger, LargeBinary

from ...core.vocab import DegradedReason
from ...storage.vector_contract import METRICS, V1_VIEWS, SpaceStatus
from ..payloads import LatencyHistogram
from ..schema_contract import vocab_check
from .core import (
    _UUID,
    JSON,
    Base,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Mapped,
    String,
    UniqueConstraint,
    datetime,
    mapped_column,
    new_uuid,
    text,
    utcnow,
)

LEGACY_INDEX_TABLE = "chunk_vecs"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_SPACE_STATUS_CHECK = f"status IN ({_quoted(tuple(member.value for member in SpaceStatus))})"
_METRIC_CHECK = f"metric IN ({_quoted(METRICS)})"
_VIEW_CHECK = f"view IN ({_quoted(V1_VIEWS)})"
_INDEX_TABLE_CHECK = (
    "index_table IS NULL OR index_table = '"
    f"{LEGACY_INDEX_TABLE}' OR "
    "(index_table LIKE 'vec_%' AND length(index_table) = 12)"
)


class VectorSpace(Base):
    """One versioned embedding configuration (plan 50 §3.1).

    ``id`` is a string rather than a UUID because study's legacy ``content``
    space must keep the ``legacy-chunk-vecs`` id its rollups and coverage
    snapshots already carry. ``index_table`` is ``chunk_vecs`` while the
    physical backend stays legacy; ``NULL`` means linear and a future
    ``vec_<8hex>`` value means a provisioned space (Q3c).

    Retention: operational, derived configuration. A retired space is kept
    only for its purge grace period and is then dropped by an audited ops
    action — never pruned silently.
    """

    __tablename__ = "vector_spaces"
    __table_args__ = (
        CheckConstraint(_SPACE_STATUS_CHECK, name="status_allowed"),
        CheckConstraint(_METRIC_CHECK, name="metric_allowed"),
        CheckConstraint("dim > 0", name="dim_positive"),
        CheckConstraint(_INDEX_TABLE_CHECK, name="index_table_shape"),
        UniqueConstraint("index_table", name="uq_vector_spaces_index_table"),
        Index(
            "uq_vector_spaces_name_active",
            "name",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index("ix_vector_spaces_name", "name"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120))
    dim: Mapped[int] = mapped_column(Integer)
    metric: Mapped[str] = mapped_column(
        String(10), default=METRICS[0], server_default=METRICS[0]
    )
    normalize: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    query_prefix: Mapped[str | None] = mapped_column(String(80))
    document_prefix: Mapped[str | None] = mapped_column(String(80))
    chunker_version: Mapped[str] = mapped_column(String(20), default="1", server_default="1")
    composer_version: Mapped[str] = mapped_column(String(20), default="1", server_default="1")
    index_table: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(
        String(12), default=SpaceStatus.ACTIVE.value, server_default=SpaceStatus.ACTIVE.value
    )
    backfill_done: Mapped[int | None] = mapped_column(Integer)
    backfill_total: Mapped[int | None] = mapped_column(Integer)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class VectorDocument(Base):
    """One source entity in a space (plan 50 §3.2) — here a material.

    ``kind`` + ``source_id`` are the polymorphic source handle (study's
    legacy mapping uses ``kind='material'`` and the material UUID). There is
    deliberately no FK to the source table: the writer's delete hook and the
    orphan sweep own erasure. ``profile_id`` is the study scope axis.

    Retention: operational, derived. Hard-deleted with its source; the
    document is a rebuild unit, never a record of its own.
    """

    __tablename__ = "vector_documents"
    __table_args__ = (
        UniqueConstraint("space_id", "kind", "source_id", name="uq_vector_documents_source"),
        Index("ix_vector_documents_space_profile", "space_id", "profile_id"),
        Index("ix_vector_documents_space_kind", "space_id", "kind"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    space_id: Mapped[str] = mapped_column(
        ForeignKey("vector_spaces.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(80))
    profile_id: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    source_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    schema_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class VectorRecord(Base):
    """One embeddable unit — study's ``body`` view of one chunk (plan 50 §3.3).

    ``rowid`` is the legacy physical rowid and therefore the reverse map into
    ``chunk_vec_ids``; it stays ``NULL`` for a record that has no physical
    vector yet and is unique per space. ``content_hash`` is the family hash
    rule over the chunk text (empty only for rows the migration mapped
    without hashing — a backfill fills them). ``embedding`` stays ``NULL``
    while sqlite-vec/pgvector owns the vector payload.

    Retention: operational, derived. Hard-deleted with its document; a
    reindex replaces records in place by ``(document, view, chunk_index)``.
    """

    __tablename__ = "vector_records"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "view", "chunk_index", name="uq_vector_records_document_view_chunk"
        ),
        CheckConstraint(_VIEW_CHECK, name="view_allowed"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        CheckConstraint(
            "char_start IS NULL OR char_end IS NULL OR char_end >= char_start",
            name="char_range_ordered",
        ),
        Index("ix_vector_records_space_view", "space_id", "view"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("vector_documents.id", ondelete="CASCADE"), index=True
    )
    space_id: Mapped[str] = mapped_column(
        ForeignKey("vector_spaces.id", ondelete="CASCADE"), index=True
    )
    view: Mapped[str] = mapped_column(String(32), default="body")
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    rowid: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RetrievalQueryRollup(Base):
    __tablename__ = "retrieval_query_rollups"
    __table_args__ = (
        Index(
            "uq_retrieval_query_rollups_dims",
            "space_id",
            "kind",
            text("COALESCE(view, '')"),
            text("COALESCE(degraded_reason, '')"),
            "bucket_start",
            "bucket_width",
            unique=True,
        ),
        CheckConstraint("bucket_width > 0", name="bucket_width_positive"),
        CheckConstraint("count >= 0", name="count_non_negative"),
        CheckConstraint("zero_results >= 0 AND zero_results <= count", name="zero_results_range"),
        CheckConstraint("candidates_sum >= 0", name="candidates_sum_non_negative"),
        vocab_check("degraded_reason", DegradedReason, nullable=True),
        Index("ix_retrieval_query_rollups_space_bucket", "space_id", "bucket_start"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    space_id: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(40))
    view: Mapped[str | None] = mapped_column(String(32))
    degraded_reason: Mapped[str | None] = mapped_column(String(24))
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bucket_width: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    zero_results: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    candidates_sum: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    latency_histogram: Mapped[LatencyHistogram | None] = mapped_column(JSON)
    latency_histogram_schema_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RetrievalCoverageSnapshot(Base):
    __tablename__ = "retrieval_coverage_snapshots"
    __table_args__ = (
        UniqueConstraint("space_id", "kind", "as_of", name="uq_retrieval_coverage_point"),
        CheckConstraint(
            "total >= 0 AND missing >= 0 AND stale >= 0 AND failed >= 0 AND embedded >= 0",
            name="coverage_counts_non_negative",
        ),
        CheckConstraint(
            "ann_recall IS NULL OR (ann_recall >= 0 AND ann_recall <= 1)",
            name="ann_recall_range",
        ),
        CheckConstraint("ann_recall_k IS NULL OR ann_recall_k > 0", name="ann_recall_k_positive"),
        CheckConstraint("probe_size IS NULL OR probe_size >= 0", name="probe_size_non_negative"),
        Index("ix_retrieval_coverage_snapshots_space_kind", "space_id", "kind", "as_of"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    space_id: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(40))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    missing: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    stale: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    embedded: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    ann_recall: Mapped[float | None] = mapped_column(Float)
    ann_recall_k: Mapped[int | None] = mapped_column(Integer)
    probe_size: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = ["RetrievalCoverageSnapshot", "RetrievalQueryRollup"]
