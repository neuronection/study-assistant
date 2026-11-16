"""Problem Desk solve history (plan 97-F).

A solve is profile-scoped and course-less: the typed/pasted/photo input, the
closed intent, the verified result document and an optional saved note. The
result is a typed ``SolveResult`` document; steps never live as unverified
free text in separate rows.

Revision ID: 0027_solve_entries
Revises: 0026_exam_papers
Create Date: 2026-11-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0027_solve_entries"
down_revision = "0026_exam_papers"
branch_labels = None
depends_on = None

INPUT_KINDS = ("typed", "pasted", "photo", "handwritten")
INTENTS = (
    "simplify",
    "evaluate",
    "solve",
    "differentiate",
    "integrate",
    "limit",
    "factor",
    "expand",
    "graph",
    "unsupported",
)


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    op.create_table(
        "solve_entries",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("input_kind", sa.String(length=20), nullable=False, server_default="typed"),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=20), nullable=False, server_default="unsupported"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("note_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="SET NULL"),
        sa.CheckConstraint(f"input_kind IN ({_values(INPUT_KINDS)})", name="input_kind_allowed"),
        sa.CheckConstraint(f"intent IN ({_values(INTENTS)})", name="intent_allowed"),
    )
    op.create_index("ix_solve_entries_profile_id", "solve_entries", ["profile_id"])
    op.create_index(
        "ix_solve_entries_profile_created", "solve_entries", ["profile_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_solve_entries_profile_created", table_name="solve_entries")
    op.drop_index("ix_solve_entries_profile_id", table_name="solve_entries")
    op.drop_table("solve_entries")
