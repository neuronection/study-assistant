"""cloud calendar links + exam/deadline plan kinds

Plan 52 / ADR-0052: a course can bind its own cloud calendar. The link row is
a credential *binding* (provider, calendar location, direction, scopes) with
no token column — tokens live in the OS keyring under
``calendar:<id>:<slot>``. Plan items gain the exam/deadline kinds so a
deadline and an examination are first-class projections, not relabelled
milestones.

SQLite cannot widen a CHECK in place; the constraint swaps through
``batch_alter_table(recreate="always")``. A downgrade fails loudly if a row
still holds ``exam``/``deadline`` (same posture as 0008) rather than silently
rewriting study data.

Revision ID: 0009_calendar_links
Revises: 0008_quiz_question_kinds
Create Date: 2026-11-03
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_calendar_links"
down_revision = "0008_quiz_question_kinds"
branch_labels = None
depends_on = None

BASELINE_KINDS = ("study", "practice", "review", "milestone")
PLAN_ITEM_KINDS = (*BASELINE_KINDS, "exam", "deadline")
BASELINE_ORIGINS = ("manual", "draft")
PLAN_ITEM_ORIGINS = (*BASELINE_ORIGINS, "calendar")

DIRECTIONS = ("push", "pull", "two-way")
STATUSES = ("ok", "degraded", "failing", "stale", "needs-auth", "needs-secret")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    with op.batch_alter_table("plan_items", recreate="always") as batch:
        batch.drop_constraint("kind_allowed", type_="check")
        batch.create_check_constraint("kind_allowed", f"kind IN ({_values(PLAN_ITEM_KINDS)})")
        batch.drop_constraint("origin_allowed", type_="check")
        batch.create_check_constraint(
            "origin_allowed", f"origin IN ({_values(PLAN_ITEM_ORIGINS)})"
        )
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            )
        )

    op.create_table(
        "calendar_links",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("auth_kind", sa.String(20), nullable=False, server_default="none"),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("account_label", sa.String(200), nullable=True),
        sa.Column("calendar_id", sa.String(512), nullable=True),
        sa.Column("calendar_url", sa.String(2048), nullable=True),
        sa.Column("base_url", sa.String(2048), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("secret_ref", sa.String(200), nullable=True),
        sa.Column("direction", sa.String(20), nullable=False, server_default="push"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(20), nullable=False, server_default="needs-auth"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sync_cursor", sa.String(1024), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"direction IN ({_values(DIRECTIONS)})", name="direction_allowed"),
        sa.CheckConstraint(f"status IN ({_values(STATUSES)})", name="status_allowed"),
    )
    op.create_index("ix_calendar_links_profile_id", "calendar_links", ["profile_id"])
    op.create_index("ix_calendar_links_course_id", "calendar_links", ["course_id"])
    op.create_index("ix_calendar_links_profile", "calendar_links", ["profile_id"])
    op.create_index(
        "uq_calendar_links_course_calendar",
        "calendar_links",
        ["course_id", "provider", "calendar_id"],
        unique=True,
    )

    op.create_table(
        "calendar_event_links",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "link_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("calendar_links.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("local_id", sa.String(64), nullable=False),
        sa.Column("uid", sa.String(200), nullable=False),
        sa.Column("remote_id", sa.String(2048), nullable=True),
        sa.Column("etag", sa.String(256), nullable=True),
        sa.Column("local_hash", sa.String(64), nullable=True),
        sa.Column("remote_hash", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_calendar_event_links_link_id", "calendar_event_links", ["link_id"])
    op.create_index(
        "ix_calendar_event_links_local", "calendar_event_links", ["link_id", "local_id"]
    )
    op.create_index(
        "uq_calendar_event_links_link_uid",
        "calendar_event_links",
        ["link_id", "uid"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_calendar_event_links_link_uid", table_name="calendar_event_links")
    op.drop_index("ix_calendar_event_links_local", table_name="calendar_event_links")
    op.drop_index("ix_calendar_event_links_link_id", table_name="calendar_event_links")
    op.drop_table("calendar_event_links")
    op.drop_index("uq_calendar_links_course_calendar", table_name="calendar_links")
    op.drop_index("ix_calendar_links_profile", table_name="calendar_links")
    op.drop_index("ix_calendar_links_course_id", table_name="calendar_links")
    op.drop_index("ix_calendar_links_profile_id", table_name="calendar_links")
    op.drop_table("calendar_links")

    with op.batch_alter_table("plan_items", recreate="always") as batch:
        batch.drop_constraint("kind_allowed", type_="check")
        batch.create_check_constraint("kind_allowed", f"kind IN ({_values(BASELINE_KINDS)})")
        batch.drop_constraint("origin_allowed", type_="check")
        batch.create_check_constraint(
            "origin_allowed", f"origin IN ({_values(BASELINE_ORIGINS)})"
        )
        batch.drop_column("updated_at")
