"""profile preferences + chat_sessions.use_embeddings (query-embedding toggle)

Revision ID: 0039_use_embeddings
Revises: 0038_reasoning_effort
Create Date: 2026-08-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0039_use_embeddings"
down_revision: str | None = "0038_reasoning_effort"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.add_column(sa.Column("preferences", sa.JSON(), nullable=True))
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(sa.Column("use_embeddings", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_column("use_embeddings")
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.drop_column("preferences")
