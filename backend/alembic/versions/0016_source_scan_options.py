"""phase 8B L3: per-source scan intervals and scan error reporting

Revision ID: 0016_source_scan_options
Revises: 0015_source_link_nodes
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_source_scan_options"
down_revision: str | None = "0015_source_link_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("material_sources") as batch_op:
        batch_op.add_column(
            sa.Column("scan_interval_sec", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("last_scan_error", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("material_sources") as batch_op:
        batch_op.drop_column("last_scan_error")
        batch_op.drop_column("scan_interval_sec")
