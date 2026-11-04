"""retrieval-operations job slot, run result and bounded rollups

Plan 51 Q3a (ADR-0051 companion; contracts/retrieval_ops.py). Adds the three
family ``VECTOR_*`` job types to the closed ``jobs.type`` CHECK, the bounded
``jobs.result`` payload (stage/progress already exist), and the two
TTL-retained aggregates the read surface composes:
``retrieval_query_rollups`` and ``retrieval_coverage_snapshots``.

Study has no vector-space lifecycle table yet, so both rollups key
``space_id`` as the synthetic legacy store id rather than a foreign key;
Q3b replaces it when the lifecycle lands.

The rollups are operational aggregates, not audit ledgers (TTL 30/90 days),
so ADR-0044's no-silent-pruning rule does not apply. Downgrade drops them;
a downgrade from rows carrying the new job types fails loudly at the CHECK
rather than rewriting run history.

Revision ID: 0010_retrieval_ops
Revises: 0009_calendar_links
Create Date: 2026-11-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_retrieval_ops"
down_revision = "0009_calendar_links"
branch_labels = None
depends_on = None

BASELINE_JOB_TYPES = (
    "ingest",
    "postprocess",
    "chat_turn",
    "drawing_ocr",
    "image_ocr",
    "genesis",
    "url_import",
    "compose",
)
VECTOR_JOB_TYPES = (
    *BASELINE_JOB_TYPES,
    "VECTOR_REINDEX",
    "VECTOR_MAINTENANCE",
    "VECTOR_CUTOVER",
)
DEGRADED_REASONS = (
    "provider_unassigned",
    "embed_failed",
    "index_missing",
    "space_mismatch",
    "over_cap",
)


def _recreate_mode() -> str:
    """SQLite copies the table; PostgreSQL alters it in place.

    A PostgreSQL ``recreate="always"`` copy drops the primary key and fails
    while dependent foreign keys still reference it.
    """
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    with op.batch_alter_table("jobs", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("type_allowed", type_="check")
        batch.create_check_constraint("type_allowed", f"type IN ({_values(VECTOR_JOB_TYPES)})")
        batch.add_column(sa.Column("result", sa.JSON(), nullable=True))

    op.create_table(
        "retrieval_query_rollups",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("space_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("view", sa.String(length=32), nullable=True),
        sa.Column("degraded_reason", sa.String(length=24), nullable=True),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_width", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zero_results", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidates_sum", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_histogram", sa.JSON(), nullable=True),
        sa.Column(
            "latency_histogram_schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"degraded_reason IS NULL OR degraded_reason IN ({_values(DEGRADED_REASONS)})",
            name="degraded_reason_allowed",
        ),
        sa.CheckConstraint("bucket_width > 0", name="bucket_width_positive"),
        sa.CheckConstraint("count >= 0", name="count_non_negative"),
        sa.CheckConstraint(
            "zero_results >= 0 AND zero_results <= count", name="zero_results_range"
        ),
        sa.CheckConstraint("candidates_sum >= 0", name="candidates_sum_non_negative"),
    )
    op.create_index(
        "uq_retrieval_query_rollups_dims",
        "retrieval_query_rollups",
        [
            "space_id",
            "kind",
            sa.text("COALESCE(view, '')"),
            sa.text("COALESCE(degraded_reason, '')"),
            "bucket_start",
            "bucket_width",
        ],
        unique=True,
    )
    op.create_index(
        "ix_retrieval_query_rollups_space_bucket",
        "retrieval_query_rollups",
        ["space_id", "bucket_start"],
    )

    op.create_table(
        "retrieval_coverage_snapshots",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("space_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stale", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ann_recall", sa.Float(), nullable=True),
        sa.Column("ann_recall_k", sa.Integer(), nullable=True),
        sa.Column("probe_size", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "total >= 0 AND missing >= 0 AND stale >= 0 AND failed >= 0 AND embedded >= 0",
            name="coverage_counts_non_negative",
        ),
        sa.CheckConstraint(
            "ann_recall IS NULL OR (ann_recall >= 0 AND ann_recall <= 1)",
            name="ann_recall_range",
        ),
        sa.CheckConstraint(
            "ann_recall_k IS NULL OR ann_recall_k > 0", name="ann_recall_k_positive"
        ),
        sa.CheckConstraint(
            "probe_size IS NULL OR probe_size >= 0", name="probe_size_non_negative"
        ),
        sa.UniqueConstraint("space_id", "kind", "as_of", name="uq_retrieval_coverage_point"),
    )
    op.create_index(
        "ix_retrieval_coverage_snapshots_space_kind",
        "retrieval_coverage_snapshots",
        ["space_id", "kind", "as_of"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrieval_coverage_snapshots_space_kind",
        table_name="retrieval_coverage_snapshots",
    )
    op.drop_table("retrieval_coverage_snapshots")

    op.drop_index(
        "ix_retrieval_query_rollups_space_bucket", table_name="retrieval_query_rollups"
    )
    op.drop_index("uq_retrieval_query_rollups_dims", table_name="retrieval_query_rollups")
    op.drop_table("retrieval_query_rollups")

    with op.batch_alter_table("jobs", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("type_allowed", type_="check")
        batch.create_check_constraint(
            "type_allowed", f"type IN ({_values(BASELINE_JOB_TYPES)})"
        )
        batch.drop_column("result")
