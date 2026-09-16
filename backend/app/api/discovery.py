from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import DiscoveryKind
from ..search.discovery import (
    DiscoveryError,
    DiscoveryResult,
    resolve_providers,
)
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/discovery", tags=["discovery"])

_DISCOVERY_IN_FLIGHT: set[int] = set()


class DiscoverySearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    providers: list[str] | None = None
    cap: int = Field(default=10, ge=1, le=25)


class DiscoveryResultOut(BaseModel):
    provider: str
    title: str
    url: str
    kind: str
    description: str = ""
    meta: dict[str, object] = Field(default_factory=dict)


class DiscoveryProviderErrorOut(BaseModel):
    provider: str
    error: str


class DiscoverySearchOut(BaseModel):
    results: list[DiscoveryResultOut]
    errors: list[DiscoveryProviderErrorOut]


@router.get("/kinds", response_model=list[str])
def discovery_kinds() -> list[str]:
    return [kind.value for kind in DiscoveryKind]


@router.post("/search", response_model=DiscoverySearchOut)
def discovery_search(
    body: DiscoverySearchIn,
    request: Request,
    session: Session = Depends(get_session),
) -> DiscoverySearchOut:
    profile = ensure_default_profile(session)
    if profile.id in _DISCOVERY_IN_FLIGHT:
        raise HTTPException(
            status_code=409, detail="a discovery search is already running"
        )
    try:
        providers = resolve_providers(
            session,
            profile.id,
            transport=getattr(request.app.state, "search_transport", None),
            requested=body.providers,
        )
    except DiscoveryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not providers:
        raise HTTPException(
            status_code=503,
            detail="no discovery providers configured — connect a search "
            "provider in Settings",
        )
    _DISCOVERY_IN_FLIGHT.add(profile.id)
    results: list[DiscoveryResultOut] = []
    errors: list[DiscoveryProviderErrorOut] = []
    try:
        for provider in providers:
            try:
                found: list[DiscoveryResult] = provider.search(
                    body.query.strip(), cap=body.cap
                )
            except Exception as error:
                errors.append(
                    DiscoveryProviderErrorOut(
                        provider=provider.id, error=str(error)[:300]
                    )
                )
                continue
            for row in found:
                results.append(
                    DiscoveryResultOut(
                        provider=row.provider,
                        title=row.title[:300],
                        url=row.url,
                        kind=row.kind,
                        description=row.description[:800],
                        meta=row.meta,
                    )
                )
    finally:
        _DISCOVERY_IN_FLIGHT.discard(profile.id)
    if not results and errors:
        raise HTTPException(
            status_code=502,
            detail="; ".join(
                f"{entry.provider}: {entry.error}" for entry in errors
            ),
        )
    return DiscoverySearchOut(results=results[: body.cap * len(providers)], errors=errors)
