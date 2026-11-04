import hashlib
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..ai.embeddings import serialize_vector
from ..core.ids import hex_id, uuid_str

VEC_TABLE = "chunk_vecs"
VEC_META = "vec_meta"
VEC_IDS = "chunk_vec_ids"

_ROWID_MASK = 0x7FFF_FFFF_FFFF_FFFF


class VectorSpaceChangeRequired(RuntimeError):
    """A model/dimension change needs an explicit new space, never a drop.

    Plan 50 P3 makes the active ``content`` space immutable in place: a new
    embedding model/dimension becomes a *building* space and a cutover
    (plan 51 Q3c). P3a therefore refuses the write and leaves ``chunk_vecs``
    untouched — the old vectors stay readable until the operator runs the
    explicit migration/cutover handoff.
    """

    def __init__(
        self,
        *,
        current_model: str | None,
        current_dim: int | None,
        requested_model: str,
        requested_dim: int,
        detail: str = "",
    ) -> None:
        self.current_model = current_model
        self.current_dim = current_dim
        self.requested_model = requested_model
        self.requested_dim = requested_dim
        message = (
            "the legacy vector store is configured for "
            f"model={current_model!r} dim={current_dim}, but this write needs "
            f"model={requested_model!r} dim={requested_dim}. A model/dimension "
            "change is a new vector space plus cutover (plan 50 P3 / plan 51 Q3c); "
            "chunk_vecs was left untouched"
        )
        super().__init__(f"{message}{f' ({detail})' if detail else ''}")


def rowid_for(chunk_id: str) -> int:
    """Stable 63-bit rowid for a UUID chunk id.

    `vec0`/pgvector both key vectors by an integer rowid; the chunk identity
    moved to a UUID string in plan 81 C, so the rowid is derived from the id
    and the `chunk_vec_ids` side table keeps the reverse mapping.
    """
    digest = hashlib.blake2b(hex_id(chunk_id).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") & _ROWID_MASK


def _ensure_ids_table(session: Session) -> None:
    session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {VEC_IDS} "
            "(rowid BIGINT PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE)"
        )
    )


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def _load_meta(session: Session) -> dict[str, str]:
    session.execute(
        text(f"CREATE TABLE IF NOT EXISTS {VEC_META} (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    )
    rows = session.execute(text(f"SELECT key, value FROM {VEC_META}")).mappings()
    return {row["key"]: row["value"] for row in rows}


def ensure_table(session: Session, dim: int, model: str) -> bool:
    """Create the legacy table once; never drop it on a model/dim change.

    P3a replaces the old drop-and-rebuild behaviour with an explicit
    :class:`VectorSpaceChangeRequired` handoff: the new embedding
    configuration is a separate space and a cutover, so the existing vectors
    (and their read path) survive until that runs.
    """
    meta = _load_meta(session)
    current_dim = meta.get("dim")
    current_model = meta.get("model")
    try:
        current_dim_int = int(current_dim) if current_dim is not None else None
    except ValueError:
        current_dim_int = None
    exists = table_exists(session)
    same = current_dim == str(dim) and (current_model is None or current_model == model)
    if same:
        if not exists:
            current_dim = None
        else:
            if current_model is None:
                session.execute(
                    text(
                        f"INSERT INTO {VEC_META} (key, value) VALUES ('model', :model) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                    ),
                    {"model": model},
                )
            return False
    if current_dim is not None or exists:
        raise VectorSpaceChangeRequired(
            current_model=current_model,
            current_dim=current_dim_int,
            requested_model=model,
            requested_dim=int(dim),
            detail="table exists" if exists and current_dim is None else "",
        )
    if _is_postgres(session):
        # ADR-0022 S3 twin: sqlite-vec vec0 → pgvector + HNSW (cosine).
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        session.execute(
            text(
                f"CREATE TABLE {VEC_TABLE} "
                f"(rowid BIGINT PRIMARY KEY, chunk_embedding vector({int(dim)}))"
            )
        )
        session.execute(
            text(
                f"CREATE INDEX ix_{VEC_TABLE}_embedding ON {VEC_TABLE} "
                "USING hnsw (chunk_embedding vector_cosine_ops)"
            )
        )
    else:
        session.execute(
            text(
                f"CREATE VIRTUAL TABLE {VEC_TABLE} USING vec0("
                f"chunk_embedding float[{dim}] distance_metric=cosine)"
            )
        )
    session.execute(
        text(
            f"INSERT INTO {VEC_META} (key, value) VALUES ('dim', :dim) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        ),
        {"dim": str(dim)},
    )
    session.execute(
        text(
            f"INSERT INTO {VEC_META} (key, value) VALUES ('model', :model) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        ),
        {"model": model},
    )
    return True


def store(session: Session, chunk_ids: list[str], vectors: list[list[float]], model: str) -> None:
    dim = len(vectors[0])
    ensure_table(session, dim, model)
    _ensure_ids_table(session)
    for chunk_id, vector in zip(chunk_ids, vectors, strict=True):
        rowid = rowid_for(chunk_id)
        session.execute(
            text(
                f"INSERT INTO {VEC_IDS} (rowid, chunk_id) VALUES (:rowid, :chunk_id) "
                "ON CONFLICT (rowid) DO UPDATE SET chunk_id = excluded.chunk_id"
            ),
            {"rowid": rowid, "chunk_id": hex_id(chunk_id)},
        )
        if _is_postgres(session):
            # serialize_vector emits JSON text, which pgvector parses as input.
            session.execute(
                text(
                    f"INSERT INTO {VEC_TABLE} (rowid, chunk_embedding) "
                    "VALUES (:rowid, CAST(:vec AS vector)) "
                    "ON CONFLICT (rowid) DO UPDATE "
                    "SET chunk_embedding = excluded.chunk_embedding"
                ),
                {"rowid": rowid, "vec": serialize_vector(vector)},
            )
        else:
            session.execute(
                text(
                    f"INSERT OR REPLACE INTO {VEC_TABLE} (rowid, chunk_embedding) "
                    "VALUES (:rowid, :vec)"
                ),
                {"rowid": rowid, "vec": serialize_vector(vector)},
            )


def delete_for_extraction(session: Session, chunk_ids: list[str]) -> None:
    if not chunk_ids:
        return
    if _is_postgres(session):
        exists = session.execute(text("SELECT to_regclass(:name)"), {"name": VEC_TABLE}).scalar()
    else:
        exists = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name = :name"),
            {"name": VEC_TABLE},
        ).first()
    if exists is None:
        return
    rowids = [rowid_for(chunk_id) for chunk_id in chunk_ids]
    placeholders = ",".join(str(rowid) for rowid in rowids)
    session.execute(text(f"DELETE FROM {VEC_TABLE} WHERE rowid IN ({placeholders})"))
    _ensure_ids_table(session)
    session.execute(text(f"DELETE FROM {VEC_IDS} WHERE rowid IN ({placeholders})"))


def read_meta(session: Session) -> dict[str, str]:
    """The legacy store's active configuration (``dim``/``model``).

    Read-only: unlike ``_load_meta`` this never creates ``vec_meta``, so a
    status request cannot mutate the database.
    """
    if _is_postgres(session):
        exists = session.execute(text("SELECT to_regclass(:name)"), {"name": VEC_META}).scalar()
    else:
        exists = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name = :name"),
            {"name": VEC_META},
        ).first()
    if exists is None:
        return {}
    rows = session.execute(text(f"SELECT key, value FROM {VEC_META}")).mappings()
    return {row["key"]: row["value"] for row in rows}


def table_exists(session: Session) -> bool:
    if _is_postgres(session):
        return (
            session.execute(text("SELECT to_regclass(:name)"), {"name": VEC_TABLE}).scalar()
            is not None
        )
    return (
        session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name = :name"),
            {"name": VEC_TABLE},
        ).first()
        is not None
    )


def stored_chunk_ids(session: Session) -> dict[int, str]:
    """``rowid -> chunk_id`` for every vector row that still has a mapping."""
    if not table_exists(session):
        return {}
    _ensure_ids_table(session)
    rows = session.execute(
        text(
            f"SELECT ids.rowid AS rowid, ids.chunk_id AS chunk_id "
            f"FROM {VEC_IDS} AS ids JOIN {VEC_TABLE} AS vec ON vec.rowid = ids.rowid"
        )
    ).mappings()
    return {int(row["rowid"]): uuid_str(str(row["chunk_id"])) for row in rows}


def orphan_rowids(session: Session, live_chunk_ids: set[str]) -> tuple[list[int], list[int]]:
    """Rows to sweep: ``(dangling_map, orphan_vector)``.

    ``dangling_map`` is a mapping whose chunk row no longer exists;
    ``orphan_vector`` is a vector row with no mapping at all.
    """
    if not table_exists(session):
        return ([], [])
    _ensure_ids_table(session)
    mapped = {
        int(row["rowid"]): uuid_str(str(row["chunk_id"]))
        for row in session.execute(text(f"SELECT rowid, chunk_id FROM {VEC_IDS}")).mappings()
    }
    vectors_rows = {
        int(row["rowid"])
        for row in session.execute(text(f"SELECT rowid FROM {VEC_TABLE}")).mappings()
    }
    dangling = [
        rowid
        for rowid, chunk_id in mapped.items()
        if chunk_id not in live_chunk_ids or rowid not in vectors_rows
    ]
    orphan = [rowid for rowid in vectors_rows if rowid not in mapped]
    return (dangling, orphan)


def delete_rowids(session: Session, rowids: list[int]) -> int:
    """Drop vector + mapping rows in one bounded sweep; returns rows touched."""
    if not rowids:
        return 0
    _ensure_ids_table(session)
    removed = 0
    for start in range(0, len(rowids), 500):
        batch = rowids[start : start + 500]
        placeholders = ",".join(str(rowid) for rowid in batch)
        if table_exists(session):
            statement = text(f"DELETE FROM {VEC_TABLE} WHERE rowid IN ({placeholders})")
            removed += int(cast(Any, session.execute(statement)).rowcount or 0)
        session.execute(text(f"DELETE FROM {VEC_IDS} WHERE rowid IN ({placeholders})"))
    return removed



def search(session: Session, query_vector: list[float], limit: int = 24) -> list[tuple[str, float]]:
    meta = _load_meta(session)
    if meta.get("dim") != str(len(query_vector)):
        return []
    if _is_postgres(session):
        rows = session.execute(
            text(
                f"SELECT rowid, chunk_embedding <=> CAST(:query AS vector) AS distance "
                f"FROM {VEC_TABLE} "
                "ORDER BY chunk_embedding <=> CAST(:query AS vector) LIMIT :k"
            ),
            {"query": serialize_vector(query_vector), "k": limit},
        ).mappings()
    else:
        rows = session.execute(
            text(
                f"SELECT rowid, distance FROM {VEC_TABLE} "
                "WHERE chunk_embedding MATCH :query AND k = :k "
                "ORDER BY distance"
            ),
            {"query": serialize_vector(query_vector), "k": limit},
        ).mappings()
    distances = {int(row["rowid"]): float(row["distance"]) for row in rows}
    if not distances:
        return []
    _ensure_ids_table(session)
    placeholders = ",".join(str(rowid) for rowid in distances)
    names = {
        int(row["rowid"]): str(row["chunk_id"])
        for row in session.execute(
            text(f"SELECT rowid, chunk_id FROM {VEC_IDS} WHERE rowid IN ({placeholders})")
        ).mappings()
    }
    return [
        (uuid_str(names[rowid]), distance)
        for rowid, distance in distances.items()
        if rowid in names
    ]


def vector_count(session: Session) -> int:
    meta = _load_meta(session)
    if "dim" not in meta:
        return 0
    count: Any = session.execute(text(f"SELECT count(*) FROM {VEC_TABLE}")).scalar()
    return int(count or 0)
