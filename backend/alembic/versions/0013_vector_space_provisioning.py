"""provision the content space's physical vec_<8hex> index

Plan 51 Q3c2a (plan 50 P3). Migration ``0012_vector_spaces`` mapped the
legacy ``chunk_vecs`` store into metadata but deliberately left the physical
backend alone. This migration performs the one-time move: it provisions the
``vec_<8hex>`` table for every space still pointing at ``chunk_vecs``, copies
the legacy vectors into it, verifies the row count, and only then switches
``vector_spaces.index_table``. ``chunk_vecs`` is never dropped — it stays the
compatibility store/fallback until the explicit Q3c2b cutover.

The helpers below are a frozen copy of the runtime provisioning rule
(``storage/vector_schema.index_table_name`` / ``storage/vector_provisioning``)
because a migration must not import application code. A migration test pins
that both derive the same table name for the study content space.

Best-effort dialects: PostgreSQL is provisioned when the ``vector`` extension
is available (a web deployment without it keeps the legacy store and fails
loudly later at write time); SQLite is provisioned when ``sqlite-vec`` loads.
No data is dropped or rewritten in place: a failed copy leaves both the
metadata pointer and the legacy tables untouched.

Revision ID: 0013_vector_space_provisioning
Revises: 0012_vector_spaces
Create Date: 2026-11-04
"""

import hashlib
import re
import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op

revision = "0013_vector_space_provisioning"
down_revision = "0012_vector_spaces"
branch_labels = None
depends_on = None

LEGACY_INDEX_TABLE = "chunk_vecs"
PGVECTOR_HNSW_MAX_DIM = 2000


def _index_table_name(space_id: str) -> str:
    try:
        return f"vec_{uuid.UUID(str(space_id)).hex[:8]}"
    except (TypeError, ValueError):
        digest = hashlib.blake2b(str(space_id).encode("utf-8"), digest_size=4).hexdigest()
        return f"vec_{digest}"


def _has_table(bind: Connection, name: str) -> bool:
    if bind.dialect.name == "postgresql":
        return (
            bind.execute(sa.text("SELECT to_regclass(:name)"), {"name": name}).scalar() is not None
        )
    return (
        bind.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": name},
        ).first()
        is not None
    )


def _rows(bind: Connection, statement: str, params: dict[str, object]) -> int:
    return int(bind.execute(sa.text(statement), params).scalar() or 0)


def _content_spaces(bind: Connection) -> list[dict[str, object]]:
    if not _has_table(bind, "vector_spaces"):
        return []
    rows = bind.execute(
        sa.text(
            "SELECT id, name, dim, index_table FROM vector_spaces "
            "WHERE index_table = :legacy ORDER BY id"
        ),
        {"legacy": LEGACY_INDEX_TABLE},
    ).mappings()
    return [dict(row) for row in rows]


def _pg_provision(bind: Connection, space: dict[str, object]) -> str | None:
    dim = int(str(space["dim"]))
    if dim < 1 or dim > PGVECTOR_HNSW_MAX_DIM:
        return None
    available = (
        bind.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).scalar()
        is not None
    )
    if not available:
        return None
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    table = _index_table_name(str(space["id"]))
    exists = bind.execute(sa.text("SELECT to_regclass(:name)"), {"name": table}).scalar()
    if exists is None:
        bind.execute(
            sa.text(
                f"CREATE TABLE {table} ("
                "record_id UUID PRIMARY KEY REFERENCES vector_records(id) ON DELETE CASCADE, "
                f"embedding vector({dim}) NOT NULL)"
            )
        )
    else:
        declared = bind.execute(
            sa.text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a "
                "WHERE a.attrelid = CAST(:table AS regclass) "
                "AND a.attname = 'embedding' AND NOT a.attisdropped"
            ),
            {"table": table},
        ).scalar()
        match = re.fullmatch(r"vector\((\d+)\)", str(declared or ""))
        if match is None or int(match.group(1)) != dim:
            raise RuntimeError(
                f"existing index {table!r} does not match vector({dim}) ({declared!r})"
            )
    bind.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_hnsw ON {table} "
            "USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
    )
    if not (_has_table(bind, "chunk_vecs") and _has_table(bind, "chunk_vec_ids")):
        return table
    expected = _rows(
        bind,
        "SELECT count(*) FROM chunk_vecs v "
        "JOIN chunk_vec_ids i ON i.rowid = v.rowid "
        "JOIN vector_records r ON r.rowid = i.rowid "
        "WHERE r.space_id = :space_id",
        {"space_id": str(space["id"])},
    )
    if expected:
        bind.execute(
            sa.text(
                f"INSERT INTO {table} (record_id, embedding) "
                "SELECT r.id, v.chunk_embedding FROM chunk_vecs v "
                "JOIN chunk_vec_ids i ON i.rowid = v.rowid "
                "JOIN vector_records r ON r.rowid = i.rowid "
                "WHERE r.space_id = :space_id "
                "ON CONFLICT (record_id) DO NOTHING"
            ),
            {"space_id": str(space["id"])},
        )
        actual = _rows(bind, f"SELECT count(*) FROM {table}", {})
        if actual < expected:
            raise RuntimeError(f"backfill into {table!r} copied {actual} of {expected} row(s)")
    return table


def _sqlite_load_vec(bind: Connection) -> bool:
    try:
        import sqlite_vec
    except ImportError:  # pragma: no cover - desktop extra absent
        return False
    try:
        raw = bind.connection.driver_connection
        if raw is None:
            return False
        raw.enable_load_extension(True)
        sqlite_vec.load(raw)
        bind.exec_driver_sql("SELECT vec_version()").scalar()
        return True
    except Exception:  # pragma: no cover - a load failure keeps the legacy store
        return False


def _sqlite_table_dim(bind: Connection, table: str) -> int | None:
    sql = bind.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": table},
    ).scalar()
    if sql is None:
        return None
    match = re.search(r"float\[(\d+)\]", str(sql))
    if match is None:
        raise RuntimeError(f"existing index {table!r} has no float[dim] embedding column")
    return int(match.group(1))


def _sqlite_provision(bind: Connection, space: dict[str, object]) -> str | None:
    if not _sqlite_load_vec(bind):
        return None
    dim = int(str(space["dim"]))
    if dim < 1:
        return None
    table = _index_table_name(str(space["id"]))
    existing_dim = _sqlite_table_dim(bind, table)
    if existing_dim is not None and existing_dim != dim:
        raise RuntimeError(f"existing index {table!r} is float[{existing_dim}], need float[{dim}]")
    bind.execute(
        sa.text(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0("
            "record_rowid INTEGER PRIMARY KEY, "
            f"embedding float[{dim}] distance_metric=cosine)"
        )
    )
    if not (_has_table(bind, "chunk_vecs") and _has_table(bind, "chunk_vec_ids")):
        return table
    rows = bind.execute(
        sa.text(
            "SELECT i.rowid AS rowid, v.chunk_embedding AS embedding "
            "FROM chunk_vecs v "
            "JOIN chunk_vec_ids i ON i.rowid = v.rowid "
            "JOIN vector_records r ON r.rowid = i.rowid "
            "WHERE r.space_id = :space_id"
        ),
        {"space_id": str(space["id"])},
    ).all()
    if rows:
        existing = {
            int(value)
            for (value,) in bind.execute(sa.text(f"SELECT record_rowid FROM {table}"))
        }
        payload = [
            {"rowid": int(row.rowid), "embedding": row.embedding}
            for row in rows
            if int(row.rowid) not in existing
        ]
        if payload:
            bind.execute(
                sa.text(
                    f"INSERT INTO {table} (record_rowid, embedding) "
                    "VALUES (:rowid, :embedding)"
                ),
                payload,
            )
        actual = _rows(bind, f"SELECT count(*) FROM {table}", {})
        if actual < len(rows):
            raise RuntimeError(f"backfill into {table!r} copied {actual} of {len(rows)} row(s)")
    return table


def upgrade() -> None:
    bind = op.get_bind()
    for space in _content_spaces(bind):
        if bind.dialect.name == "postgresql":
            table = _pg_provision(bind, space)
        elif bind.dialect.name == "sqlite":
            table = _sqlite_provision(bind, space)
        else:  # pragma: no cover - no other datastore supports the vector store
            table = None
        if table is None:
            continue
        bind.execute(
            sa.text("UPDATE vector_spaces SET index_table = :table WHERE id = :space_id"),
            {"table": table, "space_id": str(space["id"])},
        )


def _drop_table(bind: Connection, table: str) -> None:
    bind.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "vector_spaces"):
        return
    if bind.dialect.name == "sqlite":
        _sqlite_load_vec(bind)
    rows = bind.execute(
        sa.text(
            "SELECT id, index_table FROM vector_spaces "
            "WHERE index_table IS NOT NULL AND index_table LIKE 'vec_%'"
        )
    ).mappings()
    for row in list(rows):
        _drop_table(bind, str(row["index_table"]))
        bind.execute(
            sa.text("UPDATE vector_spaces SET index_table = :legacy WHERE id = :space_id"),
            {"legacy": LEGACY_INDEX_TABLE, "space_id": str(row["id"])},
        )
