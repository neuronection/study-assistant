"""ai_interactions.cached_input_tokens (prompt-cache accounting for 37D)

Revision ID: 0037_cached_input_tokens
Revises: 0036_chat_trace
Create Date: 2026-08-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037_cached_input_tokens"
down_revision: str | None = "0036_chat_trace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_interactions") as batch_op:
        batch_op.add_column(
            sa.Column("cached_input_tokens", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_interactions") as batch_op:
        batch_op.drop_column("cached_input_tokens")
