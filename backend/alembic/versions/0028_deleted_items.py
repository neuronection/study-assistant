"""plan 22D: snapshot-based trash for destructive deletes (ADR-048)

Revision ID: 0028_deleted_items
Revises: 0027_note_versions
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_deleted_items"
down_revision: str | None = "0027_note_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deleted_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id", sa.Integer(), sa.ForeignKey("profiles.id"), nullable=False
        ),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "deleted_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "purge_after", sa.DateTime(timezone=True), nullable=False
        ),
    )
    op.create_index("ix_deleted_items_profile_id", "deleted_items", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_deleted_items_profile_id", table_name="deleted_items")
    op.drop_table("deleted_items")
