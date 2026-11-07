from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..ai.embeddings import embed_with_tags
from ..services.retrieval import lifecycle
from ..services.retrieval.v1_store import V1_SPACE_ID
from ..services.search import hybrid_search, node_placements_for_materials
from .deps import get_session
from .schemas import SearchHit, SearchHitNode, SearchOut

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchOut)
def search(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    course_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> SearchOut:
    def embed_query(query: str) -> tuple[str, list[list[float]]] | None:
        tags = {
            "space_id": lifecycle.active_space_id(session) or V1_SPACE_ID,
            "kind": "query",
            "view": "body",
        }
        return embed_with_tags(request.app.state.embedder.embed, [query], tags)

    hits = hybrid_search(session, q, limit, embed_query, course_id)
    placements = node_placements_for_materials(session, [str(hit["material_id"]) for hit in hits])
    return SearchOut(
        query=q,
        hits=[
            SearchHit(
                **hit,
                nodes=[SearchHitNode(**row) for row in placements.get(str(hit["material_id"]), [])],
            )
            for hit in hits
        ],
    )
