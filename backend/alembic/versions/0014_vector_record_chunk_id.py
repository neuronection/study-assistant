"""stable chunk identity on vector records (plan 51 Q3c2b1)

A building space coexists with the active one, so a record id can no longer be
the chunk id (``vector_records.id`` is a global primary key). ``chunk_id`` is
the space-local source handle the search path hydrates back to a chunk; the
legacy ``content`` space keeps ``chunk_id = id``, which is exactly the
identity its rows already carried. The backfill only fills the legacy rows;
new spaces write their own records.

Downgrade drops the column and its uniqueness; the record rows stay.

Revision ID: 0014_vector_record_chunk_id
Revises: 0013_vector_space_provisioning
Create Date: 2026-11-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0014_vector_record_chunk_id"
down_revision = "0013_vector_space_provisioning"
branch_labels = None
depends_on = None

CONTENT_SPACE_ID = "legacy-chunk-vecs"


def upgrade() -> None:
    with op.batch_alter_table("vector_records") as batch:
        batch.add_column(sa.Column("chunk_id", sa.String(length=80), nullable=True))
        batch.create_index("ix_vector_records_chunk_id", ["chunk_id"])
        batch.create_unique_constraint(
            "uq_vector_records_space_chunk", ["space_id", "chunk_id"]
        )
    op.execute(
        sa.text(
            "UPDATE vector_records SET chunk_id = id "
            "WHERE space_id = :space_id AND chunk_id IS NULL"
        ).bindparams(space_id=CONTENT_SPACE_ID)
    )


def downgrade() -> None:
    with op.batch_alter_table("vector_records") as batch:
        batch.drop_constraint("uq_vector_records_space_chunk", type_="unique")
        batch.drop_index("ix_vector_records_chunk_id")
        batch.drop_column("chunk_id")
