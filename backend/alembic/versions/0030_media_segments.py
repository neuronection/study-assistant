"""Media segments for transcript timelines (plan 90-C first cut).

Ordered transcript rows for an existing audio/video material. The first cut
seeds one full-duration segment from the extraction when no timestamped
transcript exists; the player and click-to-seek work against the shared shape.

Revision ID: 0030_media_segments
Revises: 0029_artifacts
Create Date: 2026-11-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0030_media_segments"
down_revision = "0029_artifacts"
branch_labels = None
depends_on = None

SOURCES = ("stt", "import", "manual")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    op.create_table(
        "media_segments",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("speaker", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("order_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.CheckConstraint(f"source IN ({_values(SOURCES)})", name="source_allowed"),
    )
    op.create_index("ix_media_segments_profile_id", "media_segments", ["profile_id"])
    op.create_index(
        "ix_media_segments_profile_material_order",
        "media_segments",
        ["profile_id", "material_id", "order_idx"],
    )
    op.create_index(
        "ix_media_segments_material_order", "media_segments", ["material_id", "order_idx"]
    )


def downgrade() -> None:
    op.drop_index("ix_media_segments_material_order", table_name="media_segments")
    op.drop_index("ix_media_segments_profile_material_order", table_name="media_segments")
    op.drop_index("ix_media_segments_profile_id", table_name="media_segments")
    op.drop_table("media_segments")
