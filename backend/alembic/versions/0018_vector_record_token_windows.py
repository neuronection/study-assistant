"""Token-window records coexist per source chunk (plan 52 T5b2).

A v2 space embeds token windows. One source ``chunks`` row may therefore own
several ``vector_records`` (one per window), keyed by its window index. The
legacy v1 space keeps one record per chunk because every chunk has exactly
one window (``chunk_index=0``), so the widened constraints leave every
existing row valid.

Both unique keys gain ``chunk_id``/``chunk_index``:
``(document, view, chunk_id, chunk_index)`` and
``(space, chunk_id, chunk_index)``. No data is rewritten; a downgrade is only
safe while no v2 space has written more than one window per chunk, which is
exactly the pre-v2 state.

Revision ID: 0018_vector_record_token_windows
Revises: 0017_vector_token_schema
Create Date: 2026-11-05
"""

from alembic import op

revision = "0018_vector_record_token_windows"
down_revision = "0017_vector_token_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("vector_records") as batch:
        batch.drop_constraint(
            "uq_vector_records_document_view_chunk", type_="unique"
        )
        batch.drop_constraint("uq_vector_records_space_chunk", type_="unique")
        batch.create_unique_constraint(
            "uq_vector_records_document_view_chunk",
            ["document_id", "view", "chunk_id", "chunk_index"],
        )
        batch.create_unique_constraint(
            "uq_vector_records_space_chunk",
            ["space_id", "chunk_id", "chunk_index"],
        )


def downgrade() -> None:
    with op.batch_alter_table("vector_records") as batch:
        batch.drop_constraint(
            "uq_vector_records_document_view_chunk", type_="unique"
        )
        batch.drop_constraint("uq_vector_records_space_chunk", type_="unique")
        batch.create_unique_constraint(
            "uq_vector_records_document_view_chunk",
            ["document_id", "view", "chunk_index"],
        )
        batch.create_unique_constraint(
            "uq_vector_records_space_chunk",
            ["space_id", "chunk_id"],
        )
