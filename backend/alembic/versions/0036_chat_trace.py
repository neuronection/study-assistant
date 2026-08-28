"""chat turn trace: chat_messages.trace (phase/round timeline with timings)

Revision ID: 0036_chat_trace
Revises: 0035_chat_tool_calls
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_chat_trace"
down_revision: str | None = "0035_chat_tool_calls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(sa.Column("trace", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("trace")
