from typing import Literal

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from .. import __version__
from ..storage.health import STATUS_DEGRADED
from .schemas import HealthResponse, StorageHealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request, response: Response) -> HealthResponse:
    with request.app.state.engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    storage = request.app.state.storage_health.snapshot()
    overall: Literal["ok", "degraded", "unhealthy"]
    if storage.failed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall = "unhealthy"
    elif storage.status == STATUS_DEGRADED:
        overall = "degraded"
    else:
        overall = "ok"
    return HealthResponse(
        status=overall,
        version=__version__,
        db="ok",
        storage=StorageHealthResponse(**storage.payload()),
    )


@router.post("/shell/rendered", status_code=204)
def shell_rendered(request: Request) -> None:
    request.app.state.spa_rendered = True
