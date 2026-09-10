"""plan 22B: note version history (coalesced pre-write snapshots, ADR-046)

Revision ID: 0027_note_versions
Revises: 0026_exercise_kinds
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_note_versions"
down_revision: str | None = "0026_exercise_kinds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "note_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "note_id",
            sa.Integer(),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id", sa.Integer(), sa.ForeignKey("profiles.id"), nullable=False
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("cause", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
    )
    op.create_index("ix_note_versions_note_id", "note_versions", ["note_id"])
    op.create_index("ix_note_versions_profile_id", "note_versions", ["profile_id"])
    op.create_index(
        "ix_note_versions_note", "note_versions", ["note_id", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_note_versions_note", table_name="note_versions")
    op.drop_index("ix_note_versions_profile_id", table_name="note_versions")
    op.drop_index("ix_note_versions_note_id", table_name="note_versions")
    op.drop_table("note_versions")
