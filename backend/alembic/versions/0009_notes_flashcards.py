"""phase 6: notes, drawings, flashcards, fsrs scheduling

Revision ID: 0009_notes_flashcards
Revises: 0008_quiz_help
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_notes_flashcards"
down_revision: str | None = "0008_quiz_help"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("owner_type", sa.String(length=30), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_notes_profile_id"), ["profile_id"], unique=False)
        batch_op.create_index("ix_notes_owner", ["owner_type", "owner_id"], unique=False)
    op.create_table(
        "note_drawings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("strokes", sa.JSON(), nullable=False),
        sa.Column("png_sha", sa.String(length=64), nullable=True),
        sa.Column("ocr_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_blocks", sa.JSON(), nullable=True),
        sa.Column("ocr_markdown", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"]),
        sa.ForeignKeyConstraint(["png_sha"], ["blobs.sha256"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("note_drawings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_note_drawings_note_id"), ["note_id"], unique=False
        )
    op.create_table(
        "flashcards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("section_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("front", sa.JSON(), nullable=False),
        sa.Column("back", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_ref", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("flashcards", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_flashcards_profile_id"), ["profile_id"], unique=False)
    op.create_table(
        "fsrs_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lapses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["card_id"], ["flashcards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("fsrs_states", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_fsrs_states_card_id"), ["card_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_fsrs_states_due_at"), ["due_at"], unique=False)
    op.create_table(
        "review_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("interval_days", sa.Float(), nullable=False),
        sa.Column("elapsed_days", sa.Float(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["flashcards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("review_log", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_review_log_card_id"), ["card_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("review_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_review_log_card_id"))
    op.drop_table("review_log")
    with op.batch_alter_table("fsrs_states", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_fsrs_states_due_at"))
        batch_op.drop_index(batch_op.f("ix_fsrs_states_card_id"))
    op.drop_table("fsrs_states")
    with op.batch_alter_table("flashcards", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_flashcards_profile_id"))
    op.drop_table("flashcards")
    with op.batch_alter_table("note_drawings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_note_drawings_note_id"))
    op.drop_table("note_drawings")
    with op.batch_alter_table("notes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notes_owner"))
        batch_op.drop_index(batch_op.f("ix_notes_profile_id"))
    op.drop_table("notes")
