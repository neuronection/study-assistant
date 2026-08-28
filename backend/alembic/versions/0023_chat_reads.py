"""phase 11B: chat READ tool indicators

Revision ID: 0023_chat_reads
Revises: 0022_chat_mentions
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_chat_reads"
down_revision: str | None = "0022_chat_mentions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(sa.Column("reads", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("reads")
