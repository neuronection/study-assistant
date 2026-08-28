"""phase 7: analytics rollups, item stats, study goals

Revision ID: 0010_analytics
Revises: 0009_notes_flashcards
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_analytics"
down_revision: str | None = "0009_notes_flashcards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "concept_skill_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("skill", sa.String(length=20), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("avg_time_ratio", sa.Float(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weakness_score", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
    )
    with op.batch_alter_table("concept_skill_stats", schema=None) as batch_op:
        batch_op.create_index(
            "uq_concept_skill_stats", ["profile_id", "concept", "skill"], unique=True
        )
    op.create_table(
        "daily_rollups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("answers_n", sa.Integer(), nullable=False),
        sa.Column("correct_n", sa.Integer(), nullable=False),
        sa.Column("cards_reviewed", sa.Integer(), nullable=False),
        sa.Column("minutes", sa.Float(), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
    )
    with op.batch_alter_table("daily_rollups", schema=None) as batch_op:
        batch_op.create_index(
            "uq_daily_rollups", ["profile_id", "day"], unique=True
        )
    op.create_table(
        "item_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("n_attempts", sa.Integer(), nullable=False),
        sa.Column("p_correct", sa.Float(), nullable=False),
        sa.Column("avg_time_ms", sa.Float(), nullable=True),
        sa.Column("avg_time_ratio", sa.Float(), nullable=True),
        sa.Column("distractor_selection", sa.JSON(), nullable=True),
        sa.Column("flag", sa.String(length=10), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
    )
    with op.batch_alter_table("item_stats", schema=None) as batch_op:
        batch_op.create_index("uq_item_stats", ["question_id"], unique=True)
    op.create_table(
        "study_goals",
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("answers_per_day", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("profile_id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
    )


def downgrade() -> None:
    op.drop_table("study_goals")
    with op.batch_alter_table("item_stats", schema=None) as batch_op:
        batch_op.drop_index("uq_item_stats")
    op.drop_table("item_stats")
    with op.batch_alter_table("daily_rollups", schema=None) as batch_op:
        batch_op.drop_index("uq_daily_rollups")
    op.drop_table("daily_rollups")
    with op.batch_alter_table("concept_skill_stats", schema=None) as batch_op:
        batch_op.drop_index("uq_concept_skill_stats")
    op.drop_table("concept_skill_stats")
