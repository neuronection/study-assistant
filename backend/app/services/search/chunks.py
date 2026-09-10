from collections.abc import Callable
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ...storage import vectors
from .fusion import RRF_K
from .matching import or_terms_match, trigram_match
from .scoring import fuzzy_text_match
from .types import EmbedQuery

_CHUNK_SELECT = (
    "SELECT chunks.id AS chunk_id, chunks.text AS chunk_text, chunks.ordinal, "
    "materials.id AS material_id, materials.title AS title, {table}.markdown AS markdown "
    "FROM {table} "
    "JOIN materials ON materials.id = {table}.material_id "
    "JOIN extractions ON extractions.material_id = materials.id "
    "JOIN chunks ON chunks.extraction_id = extractions.id "
    "WHERE {table} MATCH :match {course_filter}{extra} "
    "ORDER BY rank LIMIT :limit"
)


def _chunk_rows(
    session: Session,
    chunk_ids: list[int],
    *,
    course_id: int | None = None,
    material_ids: list[int] | None = None,
) -> dict[int, dict[str, Any]]:
    if not chunk_ids:
        return {}
    placeholders = ",".join(str(int(chunk_id)) for chunk_id in chunk_ids)
    filters = [f"chunks.id IN ({placeholders})"]
    if course_id is not None:
        filters.append("materials.course_id = :course_id")
    if material_ids is not None:
        if not material_ids:
            return {}
        ids = ",".join(str(int(mid)) for mid in material_ids)
        filters.append(f"materials.id IN ({ids})")
    rows = session.execute(
        text(
            "SELECT chunks.id AS chunk_id, chunks.text AS chunk_text, "
            "materials.id AS material_id, materials.title AS title "
            "FROM chunks JOIN extractions ON extractions.id = chunks.extraction_id "
            "JOIN materials ON materials.id = extractions.material_id "
            f"WHERE {' AND '.join(filters)}"
        ),
        {"course_id": course_id},
    ).mappings()
    return {
        int(row["chunk_id"]): {
            "chunk_id": int(row["chunk_id"]),
            "material_id": int(row["material_id"]),
            "title": row["title"],
            "text": row["chunk_text"],
        }
        for row in rows
    }


def _vector_chunk_ranking(
    session: Session,
    embed_query: EmbedQuery,
    query: str,
    limit: int,
    *,
    course_id: int | None = None,
    material_ids: list[int] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        embedded = embed_query(query)
        if embedded is None or not embedded[1]:
            return [], "no embeddings model is assigned (Settings → Tasks)"
        _model, vectors_batch = embedded
        hits = vectors.search(session, vectors_batch[0], limit=limit * 3)
    except Exception as error:
        return [], f"the embeddings request failed ({type(error).__name__})"
    rows = _chunk_rows(
        session,
        [chunk_id for chunk_id, _distance in hits],
        course_id=course_id,
        material_ids=material_ids,
    )
    return (
        [rows[chunk_id] for chunk_id, _distance in hits if chunk_id in rows],
        None,
    )


def _fts_chunk_rows(
    session: Session,
    match: str,
    limit: int,
    *,
    course_id: int | None = None,
    material_ids: list[int] | None = None,
    table: str = "material_fts",
    verify_query: str | None = None,
) -> list[dict[str, Any]]:
    if not match:
        return []
    course_filter = "AND materials.course_id = :course_id" if course_id is not None else ""
    params: dict[str, Any] = {"match": match, "limit": limit, "course_id": course_id}
    extra = ""
    if material_ids is not None:
        if not material_ids:
            return []
        extra = " AND materials.id IN :material_ids"
        params["material_ids"] = material_ids
    statement = text(_CHUNK_SELECT.format(table=table, course_filter=course_filter, extra=extra))
    if material_ids is not None:
        statement = statement.bindparams(bindparam("material_ids", expanding=True))
    try:
        fts_rows = session.execute(statement, params).mappings()
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in fts_rows:
        if row["chunk_id"] in seen:
            continue
        seen.add(int(row["chunk_id"]))
        if verify_query is not None and not fuzzy_text_match(
            verify_query, f"{row['title']}\n{row['markdown']}"
        ):
            continue
        rows.append(
            {
                "chunk_id": int(row["chunk_id"]),
                "material_id": int(row["material_id"]),
                "title": row["title"],
                "text": row["chunk_text"],
            }
        )
    return rows


def retrieve_chunks_hybrid(
    session: Session,
    query: str,
    embed_query: EmbedQuery,
    *,
    course_id: int | None = None,
    material_ids: list[int] | None = None,
    limit: int = 8,
    use_embeddings: bool = True,
    embedding_warning: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    fts_rows = retrieve_chunks(
        session,
        query,
        embed_query,
        course_id=course_id,
        material_ids=material_ids,
        limit=limit * 2,
    )
    if not use_embeddings:
        return fts_rows[:limit]
    vector_rows, warning = _vector_chunk_ranking(
        session,
        embed_query,
        query,
        limit,
        course_id=course_id,
        material_ids=material_ids,
    )
    if warning is not None and embedding_warning is not None:
        embedding_warning(warning)
    if not vector_rows:
        return fts_rows[:limit]
    scores: dict[int, float] = {}
    entries: dict[int, dict[str, Any]] = {}
    for ranking in (fts_rows, vector_rows):
        for rank, row in enumerate(ranking):
            chunk_id = row["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            entries.setdefault(chunk_id, row)
    ranked = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [entries[chunk_id] for chunk_id in ranked[:limit]]


def retrieve_chunks(
    session: Session,
    query: str,
    embed_query: EmbedQuery,
    *,
    course_id: int | None = None,
    material_ids: list[int] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    rows = _fts_chunk_rows(
        session,
        or_terms_match(query),
        limit,
        course_id=course_id,
        material_ids=material_ids,
    )
    if len(rows) < limit:
        fuzzy_rows = _fts_chunk_rows(
            session,
            trigram_match(query),
            limit * 3,
            course_id=course_id,
            material_ids=material_ids,
            table="material_fts_trigram",
            verify_query=query,
        )
        seen = {row["chunk_id"] for row in rows}
        rows.extend(row for row in fuzzy_rows if row["chunk_id"] not in seen)
    return rows[:limit]
