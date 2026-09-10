"""plan 29: material_drawings (text/markdown materials own drawings, ADR-064)

Revision ID: 0032_material_drawings
Revises: 0031_error_patterns
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032_material_drawings"
down_revision: str | None = "0031_error_patterns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_drawings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("strokes", sa.JSON(), nullable=False),
        sa.Column("png_sha", sa.String(length=64), nullable=True),
        sa.Column("ocr_version", sa.Integer(), nullable=False),
        sa.Column("ocr_blocks", sa.JSON(), nullable=True),
        sa.Column("ocr_markdown", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.ForeignKeyConstraint(["png_sha"], ["blobs.sha256"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_material_drawings_material_id", "material_drawings", ["material_id"])


def downgrade() -> None:
    op.drop_index("ix_material_drawings_material_id", table_name="material_drawings")
    op.drop_table("material_drawings")
