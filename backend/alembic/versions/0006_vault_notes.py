"""markdown-vault preset: source preset, note file provenance, note links

Plan 85 D (ADR-213). A vault is the existing linked-folder machinery with a
`preset` marker: `.md` files become notes (not materials), so notes gain the
same external-file provenance materials already carry, and `[[wikilinks]]`
become a queryable edge table. Two-way sync stays a non-goal — the columns are
read provenance plus export state, never a write-back contract.

Revision ID: 0006_vault_notes
Revises: 0005_plan_item_external_uid
Create Date: 2026-10-22
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_vault_notes"
down_revision = "0005_plan_item_external_uid"
branch_labels = None
depends_on = None

PRESETS = ("folder", "vault")


def _recreate_mode() -> str:
    """SQLite copies the table; PostgreSQL alters it in place.

    A PostgreSQL ``recreate="always"`` copy drops the primary key and fails
    while dependent foreign keys still reference it.
    """
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    with op.batch_alter_table("material_sources", recreate=_recreate_mode()) as batch:
        batch.add_column(
            sa.Column("preset", sa.String(20), nullable=False, server_default="folder")
        )
        values = ", ".join(f"'{preset}'" for preset in PRESETS)
        batch.create_check_constraint("preset_allowed", f"preset IN ({values})")

    with op.batch_alter_table("notes", recreate=_recreate_mode()) as batch:
        batch.add_column(
            sa.Column(
                "source_id",
                sa.Uuid(as_uuid=False),
                sa.ForeignKey("material_sources.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("external_path", sa.String(1000), nullable=True))
        batch.add_column(sa.Column("file_mtime", sa.Float(), nullable=True))
        batch.add_column(sa.Column("file_size", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("content_hash", sa.String(64), nullable=True))
    op.create_index("ix_notes_source_id", "notes", ["source_id"])
    op.create_index("ix_notes_content_hash", "notes", ["content_hash"])

    op.create_table(
        "note_links",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_note_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_note_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("target", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_note_links_profile_id", "note_links", ["profile_id"])
    op.create_index(
        "uq_note_links_from_target", "note_links", ["from_note_id", "target"], unique=True
    )
    op.create_index("ix_note_links_to_note", "note_links", ["to_note_id"])


def downgrade() -> None:
    op.drop_index("ix_note_links_to_note", table_name="note_links")
    op.drop_index("uq_note_links_from_target", table_name="note_links")
    op.drop_index("ix_note_links_profile_id", table_name="note_links")
    op.drop_table("note_links")
    op.drop_index("ix_notes_content_hash", table_name="notes")
    op.drop_index("ix_notes_source_id", table_name="notes")
    with op.batch_alter_table("notes", recreate=_recreate_mode()) as batch:
        batch.drop_column("content_hash")
        batch.drop_column("file_size")
        batch.drop_column("file_mtime")
        batch.drop_column("external_path")
        batch.drop_column("source_id")

    with op.batch_alter_table("material_sources", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("preset_allowed", type_="check")
        batch.drop_column("preset")
