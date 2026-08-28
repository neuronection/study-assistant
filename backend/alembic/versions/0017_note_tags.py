"""phase 8C: notes tags

Revision ID: 0017_note_tags
Revises: 0016_source_scan_options
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_note_tags"
down_revision: str | None = "0016_source_scan_options"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notes") as batch_op:
        batch_op.add_column(sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notes") as batch_op:
        batch_op.drop_column("tags")
