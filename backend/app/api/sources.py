from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.vocab import MaterialKind, MaterialStatus
from ..domain.models import Material, MaterialSource
from ..jobs.runner import JobRunner
from ..services.content.sources import SourcesError, SourcesService
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceBrowseOut(BaseModel):
    source_id: int
    label: str
    path: str
    subdir: str
    missing_target: bool
    enabled: bool
    scan_interval_sec: int | None
    last_scan_error: str | None
    last_scanned_at: str | None
    subdirs: list["SourceSubdirOut"]
    materials: list["SourceMaterialOut"]
    uningested: list["UningestedFileOut"]


class SourceSubdirOut(BaseModel):
    name: str


class SourceMaterialOut(BaseModel):
    id: int
    title: str
    kind: MaterialKind
    status: MaterialStatus
    filename: str
    relpath: str


class UningestedFileOut(BaseModel):
    name: str
    relpath: str
    size_bytes: int
    mtime: float


SourceBrowseOut.model_rebuild()


class SourceIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=1000)
    recursive: bool = True
    include_globs: list[str] | None = None
    course_id: int
    scan_interval_sec: int | None = Field(default=None, ge=15)


class SourceOut(BaseModel):
    id: int
    label: str
    path: str
    recursive: bool
    include_globs: list[str] | None
    course_id: int
    enabled: bool
    scan_interval_sec: int | None = None
    last_scan_error: str | None = None
    material_count: int
    last_scanned_at: str | None


def _source_out(session: Session, source: MaterialSource, material_count: int = 0) -> SourceOut:
    return SourceOut(
        id=source.id,
        label=source.label,
        path=source.path,
        recursive=source.recursive,
        include_globs=source.include_globs,
        course_id=source.course_id,
        enabled=source.enabled,
        scan_interval_sec=source.scan_interval_sec,
        last_scan_error=source.last_scan_error,
        material_count=material_count,
        last_scanned_at=(
            source.last_scanned_at.isoformat() if source.last_scanned_at else None
        ),
    )


class ScanResult(BaseModel):
    stats: dict[str, int]
    queued_jobs: int


@router.get("", response_model=list[SourceOut])
def list_sources(
    request: Request, session: Session = Depends(get_session)
) -> list[SourceOut]:
    profile = ensure_default_profile(session)
    service = SourcesService(session, request.app.state.settings.blobs_dir)
    result: list[SourceOut] = []
    for source in service.list_sources(profile.id):
        count = len(
            session.scalars(
                select(Material.id).where(Material.source_id == source.id)
            ).all()
        )
        result.append(_source_out(session, source, count))
    return result


@router.post("", response_model=SourceOut, status_code=201)
def add_source(
    body: SourceIn,
    request: Request,
    session: Session = Depends(get_session),
) -> SourceOut:
    profile = ensure_default_profile(session)
    service = SourcesService(session, request.app.state.settings.blobs_dir)
    try:
        source = service.create_source(
            profile.id,
            label=body.label,
            path=body.path,
            recursive=body.recursive,
            include_globs=body.include_globs,
            course_id=body.course_id,
            scan_interval_sec=body.scan_interval_sec,
        )
    except SourcesError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _source_out(session, source)


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> None:
    profile = ensure_default_profile(session)
    service = SourcesService(session, request.app.state.settings.blobs_dir)
    if not service.delete_source(profile.id, source_id):
        raise HTTPException(status_code=404, detail="source not found")
    session.commit()


@router.get("/{source_id}/browse", response_model=SourceBrowseOut)
def browse_source(
    source_id: int,
    request: Request,
    subdir: str = "",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    service = SourcesService(session, request.app.state.settings.blobs_dir)
    try:
        return service.browse(profile.id, source_id, subdir)
    except SourcesError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


class IngestFileIn(BaseModel):
    relpath: str = Field(min_length=1, max_length=2000)


class IngestFileOut(BaseModel):
    material_id: int
    job_id: int | None
    deduped: bool


@router.post("/{source_id}/ingest", status_code=201, response_model=IngestFileOut)
def ingest_source_file(
    source_id: int,
    body: IngestFileIn,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    service = SourcesService(session, request.app.state.settings.blobs_dir)
    try:
        material, deduped = service.ingest_file(profile.id, source_id, body.relpath)
    except SourcesError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    job_id: int | None = None
    if not deduped:
        job = JobRunner.enqueue(session, "ingest", {"material_id": material.id})
        job_id = job.id
    session.commit()
    request.app.state.jobs.wake()
    return {"material_id": material.id, "job_id": job_id, "deduped": deduped}


class RelinkIn(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


@router.patch("/{source_id}", response_model=SourceOut)
def relink_source(
    source_id: int,
    body: RelinkIn,
    request: Request,
    session: Session = Depends(get_session),
) -> SourceOut:
    profile = ensure_default_profile(session)
    service = SourcesService(session, request.app.state.settings.blobs_dir)
    try:
        source = service.relink(profile.id, source_id, body.path)
    except SourcesError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _source_out(session, source)


@router.post("/{source_id}/reveal", status_code=204)
def reveal_source(
    source_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> None:
    profile = ensure_default_profile(session)
    service = SourcesService(session, request.app.state.settings.blobs_dir)
    try:
        service.reveal(profile.id, source_id)
    except SourcesError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _enqueue_ingests(session: Session, source_id: int) -> int:
    pending = session.scalars(
        select(Material).where(
            Material.source_id == source_id, Material.status == "pending"
        )
    ).all()
    for material in pending:
        JobRunner.enqueue(session, "ingest", {"material_id": material.id})
    return len(pending)


class ScanAllOut(BaseModel):
    scanned: int
    results: dict[str, dict[str, int]]


@router.post("/scan-all", response_model=ScanAllOut)
def scan_all_sources(
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    del session
    scheduler = getattr(request.app.state, "scans", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="scan scheduler not running")
    results = scheduler.scan_all(force=True)
    return {"scanned": len(results), "results": results}


@router.post("/{source_id}/scan", response_model=ScanResult)
def scan_source(
    source_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> ScanResult:
    profile = ensure_default_profile(session)
    service = SourcesService(session, request.app.state.settings.blobs_dir)
    try:
        stats = service.scan(profile.id, source_id)
    except SourcesError as error:
        session.rollback()
        failure = SourcesService(session, request.app.state.settings.blobs_dir)
        try:
            failing = failure._get(profile.id, source_id)
            failing.last_scan_error = str(error)
            session.commit()
        except SourcesError:
            session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    queued = _enqueue_ingests(session, source_id)
    session.commit()
    request.app.state.jobs.wake()
    return ScanResult(stats=stats, queued_jobs=queued)
