"""FSRS settings — user-owned scheduling parameters (plan 99-A).

Two tables: one profile row (created on first save) and per-course overrides
whose nullable columns inherit the profile value. The scheduler resolves
course → profile → defaults; existing profiles have no row, so the shipped
FSRS-4.5 defaults (90%, 365 days, 20 new/200 reviews a day) keep today's
behaviour until the student opts in.

Revision ID: 0022_fsrs_settings
Revises: 0021_document_anchors
Create Date: 2026-11-10
"""

from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0022_fsrs_settings"
down_revision = "0021_document_anchors"
branch_labels = None
depends_on = None

LEECH_ACTIONS = ("tag", "suspend", "none")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def _columns() -> list[Any]:
    return [
        sa.Column("desired_retention", sa.Float(), nullable=False, server_default="0.9"),
        sa.Column(
            "maximum_interval_days", sa.Integer(), nullable=False, server_default="365"
        ),
        sa.Column("new_per_day", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("reviews_per_day", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("leech_threshold", sa.Integer(), nullable=False, server_default="8"),
        sa.Column(
            "leech_action", sa.String(length=20), nullable=False, server_default="tag"
        ),
        sa.Column(
            "bury_siblings", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "load_balance", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _checks(prefix: str) -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(
            f"leech_action IN ({_values(LEECH_ACTIONS)})", name="leech_action_allowed"
        ),
        sa.CheckConstraint(
            "desired_retention BETWEEN 0.70 AND 0.97", name="retention_range"
        ),
        sa.CheckConstraint(
            "maximum_interval_days BETWEEN 30 AND 3650", name="interval_range"
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "fsrs_settings",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        *_columns(),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        *_checks("fsrs_settings"),
    )
    op.create_index("ix_fsrs_settings_profile_id", "fsrs_settings", ["profile_id"])
    op.create_index("uq_fsrs_settings_profile", "fsrs_settings", ["profile_id"], unique=True)

    op.create_table(
        "course_fsrs_overrides",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("desired_retention", sa.Float(), nullable=True),
        sa.Column("maximum_interval_days", sa.Integer(), nullable=True),
        sa.Column("new_per_day", sa.Integer(), nullable=True),
        sa.Column("reviews_per_day", sa.Integer(), nullable=True),
        sa.Column("leech_threshold", sa.Integer(), nullable=True),
        sa.Column("leech_action", sa.String(length=20), nullable=True),
        sa.Column("bury_siblings", sa.Boolean(), nullable=True),
        sa.Column("load_balance", sa.Boolean(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        *_checks("course_fsrs_overrides"),
    )
    op.create_index(
        "ix_course_fsrs_overrides_course_id", "course_fsrs_overrides", ["course_id"]
    )
    op.create_index(
        "uq_course_fsrs_overrides_course",
        "course_fsrs_overrides",
        ["course_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_course_fsrs_overrides_course", table_name="course_fsrs_overrides")
    op.drop_index(
        "ix_course_fsrs_overrides_course_id", table_name="course_fsrs_overrides"
    )
    op.drop_table("course_fsrs_overrides")
    op.drop_index("uq_fsrs_settings_profile", table_name="fsrs_settings")
    op.drop_index("ix_fsrs_settings_profile_id", table_name="fsrs_settings")
    op.drop_table("fsrs_settings")
