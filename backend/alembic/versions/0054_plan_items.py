"""study planner items

Revision ID: 0054_plan_items
Revises: 0053_scratchpad
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054_plan_items"
down_revision: str | None = "0053_scratchpad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id"),
            nullable=False,
        ),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column(
            "kind", sa.String(length=20), nullable=False, server_default="study"
        ),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "origin", sa.String(length=20), nullable=False, server_default="manual"
        ),
        sa.Column("sort_key", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
        ),
    )
    op.create_index(
        "ix_plan_items_course_due", "plan_items", ["course_id", "due_date"]
    )
    op.create_index(
        "ix_plan_items_profile_due", "plan_items", ["profile_id", "due_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_plan_items_profile_due", table_name="plan_items")
    op.drop_index("ix_plan_items_course_due", table_name="plan_items")
    op.drop_table("plan_items")
