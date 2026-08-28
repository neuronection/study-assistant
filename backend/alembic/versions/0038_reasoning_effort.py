"""models.reasoning_effort (per-model reasoning control, 37-reasoning follow-up)

Revision ID: 0038_reasoning_effort
Revises: 0037_cached_input_tokens
Create Date: 2026-08-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038_reasoning_effort"
down_revision: str | None = "0037_cached_input_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("models") as batch_op:
        batch_op.add_column(sa.Column("reasoning_effort", sa.String(20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("models") as batch_op:
        batch_op.drop_column("reasoning_effort")
