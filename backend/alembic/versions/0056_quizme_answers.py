"""quiz-me daily answer credit

Revision ID: 0056_quizme_answers
Revises: 0055_quizme
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0056_quizme_answers"
down_revision: str | None = "0055_quizme"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quizme_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("chat_sessions.id"),
            nullable=False,
        ),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
    )
    op.create_index(
        "ix_quizme_answers_profile_id", "quizme_answers", ["profile_id"]
    )
    op.create_index(
        "ix_quizme_answers_session_id", "quizme_answers", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_quizme_answers_session_id", table_name="quizme_answers")
    op.drop_index("ix_quizme_answers_profile_id", table_name="quizme_answers")
    op.drop_table("quizme_answers")
