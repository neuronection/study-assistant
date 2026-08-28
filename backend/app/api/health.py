from fastapi import APIRouter, Request
from sqlalchemy import text

from .. import __version__
from .schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    with request.app.state.engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return HealthResponse(status="ok", version=__version__, db="ok")
