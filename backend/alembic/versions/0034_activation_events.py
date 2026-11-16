"""Local-only activation counters (plan 101-F).

Profile-scoped events, no content and no network path. The closed event
vocabulary mirrors ``ActivationEvent``.

Revision ID: 0034_activation_events
Revises: 0033_ai_cost_provenance
Create Date: 2026-11-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0034_activation_events"
down_revision = "0033_ai_cost_provenance"
branch_labels = None
depends_on = None

EVENTS = (
    "onboarding_step",
    "first_file_ingested",
    "first_review",
    "first_quiz",
    "first_ai_call",
    "first_capture",
    "update_installed",
    "highlight_to_card",
    "brief_played_50pct",
    "solve_completed",
    "paper_sat",
    "device_linked",
    "feature_opened",
    "tip_dismissed",
)


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    op.create_table(
        "activation_events",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("props", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.CheckConstraint(f"event IN ({_values(EVENTS)})", name="event_allowed"),
    )
    op.create_index("ix_activation_events_profile_id", "activation_events", ["profile_id"])
    op.create_index("ix_activation_events_profile_at", "activation_events", ["profile_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_activation_events_profile_at", table_name="activation_events")
    op.drop_index("ix_activation_events_profile_id", table_name="activation_events")
    op.drop_table("activation_events")
