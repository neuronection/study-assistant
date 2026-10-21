import hashlib
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..ai.embeddings import serialize_vector
from ..core.ids import hex_id, uuid_str

VEC_TABLE = "chunk_vecs"
VEC_META = "vec_meta"
VEC_IDS = "chunk_vec_ids"

_ROWID_MASK = 0x7FFF_FFFF_FFFF_FFFF


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
    meta = _load_meta(session)
    current_dim = meta.get("dim")
    current_model = meta.get("model")
    if current_dim == str(dim) and current_model == model:
        return False
    if current_dim is not None:
        session.execute(text(f"DROP TABLE IF EXISTS {VEC_TABLE}"))
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
