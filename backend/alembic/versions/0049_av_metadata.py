"""audio/video metadata on materials — duration and bitrate for transcribe pre-flight

Revision ID: 0049_av_metadata
Revises: 0048_material_images
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0049_av_metadata"
down_revision: str | None = "0048_material_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("materials", sa.Column("duration_sec", sa.Float(), nullable=True))
    op.add_column("materials", sa.Column("bitrate_kbps", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("materials", "bitrate_kbps")
    op.drop_column("materials", "duration_sec")
