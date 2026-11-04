"""retrieval alerts + caller-supplied generation tags (plan 51 Q3c3a)

Adds the minimal seams Q3c3a needs:

* ``ai_interactions.metadata`` (JSON, non-null, default ``{}``) and
  ``metadata_schema_version`` — the caller-supplied embedding tags
  (``space_id``/``kind``/``view``/``chunk_index``). Study's ledger is
  ``ai_interactions`` (not career's ``ai_generations``); the gateway records
  exactly what the caller hands it and never invents a tag.
* ``notification_kinds`` — the boot-seeded closed alert-kind registry.
* ``notifications`` — one deduped event row with admin recipient ids and a
  partial unique dedup key. This is the existing bell/aggregate's storage
  seam, not a second notification path.

The alert kinds/thresholds themselves stay in the vendored family contract
(``ALERT_DEFAULTS``); this migration only creates the store.

Downgrade drops the two notification tables and the two ledger columns; run
history keeps its metadata until then.

Revision ID: 0015_retrieval_alerts
Revises: 0014_vector_record_chunk_id
Create Date: 2026-11-04
"""

from typing import Literal

import sqlalchemy as sa

from alembic import op

revision = "0015_retrieval_alerts"
down_revision = "0014_vector_record_chunk_id"
branch_labels = None
depends_on = None

NOTIFICATION_KINDS = (
    "retrieval.coverage_low",
    "retrieval.reindex_failed",
    "retrieval.reindex_stalled",
    "retrieval.quality_gate",
    "retrieval.query_slo",
    "retrieval.degraded_rate",
    "retrieval.provider_unassigned",
    "retrieval.index_missing",
    "retrieval.budget_exhausted",
    "retrieval.space_drop_pending",
)
SEVERITIES = ("info", "warning", "error")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def _recreate_mode() -> Literal["auto", "always"]:
    """SQLite copies the table; PostgreSQL alters it in place."""
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    with op.batch_alter_table("ai_interactions", recreate=_recreate_mode()) as batch:
        batch.add_column(
            sa.Column(
                "metadata",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch.add_column(
            sa.Column(
                "metadata_schema_version",
                sa.SmallInteger(),
                nullable=False,
                server_default="1",
            )
        )

    op.create_table(
        "notification_kinds",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
        sa.Column("admin_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("default_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"key IN ({_values(NOTIFICATION_KINDS)})", name="key_allowed"),
        sa.CheckConstraint(f"severity IN ({_values(SEVERITIES)})", name="severity_allowed"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.JSON(), nullable=True),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("dedup_key", sa.String(length=200), nullable=True),
        sa.Column("dedup_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["kind"], ["notification_kinds.key"], ondelete="CASCADE"),
        sa.CheckConstraint(f"severity IN ({_values(SEVERITIES)})", name="severity_allowed"),
    )
    op.create_index("ix_notifications_kind", "notifications", ["kind"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_kind_created", "notifications", ["kind", "created_at"])
    op.create_index(
        "uq_notifications_dedup_key",
        "notifications",
        ["dedup_key"],
        unique=True,
        postgresql_where=sa.text("dedup_key IS NOT NULL"),
        sqlite_where=sa.text("dedup_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_notifications_dedup_key", table_name="notifications")
    op.drop_index("ix_notifications_kind_created", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_kind", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("notification_kinds")
    with op.batch_alter_table("ai_interactions", recreate=_recreate_mode()) as batch:
        batch.drop_column("metadata_schema_version")
        batch.drop_column("metadata")
