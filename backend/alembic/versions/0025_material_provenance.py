"""phase 11D: materials provenance

Revision ID: 0025_material_provenance
Revises: 0024_chat_proposals
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_material_provenance"
down_revision: str | None = "0024_chat_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("materials") as batch_op:
        batch_op.add_column(sa.Column("provenance", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("materials") as batch_op:
        batch_op.drop_column("provenance")
