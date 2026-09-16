from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import DiscoveryKind, SuggestionStatus
from ..domain.models import MaterialSuggestion
from ..search.discovery import (
    DiscoveryError,
    DiscoveryResult,
    resolve_providers,
)
from ..services.content import discovery as suggestions
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/discovery", tags=["discovery"])

_DISCOVERY_IN_FLIGHT: set[int] = set()


class DiscoverySearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    providers: list[str] | None = None
    cap: int = Field(default=10, ge=1, le=25)


class SuggestionStateOut(BaseModel):
    id: int
    status: str
    material_id: int | None = None


class DiscoveryResultOut(BaseModel):
    provider: str
    title: str
    url: str
    kind: str
    description: str = ""
    meta: dict[str, object] = Field(default_factory=dict)
    suggestion: SuggestionStateOut | None = None


class DiscoveryProviderErrorOut(BaseModel):
    provider: str
    error: str


class DiscoverySearchOut(BaseModel):
    results: list[DiscoveryResultOut]
    errors: list[DiscoveryProviderErrorOut]


class SuggestionOut(BaseModel):
    id: int
    course_id: int | None
    node_id: int | None
    provider: str
    url: str
    url_norm: str
    title: str
    snippet: str = ""
    kind: str
    meta: dict[str, object] = Field(default_factory=dict)
    status: str
    material_id: int | None
    created_at: datetime
    updated_at: datetime


def _suggestion_out(row: MaterialSuggestion) -> SuggestionOut:
    return SuggestionOut(
        id=row.id,
        course_id=row.course_id,
        node_id=row.node_id,
        provider=row.provider,
        url=row.url,
        url_norm=row.url_norm,
        title=row.title,
        snippet=row.snippet or "",
        kind=row.kind,
        meta=row.meta or {},
        status=row.status,
        material_id=row.material_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SuggestionSaveIn(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=300)
    snippet: str | None = Field(default=None, max_length=2000)
    kind: str | None = None
    meta: dict[str, object] | None = None
    course_id: int | None = None
    node_id: int | None = None


class SuggestionSaveOut(BaseModel):
    suggestion: SuggestionOut
    created: bool


class SuggestionPatchIn(BaseModel):
    status: str | None = None
    material_id: int | None = None
    node_id: int | None = None


class SuggestionListOut(BaseModel):
    items: list[SuggestionOut]
    next_cursor: int | None = None


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
    results = results[: body.cap * len(providers)]
    known = suggestions.suggestion_states_for_urls(
        session, profile.id, [result.url for result in results]
    )
    if known:
        for result in results:
            match = known.get(result.url)
            if match is not None:
                result.suggestion = SuggestionStateOut(
                    id=match.id,
                    status=match.status,
                    material_id=match.material_id,
                )
    return DiscoverySearchOut(results=results, errors=errors)


@router.get("/suggestions", response_model=SuggestionListOut)
def list_suggestions(
    course_id: int | None = None,
    node_id: int | None = None,
    status: str | None = None,
    kind: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> SuggestionListOut:
    profile = ensure_default_profile(session)
    try:
        if status is not None:
            SuggestionStatus.parse(status)
        rows, next_cursor = suggestions.list_suggestions(
            session,
            profile.id,
            course_id=course_id,
            node_id=node_id,
            status=status,
            kind=kind,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return SuggestionListOut(
        items=[_suggestion_out(row) for row in rows], next_cursor=next_cursor
    )


@router.post("/suggestions", response_model=SuggestionSaveOut, status_code=200)
def save_suggestion(
    body: SuggestionSaveIn,
    session: Session = Depends(get_session),
) -> SuggestionSaveOut:
    profile = ensure_default_profile(session)
    try:
        row, created = suggestions.save_suggestion(
            session,
            profile.id,
            provider=body.provider,
            url=body.url,
            title=body.title,
            snippet=body.snippet,
            kind=body.kind,
            meta=body.meta,
            course_id=body.course_id,
            node_id=body.node_id,
        )
        session.commit()
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    return SuggestionSaveOut(suggestion=_suggestion_out(row), created=created)


@router.patch("/suggestions/{suggestion_id}", response_model=SuggestionOut)
def patch_suggestion(
    suggestion_id: int,
    body: SuggestionPatchIn,
    session: Session = Depends(get_session),
) -> SuggestionOut:
    profile = ensure_default_profile(session)
    try:
        row = suggestions.update_suggestion(
            session,
            profile.id,
            suggestion_id,
            status=body.status,
            material_id=body.material_id,
            node_id=body.node_id,
        )
        session.commit()
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _suggestion_out(row)


@router.delete("/suggestions/{suggestion_id}", status_code=204)
def delete_suggestion(
    suggestion_id: int,
    session: Session = Depends(get_session),
) -> None:
    profile = ensure_default_profile(session)
    try:
        suggestions.forget_suggestion(session, profile.id, suggestion_id)
        session.commit()
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
