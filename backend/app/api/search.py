from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..services.search import hybrid_search
from .deps import get_session
from .schemas import SearchHit, SearchOut

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchOut)
def search(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    course_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> SearchOut:
    def embed_query(query: str) -> tuple[str, list[list[float]]] | None:
        result: tuple[str, list[list[float]]] | None = request.app.state.embedder.embed([query])
        return result

    hits = hybrid_search(session, q, limit, embed_query, course_id)
    return SearchOut(
        query=q,
        hits=[SearchHit(**hit) for hit in hits],
    )
