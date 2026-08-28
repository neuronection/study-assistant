"""phase 5b: quiz help events + chat session context

Revision ID: 0008_quiz_help
Revises: 0007_exercises
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_quiz_help"
down_revision: str | None = "0007_exercises"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quiz_help_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("violations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("quiz_help_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_quiz_help_events_attempt_question", ["attempt_id", "question_id"], unique=False
        )
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("context", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        batch_op.drop_column("context")
    with op.batch_alter_table("quiz_help_events", schema=None) as batch_op:
        batch_op.drop_index("ix_quiz_help_events_attempt_question")
    op.drop_table("quiz_help_events")
