"""phase 11C1: chat HITL proposals

Revision ID: 0024_chat_proposals
Revises: 0023_chat_reads
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_chat_proposals"
down_revision: str | None = "0023_chat_reads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey("chat_messages.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("chat_proposals")
