"""plan 34D: widget state channel — chat_messages.state + step_attempts.state

Revision ID: 0033_widget_state
Revises: 0032_material_drawings
Create Date: 2026-08-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033_widget_state"
down_revision: str | None = "0032_material_drawings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(sa.Column("state", sa.JSON(), nullable=True))
    with op.batch_alter_table("step_attempts") as batch_op:
        batch_op.add_column(sa.Column("state", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("step_attempts") as batch_op:
        batch_op.drop_column("state")
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("state")
