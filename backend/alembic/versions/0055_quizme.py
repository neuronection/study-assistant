"""quiz-me chat mode

Revision ID: 0055_quizme
Revises: 0054_plan_items
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0055_quizme"
down_revision: str | None = "0054_plan_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column(
            "quizme", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("quiz_pending", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "quiz_pending")
    op.drop_column("chat_sessions", "quizme")
