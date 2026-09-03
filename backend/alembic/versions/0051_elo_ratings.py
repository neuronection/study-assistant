"""item-level Elo ratings + per-cell student ratings

Revision ID: 0051_elo_ratings
Revises: 0050_provider_and_model_settings
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0051_elo_ratings"
down_revision: str | None = "0050_provider_and_model_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("item_stats", sa.Column("rating", sa.Float(), nullable=True))
    op.add_column(
        "item_stats", sa.Column("rating_count", sa.Integer(), nullable=True)
    )
    op.create_table(
        "concept_skill_ratings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("skill", sa.String(length=20), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=True),
    )
    op.create_index(
        "uq_concept_skill_ratings",
        "concept_skill_ratings",
        ["profile_id", "concept", "skill"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_concept_skill_ratings", table_name="concept_skill_ratings")
    op.drop_table("concept_skill_ratings")
    op.drop_column("item_stats", "rating_count")
    op.drop_column("item_stats", "rating")
