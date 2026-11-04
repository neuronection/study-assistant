"""Physical vector-store provisioning for one embedding space (plan 50 §3.4,
plan 51 Q3c2a).

This is the only seam allowed to issue ``CREATE TABLE`` for a vector index.
It never runs on a read path: the Alembic backfill or a write/job path calls
:func:`provision_space` off the request. Study's sessions are caller-owned
(the store shares the ingest/transaction), so provisioning flushes but never
commits on its own; the caller commits the DDL and the metadata write
together. That is what keeps ``vector_spaces.index_table`` from ever naming a
table that does not exist (or the reverse).

PostgreSQL is a hard prerequisite: a web deployment that enables semantic
search must have the ``vector`` extension, and provisioning fails loudly when
it cannot be created. SQLite is best-effort: without a loadable ``sqlite-vec``
the space is not moved onto a ``vec0`` table and the legacy physical store
stays the honest fallback — the factory never pretends an ANN index exists.

The physical table addresses records by ``vector_records.id`` (pgvector) or
by the study rowid rule (``vector_records.rowid`` for sqlite-vec). The
metadata row is the rowid map; no second mapping table is invented.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..domain.models import VectorSpace as VectorSpaceRow
from .vector_contract import BACKEND_LINEAR, BACKEND_PGVECTOR, BACKEND_SQLITE_VEC
from .vector_schema import index_table_name, validate_index_table

logger = logging.getLogger(__name__)

# pgvector's HNSW operator classes are defined for ``vector`` up to 2000
# dimensions; the contract's capability ceiling is 3072, so provisioning must
# refuse the un-indexable middle instead of failing cryptically.
PGVECTOR_HNSW_MAX_DIM = 2000


class VectorProvisioningError(RuntimeError):
    """Provisioning could not create a usable physical store."""


class VectorDimensionMismatch(VectorProvisioningError):
    """An existing physical table has a different dimension than the space."""


class VectorExtensionUnavailable(VectorProvisioningError):
    """The dialect's vector extension/driver is not available."""


class VectorSpaceRowMissing(VectorProvisioningError):
    """The requested space has no persisted metadata row."""


@dataclass(frozen=True)
class SpaceProvision:
    """The result of one idempotent provisioning call."""

    space_id: str
    name: str
    backend: str
    index_table: str | None
    dim: int
    created: bool
    detail: str


@dataclass(frozen=True)
class SpaceStatus:
    """The physical side of one space, for ops/status reads."""

    space_id: str
    name: str
    backend: str
    index_table: str | None
    dim: int
    table_exists: bool
    table_dim: int | None
    index_present: bool
    row_count: int
    detail: str


def _row_for(session: Session, space: VectorSpaceRow | str) -> VectorSpaceRow:
    if isinstance(space, VectorSpaceRow):
        row = session.get(VectorSpaceRow, space.id)
    else:
        row = session.get(VectorSpaceRow, str(space))
    if row is None:
        raise VectorSpaceRowMissing(f"vector space {space!r} has no persisted row")
    return row


def _declared_table(row: VectorSpaceRow) -> str:
    if row.index_table is not None and row.index_table != "chunk_vecs":
        validate_index_table(row.index_table)
        expected = index_table_name(row.id)
        if row.index_table != expected:
            raise VectorProvisioningError(
                f"space {row.name!r} declares {row.index_table!r}, but its id derives {expected!r}"
            )
        return row.index_table
    return index_table_name(row.id)


def _engine(session: Session) -> Engine:
    bind = session.get_bind()
    if isinstance(bind, Connection):
        return bind.engine
    return bind


def _sqlite_load_vec(session: Session) -> bool:
    try:
        import sqlite_vec
    except ImportError:  # pragma: no cover - sqlite-vec is a desktop extra
        return False
    try:
        raw = session.connection().connection.driver_connection
        if raw is None:
            return False
        raw.enable_load_extension(True)
        sqlite_vec.load(raw)
        session.connection().exec_driver_sql("SELECT vec_version()").scalar()
        return True
    except Exception:
        logger.warning("sqlite-vec could not be loaded", exc_info=True)
        return False


def _sqlite_table_dim(session: Session, table: str) -> int | None:
    sql = session.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": table},
    ).scalar()
    if sql is None:
        return None
    match = re.search(r"float\[(\d+)\]", str(sql))
    if match is None:
        raise VectorDimensionMismatch(
            f"existing index {table!r} has no float[dim] embedding column"
        )
    return int(match.group(1))


def _pg_extension_version(session: Session) -> str | None:
    return session.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()


def _create_pg_extension(session: Session) -> str:
    engine = _engine(session)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except SQLAlchemyError as exc:
        raise VectorExtensionUnavailable(
            "pgvector is not installed and CREATE EXTENSION vector failed — "
            "semantic search is a hard prerequisite on PostgreSQL"
        ) from exc
    version = _pg_extension_version(session)
    if version is None:  # pragma: no cover - defensive after a successful create
        raise VectorExtensionUnavailable("pgvector could not be installed")
    return str(version)


def _pg_provision(session: Session, row: VectorSpaceRow) -> SpaceProvision:
    if row.dim > PGVECTOR_HNSW_MAX_DIM:
        raise VectorProvisioningError(
            f"space {row.name!r} needs vector({row.dim}), but pgvector's HNSW index "
            f"supports at most {PGVECTOR_HNSW_MAX_DIM} dimensions"
        )
    table = _declared_table(row)
    version = _pg_extension_version(session) or _create_pg_extension(session)
    exists = (
        session.execute(text("SELECT to_regclass(CAST(:table AS text))"), {"table": table}).scalar()
        is not None
    )
    if exists:
        declared = session.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a "
                "WHERE a.attrelid = CAST(:table AS regclass) "
                "AND a.attname = 'embedding' AND NOT a.attisdropped"
            ),
            {"table": table},
        ).scalar()
        match = re.fullmatch(r"vector\((\d+)\)", str(declared or ""))
        if match is None:
            raise VectorDimensionMismatch(
                f"existing index {table!r} has no vector embedding column ({declared!r})"
            )
        if int(match.group(1)) != row.dim:
            raise VectorDimensionMismatch(
                f"existing index {table!r} is vector({match.group(1)}), "
                f"space {row.name!r} needs vector({row.dim})"
            )
    else:
        session.execute(
            text(
                f"CREATE TABLE {table} ("
                "record_id UUID PRIMARY KEY REFERENCES vector_records(id) ON DELETE CASCADE, "
                f"embedding vector({row.dim}) NOT NULL)"
            )
        )
    session.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_hnsw ON {table} "
            "USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
    )
    row.index_table = table
    session.flush()
    return SpaceProvision(
        space_id=str(row.id),
        name=str(row.name),
        backend=BACKEND_PGVECTOR,
        index_table=table,
        dim=int(row.dim),
        created=not exists,
        detail=f"pgvector {version}: {table} vector({row.dim}) + HNSW cosine",
    )


def _sqlite_provision(session: Session, row: VectorSpaceRow) -> SpaceProvision:
    if not _sqlite_load_vec(session):
        raise VectorExtensionUnavailable(
            "sqlite-vec is not loadable; the space keeps its existing physical store"
        )
    table = _declared_table(row)
    existing_dim = _sqlite_table_dim(session, table)
    if existing_dim is not None and existing_dim != row.dim:
        raise VectorDimensionMismatch(
            f"existing index {table!r} is float[{existing_dim}], "
            f"space {row.name!r} needs float[{row.dim}]"
        )
    session.execute(
        text(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0("
            "record_rowid INTEGER PRIMARY KEY, "
            f"embedding float[{row.dim}] distance_metric=cosine)"
        )
    )
    row.index_table = table
    session.flush()
    version = session.connection().exec_driver_sql("SELECT vec_version()").scalar()
    return SpaceProvision(
        space_id=str(row.id),
        name=str(row.name),
        backend=BACKEND_SQLITE_VEC,
        index_table=table,
        dim=int(row.dim),
        created=existing_dim is None,
        detail=f"sqlite-vec {version}: {table} float[{row.dim}] cosine",
    )


def provision_space(
    session: Session,
    space: VectorSpaceRow | str,
    *,
    backend: str | None = None,
) -> SpaceProvision:
    """Create/verify one space's physical index, idempotently.

    ``backend`` defaults to the dialect's engine (pgvector on PostgreSQL,
    sqlite-vec on SQLite). The ``vector_spaces.index_table`` write shares the
    caller's transaction, so metadata and DDL can never disagree.
    """
    row = _row_for(session, space)
    dialect = session.get_bind().dialect.name
    if backend == BACKEND_LINEAR:
        raise VectorProvisioningError(
            "linear spaces own no physical index table; nothing to provision"
        )
    if backend == BACKEND_PGVECTOR:
        if dialect != "postgresql":
            raise VectorProvisioningError("pgvector provisioning needs PostgreSQL")
        return _pg_provision(session, row)
    if backend == BACKEND_SQLITE_VEC:
        if dialect != "sqlite":
            raise VectorProvisioningError("sqlite-vec provisioning needs SQLite")
        return _sqlite_provision(session, row)
    if dialect == "postgresql":
        return _pg_provision(session, row)
    if dialect == "sqlite":
        return _sqlite_provision(session, row)
    raise VectorProvisioningError(f"unsupported database dialect: {dialect}")


def legacy_backfill_count(session: Session, space_id: str) -> int:
    """Rows the legacy ``chunk_vecs`` store can contribute to this space."""
    if not (_table_exists(session, "chunk_vecs") and _table_exists(session, "chunk_vec_ids")):
        return 0
    value = session.execute(
        text(
            "SELECT count(*) FROM chunk_vecs v "
            "JOIN chunk_vec_ids i ON i.rowid = v.rowid "
            "JOIN vector_records r ON r.rowid = i.rowid "
            "WHERE r.space_id = :space_id"
        ),
        {"space_id": space_id},
    ).scalar()
    return int(value or 0)


def backfill_from_legacy(
    session: Session,
    space: VectorSpaceRow | str,
    *,
    verify: bool = True,
) -> int:
    """Copy the legacy ``chunk_vecs`` rows into the provisioned index.

    The legacy table is never read by a request path after this: it stays as
    the compatibility fallback (and is still dual-written while the space is
    ``active``). The copy is idempotent (upsert/ignore by record identity) and
    verifies its own row count before the caller commits the index_table
    switch.
    """
    row = _row_for(session, space)
    if row.index_table is None or row.index_table == "chunk_vecs":
        raise VectorProvisioningError(f"space {row.name!r} has no provisioned index to backfill")
    table = validate_index_table(row.index_table)
    expected = legacy_backfill_count(session, str(row.id))
    if expected == 0:
        if _table_exists(session, "chunk_vecs") and _table_rows(session, "chunk_vecs") > 0:
            raise VectorProvisioningError(
                "the legacy store has vectors but no metadata rows for this space; "
                "run the metadata backfill before switching index_table"
            )
        return 0
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        session.execute(
            text(
                f"INSERT INTO {table} (record_id, embedding) "
                "SELECT r.id, v.chunk_embedding FROM chunk_vecs v "
                "JOIN chunk_vec_ids i ON i.rowid = v.rowid "
                "JOIN vector_records r ON r.rowid = i.rowid "
                "WHERE r.space_id = :space_id "
                "ON CONFLICT (record_id) DO NOTHING"
            ),
            {"space_id": str(row.id)},
        )
    elif dialect == "sqlite":
        rows = session.execute(
            text(
                "SELECT i.rowid AS rowid, v.chunk_embedding AS embedding "
                "FROM chunk_vecs v "
                "JOIN chunk_vec_ids i ON i.rowid = v.rowid "
                "JOIN vector_records r ON r.rowid = i.rowid "
                "WHERE r.space_id = :space_id"
            ),
            {"space_id": str(row.id)},
        ).all()
        if rows:
            existing = {
                int(value)
                for (value,) in session.execute(text(f"SELECT record_rowid FROM {table}"))
            }
            payload = [
                {"rowid": int(item.rowid), "embedding": item.embedding}
                for item in rows
                if int(item.rowid) not in existing
            ]
            if payload:
                session.execute(
                    text(
                        f"INSERT INTO {table} (record_rowid, embedding) "
                        "VALUES (:rowid, :embedding)"
                    ),
                    payload,
                )
    else:  # pragma: no cover - provision_space already refuses unknown dialects
        raise VectorProvisioningError(f"unsupported database dialect: {dialect}")
    if verify:
        actual = int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)
        if actual < expected:
            raise VectorProvisioningError(
                f"legacy backfill into {table!r} copied {actual} of {expected} row(s); "
                "the legacy store stays the active fallback"
            )
    return expected


def space_status(
    session: Session,
    space: VectorSpaceRow | str,
) -> SpaceStatus:
    """Report the physical side of a space without creating anything."""
    row = _row_for(session, space)
    dialect = session.get_bind().dialect.name
    table = row.index_table
    if table is not None and table != "chunk_vecs":
        validate_index_table(table)
    backend = BACKEND_LINEAR
    exists = False
    table_dim: int | None = None
    index_present = False
    row_count = 0
    detail = "linear fallback"
    if table == "chunk_vecs":
        backend = BACKEND_PGVECTOR if dialect == "postgresql" else BACKEND_SQLITE_VEC
        exists = _table_exists(session, table)
        row_count = _table_rows(session, table) if exists else 0
        detail = (
            f"legacy {table} store (no provisioned vec_ table); {row_count} row(s)"
            if exists
            else f"legacy {table} store is missing"
        )
    elif table is not None and dialect == "postgresql":
        backend = BACKEND_PGVECTOR
        present = (
            session.execute(
                text("SELECT to_regclass(CAST(:table AS text))"), {"table": table}
            ).scalar()
            is not None
        )
        declared = (
            session.execute(
                text(
                    "SELECT format_type(a.atttypid, a.atttypmod) "
                    "FROM pg_attribute a "
                    "WHERE a.attrelid = CAST(:table AS regclass) "
                    "AND a.attname = 'embedding' AND NOT a.attisdropped"
                ),
                {"table": table},
            ).scalar()
            if present
            else None
        )
        exists = declared is not None
        if declared is not None:
            match = re.fullmatch(r"vector\((\d+)\)", str(declared))
            table_dim = int(match.group(1)) if match else None
            row_count = _table_rows(session, table)
            index_present = (
                session.execute(
                    text(
                        "SELECT 1 FROM pg_indexes WHERE tablename = :table AND indexname = :index"
                    ),
                    {"table": table, "index": f"ix_{table}_hnsw"},
                ).scalar()
                is not None
            )
            detail = f"pgvector: {declared}, {row_count} row(s)"
        else:
            detail = f"pgvector: index table {table!r} is missing"
    elif table is not None and dialect == "sqlite":
        backend = BACKEND_SQLITE_VEC
        table_dim = _sqlite_table_dim(session, table)
        exists = table_dim is not None
        if exists:
            row_count = _table_rows(session, table)
            index_present = True
            detail = f"sqlite-vec: float[{table_dim}], {row_count} row(s)"
    return SpaceStatus(
        space_id=str(row.id),
        name=str(row.name),
        backend=backend,
        index_table=table,
        dim=int(row.dim),
        table_exists=exists,
        table_dim=table_dim,
        index_present=index_present,
        row_count=row_count,
        detail=detail,
    )


def drop_space_index(session: Session, space: VectorSpaceRow | str) -> str | None:
    """Drop one retired space's physical index (explicit drop action only).

    The active space is refused by the lifecycle caller, never here. The
    legacy ``content`` space also drops the compatibility ``chunk_vecs`` store
    and its reverse map — that is the explicit retirement of the legacy
    fallback, not an implicit cleanup.
    """
    row = _row_for(session, space)
    table = row.index_table
    if table is not None and table != "chunk_vecs":
        validate_index_table(table)
    dialect = session.get_bind().dialect.name
    dropped: str | None = table
    if table is not None:
        suffix = " CASCADE" if dialect == "postgresql" else ""
        session.execute(text(f"DROP TABLE IF EXISTS {table}{suffix}"))
    if str(row.id) == "legacy-chunk-vecs":
        for legacy in ("chunk_vecs", "chunk_vec_ids"):
            if _table_exists(session, legacy):
                session.execute(text(f"DROP TABLE IF EXISTS {legacy}"))
        dropped = "chunk_vecs" if table in (None, "chunk_vecs") else dropped
    session.flush()
    return dropped


def _table_exists(session: Session, table: str) -> bool:
    if session.get_bind().dialect.name == "postgresql":
        return (
            session.execute(text("SELECT to_regclass(:name)"), {"name": table}).scalar() is not None
        )
    return (
        session.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table},
        ).first()
        is not None
    )


def _table_rows(session: Session, table: str) -> int:
    return int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)


__all__ = [
    "PGVECTOR_HNSW_MAX_DIM",
    "SpaceProvision",
    "SpaceStatus",
    "VectorDimensionMismatch",
    "VectorExtensionUnavailable",
    "VectorProvisioningError",
    "VectorSpaceRowMissing",
    "backfill_from_legacy",
    "drop_space_index",
    "legacy_backfill_count",
    "provision_space",
    "space_status",
]
