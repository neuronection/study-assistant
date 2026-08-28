"""drawing view box — saved-region scale metadata for drawings

Revision ID: 0046_drawing_view_box
Revises: 0045_material_fts_trigram
Create Date: 2026-08-28

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0046_drawing_view_box"
down_revision: str | None = "0045_material_fts_trigram"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "note_drawings", sa.Column("view", sa.JSON(), nullable=True)
    )
    op.add_column(
        "material_drawings", sa.Column("view", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("material_drawings", "view")
    op.drop_column("note_drawings", "view")
