from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.models import Course, ExternalSource
from ..services.content import external_sources as external
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/external-sources", tags=["external-sources"])

MIN_INTERVAL_SEC = external.MIN_SCAN_INTERVAL_SEC


class ExternalSourceIn(BaseModel):
    course_id: int
    kind: str = Field(min_length=1, max_length=30)
    url: str = Field(min_length=1, max_length=2048)
    label: str | None = Field(default=None, max_length=200)
    options: dict[str, Any] | None = None
    enabled: bool = True
    scan_interval_sec: int | None = Field(default=None, ge=MIN_INTERVAL_SEC)


class ExternalSourcePatch(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    options: dict[str, Any] | None = None
    scan_interval_sec: int | None = Field(default=None, ge=MIN_INTERVAL_SEC)


class ExternalSourceOut(BaseModel):
    id: int
    course_id: int
    kind: str
    url: str
    label: str | None
    options: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    scan_interval_sec: int | None
    last_scan_error: str | None
    last_scanned_at: str | None


def _out(source: ExternalSource) -> ExternalSourceOut:
    return ExternalSourceOut(
        id=source.id,
        course_id=source.course_id,
        kind=source.kind,
        url=source.url,
        label=source.label,
        options=source.options or {},
        enabled=source.enabled,
        scan_interval_sec=source.scan_interval_sec,
        last_scan_error=source.last_scan_error,
        last_scanned_at=(
            source.last_scanned_at.isoformat() if source.last_scanned_at else None
        ),
    )


def _owned_source(
    session: Session, profile_id: int, source_id: int
) -> ExternalSource:
    source = session.get(ExternalSource, source_id)
    if source is None or source.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="source not found")
    return source


@router.get("", response_model=list[ExternalSourceOut])
def list_sources(
    course_id: int | None = None,
    session: Session = Depends(get_session),
) -> list[ExternalSourceOut]:
    profile = ensure_default_profile(session)
    stmt = select(ExternalSource).where(
        ExternalSource.profile_id == profile.id
    )
    if course_id is not None:
        stmt = stmt.where(ExternalSource.course_id == course_id)
    sources = list(session.scalars(stmt.order_by(ExternalSource.id)))
    return [_out(source) for source in sources]


@router.post("", response_model=ExternalSourceOut, status_code=201)
def create_source(
    body: ExternalSourceIn,
    session: Session = Depends(get_session),
) -> ExternalSourceOut:
    profile = ensure_default_profile(session)
    course = session.get(Course, body.course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=422, detail="course not found")
    try:
        kind, url, options = external.validate_source(
            body.kind, body.url, body.options
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    source = ExternalSource(
        profile_id=profile.id,
        course_id=body.course_id,
        kind=kind,
        url=url,
        label=(body.label or "").strip()[:200] or None,
        options=options,
        enabled=body.enabled,
        scan_interval_sec=body.scan_interval_sec,
    )
    session.add(source)
    session.commit()
    return _out(source)


@router.patch("/{source_id}", response_model=ExternalSourceOut)
def patch_source(
    source_id: int,
    body: ExternalSourcePatch,
    session: Session = Depends(get_session),
) -> ExternalSourceOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    if body.label is not None:
        source.label = body.label.strip()[:200] or None
    if body.enabled is not None:
        source.enabled = body.enabled
    if body.scan_interval_sec is not None:
        source.scan_interval_sec = body.scan_interval_sec
    if body.options is not None:
        try:
            _, _, options = external.validate_source(
                source.kind, source.url, body.options
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        source.options = options
    session.commit()
    return _out(source)


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: int,
    session: Session = Depends(get_session),
) -> None:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    session.delete(source)
    session.commit()


@router.post("/{source_id}/scan", response_model=dict[str, int])
def scan_source(
    source_id: int,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        stats = external.run_scan(session, source)
        session.commit()
    except (external.ExternalSourcesError, ValueError) as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        session.rollback()
        dead = session.get(ExternalSource, source_id)
        if dead is not None:
            dead.last_scan_error = str(error)[:500]
            session.commit()
        raise HTTPException(
            status_code=502, detail=f"scan failed: {str(error)[:300]}"
        ) from error
    return stats
    return stats
