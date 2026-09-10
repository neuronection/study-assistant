"""drawing ocr job pointer — background transcription state for drawings

Revision ID: 0047_drawing_ocr_jobs
Revises: 0046_drawing_view_box
Create Date: 2026-08-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0047_drawing_ocr_jobs"
down_revision: str | None = "0046_drawing_view_box"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "note_drawings", sa.Column("ocr_job_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "material_drawings", sa.Column("ocr_job_id", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("material_drawings", "ocr_job_id")
    op.drop_column("note_drawings", "ocr_job_id")
