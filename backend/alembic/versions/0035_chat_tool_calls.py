"""chat tool calls: chat_messages.tool_calls (tool name + args shown in the tutor)

Revision ID: 0035_chat_tool_calls
Revises: 0034_chat_public_id
Create Date: 2026-08-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035_chat_tool_calls"
down_revision: str | None = "0034_chat_public_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(sa.Column("tool_calls", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("tool_calls")
