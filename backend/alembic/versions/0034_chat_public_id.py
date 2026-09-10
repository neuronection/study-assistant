"""chat routability: chat_sessions.public_id (opaque UUID for URLs)

Revision ID: 0034_chat_public_id
Revises: 0033_widget_state
Create Date: 2026-08-24

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0034_chat_public_id"
down_revision: str | None = "0033_widget_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_columns = {column["name"] for column in inspector.get_columns("chat_sessions")}

    if "public_id" not in existing_columns:
        with op.batch_alter_table("chat_sessions") as batch_op:
            batch_op.add_column(sa.Column("public_id", sa.String(36), nullable=True))

    for (session_id,) in connection.execute(
        sa.text("SELECT id FROM chat_sessions WHERE public_id IS NULL")
    ).fetchall():
        connection.execute(
            sa.text("UPDATE chat_sessions SET public_id = :public_id WHERE id = :id"),
            {"public_id": str(uuid4()), "id": session_id},
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("chat_sessions")}
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.alter_column("public_id", existing_type=sa.String(36), nullable=False)
        if "ix_chat_sessions_public_id" not in existing_indexes:
            batch_op.create_index("ix_chat_sessions_public_id", ["public_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_index("ix_chat_sessions_public_id")
        batch_op.drop_column("public_id")
