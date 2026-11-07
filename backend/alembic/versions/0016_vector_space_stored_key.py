"""Plan 52 T5b1 — persist the vector space's cutover identity.

Adds ``vector_spaces.space_key``: the v1
:func:`~app.storage.vector_contract.space_key` of each row's configuration,
stamped exactly once. Remap/cutover compares this stored value, never a key
recomputed across a tokenizer/chunker version boundary; without it the first
post-upgrade legacy cutover could silently skip the space remap.

The backfill pre-image is inlined (not imported from the contract) so this
migration keeps stamping the v1 key even after the application's space-key
function gains a tokenizer/chunker component in a later slice. Each row keeps
the value verbatim; the column then becomes non-null. SQLite uses batch mode
for the rebuild; PostgreSQL only sets the column not-null.

Downgrade drops the column: the stored identity is derivable from the row at
the v1 pre-image, so it is rebuildable, not audit data.

Revision ID: 0016_vector_space_stored_key
Revises: 0015_retrieval_alerts
Create Date: 2026-11-05
"""

import hashlib

import sqlalchemy as sa

from alembic import op

revision = "0016_vector_space_stored_key"
down_revision = "0015_retrieval_alerts"
branch_labels = None
depends_on = None


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").split()).lower()


def _v1_space_key(
    provider: str,
    model: str,
    dim: int,
    normalize: bool,
    query_prefix: str | None,
    document_prefix: str | None,
    chunker_version: str,
    composer_version: str,
) -> str:
    """Frozen copy of the contract's v1 eight-field pre-image."""
    parts = (
        _normalize_text(provider),
        _normalize_text(model),
        str(int(dim)),
        "1" if normalize else "0",
        _normalize_text(query_prefix or ""),
        _normalize_text(document_prefix or ""),
        _normalize_text(chunker_version),
        _normalize_text(composer_version),
    )
    canonical = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column("vector_spaces", sa.Column("space_key", sa.String(length=64), nullable=True))
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                "SELECT id, provider, model, dim, normalize, query_prefix, "
                "document_prefix, chunker_version, composer_version FROM vector_spaces"
            )
        ).mappings()
    )
    for row in rows:
        bind.execute(
            sa.text("UPDATE vector_spaces SET space_key = :space_key WHERE id = :id"),
            {
                "space_key": _v1_space_key(
                    row["provider"],
                    row["model"],
                    int(row["dim"]),
                    bool(row["normalize"]),
                    row["query_prefix"],
                    row["document_prefix"],
                    row["chunker_version"],
                    row["composer_version"],
                ),
                "id": row["id"],
            },
        )
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("vector_spaces") as batch:
            batch.alter_column("space_key", existing_type=sa.String(length=64), nullable=False)
    else:
        op.alter_column(
            "vector_spaces",
            "space_key",
            existing_type=sa.String(length=64),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("vector_spaces") as batch:
        batch.drop_column("space_key")
