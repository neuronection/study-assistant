"""phase 7 slice 3: material sources (linked folders), profiles UI support

Revision ID: 0011_sources
Revises: 0010_analytics
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_sources"
down_revision: str | None = "0010_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("recursive", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("include_globs", sa.JSON(), nullable=True),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("material_sources", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_sources_profile_id"), ["profile_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("material_sources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_material_sources_profile_id"))
    op.drop_table("material_sources")
