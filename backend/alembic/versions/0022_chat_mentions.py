"""phase 11A: chat mentions + session mention registry

Revision ID: 0022_chat_mentions
Revises: 0021_tree_ai_hint
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_chat_mentions"
down_revision: str | None = "0021_tree_ai_hint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(sa.Column("mentions", sa.JSON(), nullable=True))
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(sa.Column("mention_registry", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("mentions")
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_column("mention_registry")
