"""phase 10C: tree nodes AI hint

Revision ID: 0021_tree_ai_hint
Revises: 0020_course_required
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_tree_ai_hint"
down_revision: str | None = "0020_course_required"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tree_nodes") as batch_op:
        batch_op.add_column(sa.Column("ai_hint", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tree_nodes") as batch_op:
        batch_op.drop_column("ai_hint")
