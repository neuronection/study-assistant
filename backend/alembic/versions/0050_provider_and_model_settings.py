"""provider locality/country + per-model generation settings

Revision ID: 0050_provider_and_model_settings
Revises: 0049_av_metadata
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0050_provider_and_model_settings"
down_revision: str | None = "0049_av_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("is_local", sa.Boolean(), nullable=True))
    op.add_column("providers", sa.Column("country", sa.String(80), nullable=True))
    op.add_column("models", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("models", sa.Column("max_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("models", "max_tokens")
    op.drop_column("models", "temperature")
    op.drop_column("providers", "country")
    op.drop_column("providers", "is_local")
