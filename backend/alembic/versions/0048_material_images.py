"""embedded document images — extraction targets for converted materials

Revision ID: 0048_material_images
Revises: 0047_drawing_ocr_jobs
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0048_material_images"
down_revision: str | None = "0047_drawing_ocr_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "material_id",
            sa.Integer(),
            sa.ForeignKey("materials.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blob_sha", sa.String(), sa.ForeignKey("blobs.sha256"), nullable=True),
        sa.Column("mime", sa.String(length=120), nullable=True),
        sa.Column("ocr_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_markdown", sa.Text(), nullable=True),
        sa.Column("ocr_job_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("material_images")
