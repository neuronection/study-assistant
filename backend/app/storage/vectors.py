from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..ai.embeddings import serialize_vector

VEC_TABLE = "chunk_vecs"
VEC_META = "vec_meta"


def _load_meta(session: Session) -> dict[str, str]:
    session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {VEC_META} "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
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


def store(
    session: Session, chunk_ids: list[int], vectors: list[list[float]], model: str
) -> None:
    dim = len(vectors[0])
    ensure_table(session, dim, model)
    for chunk_id, vector in zip(chunk_ids, vectors, strict=True):
        session.execute(
            text(
                f"INSERT OR REPLACE INTO {VEC_TABLE} (rowid, chunk_embedding) "
                "VALUES (:rowid, :vec)"
            ),
            {"rowid": chunk_id, "vec": serialize_vector(vector)},
        )


def delete_for_extraction(session: Session, chunk_ids: list[int]) -> None:
    if not chunk_ids:
        return
    exists = session.execute(
        text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = :name"
        ),
        {"name": VEC_TABLE},
    ).first()
    if exists is None:
        return
    placeholders = ",".join(str(int(chunk_id)) for chunk_id in chunk_ids)
    session.execute(
        text(f"DELETE FROM {VEC_TABLE} WHERE rowid IN ({placeholders})")
    )


def search(
    session: Session, query_vector: list[float], limit: int = 24
) -> list[tuple[int, float]]:
    meta = _load_meta(session)
    if meta.get("dim") != str(len(query_vector)):
        return []
    rows = session.execute(
        text(
            f"SELECT rowid, distance FROM {VEC_TABLE} "
            "WHERE chunk_embedding MATCH :query AND k = :k "
            "ORDER BY distance"
        ),
        {"query": serialize_vector(query_vector), "k": limit},
    ).mappings()
    return [(int(row["rowid"]), float(row["distance"])) for row in rows]


def vector_count(session: Session) -> int:
    meta = _load_meta(session)
    if "dim" not in meta:
        return 0
    count: Any = session.execute(text(f"SELECT count(*) FROM {VEC_TABLE}")).scalar()
    return int(count or 0)
