"""material description

Revision ID: 0052_material_description
Revises: 0051_elo_ratings
Create Date: 2026-09-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0052_material_description"
down_revision: str | None = "0051_elo_ratings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("materials", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("materials", "description")
