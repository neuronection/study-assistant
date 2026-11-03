"""Bounded retrieval-operations aggregates (plan 51 Q0/Q3a).

Both tables are **operational aggregates, not audit ledgers**: they are
TTL-pruned (query rollups 30 days, coverage snapshots 90 days), so losing a
row loses a measurement, never a record. They are written off the request
hot path (the telemetry flusher and the reconcile handler), never by a
dashboard read.

Study has no vector-space lifecycle table yet, so ``space_id`` is the stable
synthetic id of the legacy `chunk_vecs` store (``legacy-chunk-vecs``); it is
a string, not a foreign key. Q3b replaces it with a real space id when the
lifecycle lands.
"""

from ...core.vocab import DegradedReason
from ..payloads import LatencyHistogram
from ..schema_contract import vocab_check
from .core import (
    _UUID,
    JSON,
    Base,
    CheckConstraint,
    DateTime,
    Float,
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
