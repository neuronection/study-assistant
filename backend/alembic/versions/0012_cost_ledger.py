"""phase 7 slice 4: ai_interactions task column for the cost ledger

Revision ID: 0012_cost_ledger
Revises: 0011_sources
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_cost_ledger"
down_revision: str | None = "0011_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("task", sa.String(length=40), nullable=True))
    with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
        batch_op.create_index("ix_ai_interactions_task", ["task"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
        batch_op.drop_index("ix_ai_interactions_task")
    with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
        batch_op.drop_column("task")
