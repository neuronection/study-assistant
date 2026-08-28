"""material_fts_trigram — typo-tolerant fuzzy search index

Revision ID: 0045_material_fts_trigram
Revises: 0044_chat_branches
Create Date: 2026-08-27

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0045_material_fts_trigram"
down_revision: str | None = "0044_chat_branches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE VIRTUAL TABLE material_fts_trigram USING fts5("
        "title, markdown, description, topics, material_id UNINDEXED, "
        "tokenize='trigram')"
    )
    op.execute(
        "INSERT INTO material_fts_trigram (title, markdown, description, topics, "
        "material_id) SELECT title, markdown, description, topics, material_id "
        "FROM material_fts"
    )


def downgrade() -> None:
    op.execute("DROP TABLE material_fts_trigram")
