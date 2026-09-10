"""plan 28: error_patterns (course-type-scoped error-pattern taxonomies, ADR-063)

Revision ID: 0031_error_patterns
Revises: 0030_material_folder_links
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_error_patterns"
down_revision: str | None = "0030_material_folder_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "error_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("course_type_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("detection", sa.JSON(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_type_id"], ["course_types.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_error_patterns_course_type", "error_patterns", ["course_type_id"])


def downgrade() -> None:
    op.drop_index("ix_error_patterns_course_type", table_name="error_patterns")
    op.drop_table("error_patterns")
