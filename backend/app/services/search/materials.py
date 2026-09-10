from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...storage import vectors
from .fusion import (
    TIER_WEIGHT_EXACT,
    TIER_WEIGHT_PREFIX,
    TIER_WEIGHT_TRIGRAM,
    TIER_WEIGHT_VECTOR,
    fuse_rrf,
)
from .matching import phrase_match, prefix_terms_match, trigram_match
from .scoring import fuzzy_text_match
from .types import EmbedQuery

_COURSE_FILTER = "AND materials.course_id = :course_id"


def _fts_ranking(
    session: Session,
    match: str,
    limit: int,
    course_id: int | None = None,
    *,
    table: str = "material_fts",
) -> list[dict[str, Any]]:
    if not match:
        return []
    course_filter = _COURSE_FILTER if course_id is not None else ""
    try:
        rows = session.execute(
            text(
                f"SELECT {table}.material_id AS material_id, materials.title AS title, "
                f"snippet({table}, 1, '…', '…', '…', 12) AS snippet "
                f"FROM {table} JOIN materials ON materials.id = {table}.material_id "
                f"WHERE {table} MATCH :match {course_filter} "
                "ORDER BY rank LIMIT :limit"
            ),
            {"match": match, "limit": limit, "course_id": course_id},
        ).mappings()
    except Exception:
        return []
    return [dict(row) for row in rows]


def _trigram_ranking(
    session: Session,
    query: str,
    limit: int,
    course_id: int | None = None,
) -> list[dict[str, Any]]:
    match = trigram_match(query)
    if not match:
        return []
    course_filter = _COURSE_FILTER if course_id is not None else ""
    try:
        rows = session.execute(
            text(
                "SELECT material_fts_trigram.material_id AS material_id, "
                "material_fts_trigram.title AS title, "
                "material_fts_trigram.markdown AS markdown, "
                "snippet(material_fts_trigram, 1, '…', '…', '…', 12) AS snippet "
                "FROM material_fts_trigram "
                "JOIN materials ON materials.id = material_fts_trigram.material_id "
                f"WHERE material_fts_trigram MATCH :match {course_filter} "
                "ORDER BY rank LIMIT :limit"
            ),
            {"match": match, "limit": limit * 3, "course_id": course_id},
        ).mappings()
    except Exception:
        return []
    hits: list[dict[str, Any]] = []
    for row in rows:
        if not fuzzy_text_match(query, f"{row['title']}\n{row['markdown']}"):
            continue
        hits.append(
            {
                "material_id": row["material_id"],
                "title": row["title"],
                "snippet": row["snippet"],
            }
        )
        if len(hits) == limit:
            break
    return hits


def _vector_ranking(
    session: Session,
    embed_query: EmbedQuery,
    query: str,
    limit: int,
    course_id: int | None = None,
) -> list[dict[str, Any]]:
    try:
        embedded = embed_query(query)
        if embedded is None or not embedded[1]:
            return []
        _model, vectors_batch = embedded
        query_vector = vectors_batch[0]
        hits = vectors.search(session, query_vector, limit=limit)
    except Exception:
        return []
    if not hits:
        return []
    chunk_ids = [chunk_id for chunk_id, _distance in hits]
    placeholders = ",".join(str(int(chunk_id)) for chunk_id in chunk_ids)
    course_filter = _COURSE_FILTER if course_id is not None else ""
    rows = session.execute(
        text(
            "SELECT chunks.id AS chunk_id, chunks.text AS chunk_text, "
            "materials.id AS material_id, materials.title AS title "
            "FROM chunks JOIN extractions ON extractions.id = chunks.extraction_id "
            "JOIN materials ON materials.id = extractions.material_id "
            f"WHERE chunks.id IN ({placeholders}) {course_filter}"
        ),
        {"course_id": course_id},
    ).mappings()
    by_chunk = {row["chunk_id"]: row for row in rows}
    results: list[dict[str, Any]] = []
    for chunk_id, _distance in hits:
        row = by_chunk.get(chunk_id)
        if row is None:
            continue
        excerpt = row["chunk_text"][:180].replace("\n", " ")
        results.append(
            {
                "material_id": row["material_id"],
                "title": row["title"],
                "snippet": f"…{excerpt}…",
            }
        )
    return results


def hybrid_search(
    session: Session,
    query: str,
    limit: int,
    embed_query: EmbedQuery,
    course_id: int | None = None,
) -> list[dict[str, Any]]:
    exact_hits = _fts_ranking(session, phrase_match(query), limit, course_id)
    rankings: list[tuple[list[dict[str, Any]], float]] = [(exact_hits, TIER_WEIGHT_EXACT)]
    if len(exact_hits) < limit:
        prefix_hits = _fts_ranking(session, prefix_terms_match(query), limit, course_id)
        rankings.append((prefix_hits, TIER_WEIGHT_PREFIX))
        if len(exact_hits) + len(prefix_hits) < limit:
            fuzzy_hits = _trigram_ranking(session, query, limit, course_id)
            rankings.append((fuzzy_hits, TIER_WEIGHT_TRIGRAM))
    vector_hits = _vector_ranking(session, embed_query, query, limit, course_id)
    rankings.append((vector_hits, TIER_WEIGHT_VECTOR))
    return fuse_rrf(rankings, key="material_id", limit=limit)
