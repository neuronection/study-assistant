"""Review filters + review source (plan 99-B).

``review_log.source`` distinguishes a real scheduled review from a cram
preview (logged for time/streak honesty, never fed to FSRS/Elo) and from
external/backfill imports. ``review_filters`` stores named, profile-scoped
filter presets (course/node, ahead window, limit, order).

Revision ID: 0023_review_filters
Revises: 0022_fsrs_settings
Create Date: 2026-11-11
"""

from typing import Literal

import sqlalchemy as sa

from alembic import op

revision = "0023_review_filters"
down_revision = "0022_fsrs_settings"
branch_labels = None
depends_on = None

SOURCES = ("review", "cram_preview", "external", "backfill")
ORDERS = ("due", "oldest", "mixed")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def _recreate_mode() -> Literal["auto", "always"]:
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    with op.batch_alter_table("review_log", recreate=_recreate_mode()) as batch:
        batch.add_column(
            sa.Column("source", sa.String(length=20), nullable=False, server_default="review")
        )
        batch.create_check_constraint("source_allowed", f"source IN ({_values(SOURCES)})")

    op.create_table(
        "review_filters",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("include_not_due", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("due_window_days", sa.Integer(), nullable=True),
        sa.Column("limit", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.String(length=20), nullable=False, server_default="due"),
        sa.Column("kinds", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.CheckConstraint(f"sort_order IN ({_values(ORDERS)})", name="sort_order_allowed"),
    )
    op.create_index("ix_review_filters_profile_id", "review_filters", ["profile_id"])
    op.create_index("ix_review_filters_course_id", "review_filters", ["course_id"])
    op.create_index("ix_review_filters_node_id", "review_filters", ["node_id"])
    op.create_index(
        "ix_review_filters_profile_created", "review_filters", ["profile_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_review_filters_profile_created", table_name="review_filters")
    op.drop_index("ix_review_filters_node_id", table_name="review_filters")
    op.drop_index("ix_review_filters_course_id", table_name="review_filters")
    op.drop_index("ix_review_filters_profile_id", table_name="review_filters")
    op.drop_table("review_filters")
    with op.batch_alter_table("review_log", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("source_allowed", type_="check")
        batch.drop_column("source")
