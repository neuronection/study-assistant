"""vector-space metadata over the legacy chunk_vecs store

Plan 50 P3a (ADR-0051 companion). Creates the portable vector metadata layer
— ``vector_spaces``, ``vector_documents``, ``vector_records`` — and backfills
study's one ``content`` space from the existing ``vec_meta`` configuration and
the ``chunk_vecs``/``chunk_vec_ids`` reverse map.

This is **not** the physical cutover. ``chunk_vecs`` stays the index table
(``vector_spaces.index_table = 'chunk_vecs'``), ``vec_meta`` still decides the
model/dim, and no ``vec_*`` table is provisioned. The metadata rows give the
read/coverage surfaces a stable address (space id/key, document kind/source
id, record view/chunk/content hash, rowid) so plan 51 Q3c can add
build/activate/retire/drop and the cutover without another table.

A model/dimension change no longer drops ``chunk_vecs`` (see
``storage/vectors.ensure_table``): it raises an explicit new-space handoff.
This migration only maps what exists.

The backfill computes the family content hash from the chunk text (a frozen
copy of the rule, since a migration must not import application code);
``StudyVectorStore.backfill_metadata`` can still repair/refresh rows
idempotently. Coverage is never written here: snapshots remain the only
coverage source.

Downgrade drops the three metadata tables; the legacy vector tables and all
snapshots/rollups are untouched.

Revision ID: 0012_vector_spaces
Revises: 0011_retrieval_run_actions
Create Date: 2026-11-04
"""

import hashlib

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op

revision = "0012_vector_spaces"
down_revision = "0011_retrieval_run_actions"
branch_labels = None
depends_on = None

CONTENT_SPACE_ID = "v1-chunk-vecs"
_SPACE_STATUS_CHECK = "status IN ('active', 'building', 'retired')"
_METRIC_CHECK = "metric IN ('cosine')"
_VIEW_CHECK = "view IN ('summary', 'requirements', 'responsibilities', 'skills', 'body')"
_INDEX_TABLE_CHECK = (
    "index_table IS NULL OR index_table = 'chunk_vecs' OR "
    "(index_table LIKE 'vec_%' AND length(index_table) = 12)"
)


def _has_table(bind: Connection, name: str) -> bool:
    if bind.dialect.name == "sqlite":
        return (
            bind.execute(
                sa.text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
                {"name": name},
            ).first()
            is not None
        )
    return bind.execute(sa.text("SELECT to_regclass(:name)"), {"name": name}).scalar() is not None


def _provider_name(bind: Connection) -> str:
    for statement in (
        "SELECT p.name FROM task_assignments ta "
        "JOIN models m ON m.id = ta.model_id "
        "JOIN providers p ON p.id = m.provider_id "
        "WHERE ta.task = 'embeddings'",
        "SELECT p.name FROM default_task_assignments ta "
        "JOIN models m ON m.id = ta.model_id "
        "JOIN providers p ON p.id = m.provider_id "
        "WHERE ta.requires = 'embeddings'",
    ):
        try:
            value = bind.execute(sa.text(statement)).scalar()
        except sa.exc.SQLAlchemyError:  # pragma: no cover - registry drift only
            value = None
        if value:
            return str(value)
    return "unassigned"


def _legacy_meta(bind: Connection) -> tuple[str | None, int | None]:
    if not _has_table(bind, "vec_meta"):
        return (None, None)
    rows = bind.execute(sa.text("SELECT key, value FROM vec_meta")).all()
    meta = {str(key): str(value) for key, value in rows}
    raw_dim = meta.get("dim")
    try:
        dim = int(raw_dim) if raw_dim is not None else None
    except ValueError:
        dim = None
    if dim is not None and dim <= 0:
        dim = None
    return (meta.get("model"), dim)


def _create_space(bind: Connection, model: str | None, dim: int) -> None:
    bind.execute(
        sa.text(
            "INSERT INTO vector_spaces "
            "(id, name, provider, model, dim, metric, normalize, "
            " chunker_version, composer_version, index_table, status, "
            " created_at, updated_at) "
            "VALUES (:id, 'content', :provider, :model, :dim, 'cosine', "
            "        :normalize, '1', '1', 'chunk_vecs', 'active', "
            "        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {
            "id": CONTENT_SPACE_ID,
            "provider": _provider_name(bind),
            "model": model or "unknown",
            "dim": dim,
            "normalize": True,
        },
    )


def _backfill_documents(bind: Connection, chunk_join: str) -> None:
    chunk_predicate = (
        "JOIN chunks c ON c.id = ids.chunk_id"
        if chunk_join == "plain"
        else "JOIN chunks c ON replace(c.id::text, '-', '') = ids.chunk_id"
    )
    bind.execute(
        sa.text(
            "INSERT INTO vector_documents "
            "(id, space_id, kind, source_id, profile_id, source_hash, "
            " schema_version, created_at, updated_at) "
            "SELECT m.id, :space_id, 'material', m.id, m.profile_id, '', 0, "
            "       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "FROM chunk_vec_ids ids "
            f"{chunk_predicate} "
            "JOIN extractions e ON e.id = c.extraction_id "
            "JOIN materials m ON m.id = e.material_id "
            "GROUP BY m.id, m.profile_id"
        ),
        {"space_id": CONTENT_SPACE_ID},
    )


def _content_hash(text: str) -> str:
    """Frozen copy of the family content-hash rule (ADR-0051 §3.2)."""
    normalized = " ".join((text or "").split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _backfill_records(bind: Connection, chunk_join: str) -> None:
    chunk_predicate = (
        "JOIN chunks c ON c.id = ids.chunk_id"
        if chunk_join == "plain"
        else "JOIN chunks c ON replace(c.id::text, '-', '') = ids.chunk_id"
    )
    rows = bind.execute(
        sa.text(
            "SELECT ids.rowid, c.id, m.id, c.text "
            "FROM chunk_vec_ids ids "
            f"{chunk_predicate} "
            "JOIN extractions e ON e.id = c.extraction_id "
            "JOIN materials m ON m.id = e.material_id "
            "ORDER BY m.id, e.created_at, c.ordinal"
        )
    ).all()
    counters: dict[object, int] = {}
    payload: list[dict[str, object]] = []
    for rowid, chunk_id, material_id, chunk_text in rows:
        chunk_index = counters.get(material_id, 0)
        counters[material_id] = chunk_index + 1
        payload.append(
            {
                "id": chunk_id,
                "document_id": material_id,
                "space_id": CONTENT_SPACE_ID,
                "chunk_index": chunk_index,
                "rowid": rowid,
                "content_hash": _content_hash(str(chunk_text or "")),
            }
        )
    statement = sa.text(
        "INSERT INTO vector_records "
        "(id, document_id, space_id, view, chunk_index, rowid, content_hash, "
        " embedding, created_at) "
        "VALUES (:id, :document_id, :space_id, 'body', :chunk_index, :rowid, "
        "        :content_hash, NULL, CURRENT_TIMESTAMP)"
    )
    for start in range(0, len(payload), 500):
        bind.execute(statement, payload[start : start + 500])


def _create_tables() -> None:
    op.create_table(
        "vector_spaces",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=10), nullable=False, server_default="cosine"),
        sa.Column("normalize", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("query_prefix", sa.String(length=80), nullable=True),
        sa.Column("document_prefix", sa.String(length=80), nullable=True),
        sa.Column("chunker_version", sa.String(length=20), nullable=False, server_default="1"),
        sa.Column("composer_version", sa.String(length=20), nullable=False, server_default="1"),
        sa.Column("index_table", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="active"),
        sa.Column("backfill_done", sa.Integer(), nullable=True),
        sa.Column("backfill_total", sa.Integer(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_SPACE_STATUS_CHECK, name="status_allowed"),
        sa.CheckConstraint(_METRIC_CHECK, name="metric_allowed"),
        sa.CheckConstraint("dim > 0", name="dim_positive"),
        sa.CheckConstraint(_INDEX_TABLE_CHECK, name="index_table_shape"),
        sa.UniqueConstraint("index_table", name="uq_vector_spaces_index_table"),
    )
    op.create_index("ix_vector_spaces_name", "vector_spaces", ["name"])
    op.create_index(
        "uq_vector_spaces_name_active",
        "vector_spaces",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "vector_documents",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("space_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["space_id"], ["vector_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("space_id", "kind", "source_id", name="uq_vector_documents_source"),
    )
    op.create_index("ix_vector_documents_space_id", "vector_documents", ["space_id"])
    op.create_index("ix_vector_documents_profile_id", "vector_documents", ["profile_id"])
    op.create_index(
        "ix_vector_documents_space_profile",
        "vector_documents",
        ["space_id", "profile_id"],
    )
    op.create_index("ix_vector_documents_space_kind", "vector_documents", ["space_id", "kind"])

    op.create_table(
        "vector_records",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("document_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("space_id", sa.String(length=80), nullable=False),
        sa.Column("view", sa.String(length=32), nullable=False, server_default="body"),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rowid", sa.BigInteger(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_VIEW_CHECK, name="view_allowed"),
        sa.CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        sa.CheckConstraint(
            "char_start IS NULL OR char_end IS NULL OR char_end >= char_start",
            name="char_range_ordered",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["vector_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["space_id"], ["vector_spaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("rowid", name="uq_vector_records_rowid"),
        sa.UniqueConstraint(
            "document_id", "view", "chunk_index", name="uq_vector_records_document_view_chunk"
        ),
    )
    op.create_index("ix_vector_records_document_id", "vector_records", ["document_id"])
    op.create_index("ix_vector_records_space_id", "vector_records", ["space_id"])
    op.create_index("ix_vector_records_space_view", "vector_records", ["space_id", "view"])


def upgrade() -> None:
    _create_tables()
    bind = op.get_bind()
    model, dim = _legacy_meta(bind)
    if dim is None:
        return
    _create_space(bind, model, dim)
    if not _has_table(bind, "chunk_vec_ids"):
        return
    chunk_join = "plain" if bind.dialect.name == "sqlite" else "cast"
    _backfill_documents(bind, chunk_join)
    _backfill_records(bind, chunk_join)


def downgrade() -> None:
    op.drop_index("ix_vector_records_space_view", table_name="vector_records")
    op.drop_index("ix_vector_records_space_id", table_name="vector_records")
    op.drop_index("ix_vector_records_document_id", table_name="vector_records")
    op.drop_table("vector_records")

    op.drop_index("ix_vector_documents_space_kind", table_name="vector_documents")
    op.drop_index("ix_vector_documents_space_profile", table_name="vector_documents")
    op.drop_index("ix_vector_documents_profile_id", table_name="vector_documents")
    op.drop_index("ix_vector_documents_space_id", table_name="vector_documents")
    op.drop_table("vector_documents")

    op.drop_index("uq_vector_spaces_name_active", table_name="vector_spaces")
    op.drop_index("ix_vector_spaces_name", table_name="vector_spaces")
    op.drop_table("vector_spaces")
