"""Document anchors — addressable highlights (plan 90-B).

One model for every region the product will need: extraction text ranges now,
PDF quads/image regions/time ranges/transcript spans as their consumers land.
A text highlight stores the extraction version it was created against plus the
normalized quote, offsets and occurrence; when the extraction changes,
``reanchor_material`` re-locates the quote and rewrites the offsets, or marks
the anchor ``orphaned_at`` (honest, never silent loss).

Downgrade drops the table. Anchors are user marks, not derived content; the
extraction and material cascade rules are declared on the row.

Revision ID: 0021_document_anchors
Revises: 0020_capture_staging
Create Date: 2026-11-10
"""

import sqlalchemy as sa

from alembic import op

revision = "0021_document_anchors"
down_revision = "0020_capture_staging"
branch_labels = None
depends_on = None

ANCHOR_KINDS = (
    "text_range",
    "pdf_quad",
    "image_region",
    "time_range",
    "transcript_span",
    "card_ref",
)
ANCHOR_SOURCES = ("user", "ai", "import")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    op.create_table(
        "document_anchors",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("anchor_kind", sa.String(length=20), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "color", sa.String(length=20), nullable=False, server_default="yellow"
        ),
        sa.Column("note_md", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("orphaned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            f"anchor_kind IN ({_values(ANCHOR_KINDS)})", name="anchor_kind_allowed"
        ),
        sa.CheckConstraint(
            f"source IN ({_values(ANCHOR_SOURCES)})", name="source_allowed"
        ),
    )
    op.create_index(
        "ix_document_anchors_profile_id", "document_anchors", ["profile_id"]
    )
    op.create_index(
        "ix_document_anchors_material_id", "document_anchors", ["material_id"]
    )
    op.create_index(
        "ix_document_anchors_material_page",
        "document_anchors",
        ["material_id", "page"],
    )
    op.create_index(
        "ix_document_anchors_profile_created",
        "document_anchors",
        ["profile_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_anchors_profile_created", table_name="document_anchors"
    )
    op.drop_index("ix_document_anchors_material_page", table_name="document_anchors")
    op.drop_index("ix_document_anchors_material_id", table_name="document_anchors")
    op.drop_index("ix_document_anchors_profile_id", table_name="document_anchors")
    op.drop_table("document_anchors")
