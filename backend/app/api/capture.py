from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.vocab import CaptureStatus
from ..domain.models import CaptureStaging
from ..services.capture import (
    CaptureBlobMissing,
    CaptureConflict,
    CaptureItem,
    CaptureNotFound,
    assemble_captures,
    commit_capture,
    discard_capture,
    list_staged_captures,
    stage_captures,
    sweep_expired_captures,
)
from ..services.content.materials import UnsupportedMaterialError
from ..services.knowledge.courses import CourseError
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/capture", tags=["capture"])


class CaptureStagingOut(BaseModel):
    id: str
    source_kind: str
    status: str
    filename: str
    mime: str | None
    blob_sha: str
    byte_size: int
    group_id: str | None
    created_at: datetime
    expires_at: datetime
    material_id: str | None


class CaptureAssembleItemIn(BaseModel):
    capture_id: str
    rotation: int = 0


class CaptureAssembleIn(BaseModel):
    items: list[CaptureAssembleItemIn]
    title: str | None = None


class CaptureCommitIn(BaseModel):
    course_id: str
    folder_id: str | None = None
    node_id: str | None = None
    title: str | None = None


class CaptureCommitOut(BaseModel):
    capture_id: str
    material_id: str
    job_id: str | None
    deduped: bool
    status: str


def _out(row: CaptureStaging) -> CaptureStagingOut:
    return CaptureStagingOut(
        id=row.id,
        source_kind=row.source_kind,
        status=row.status,
        filename=row.filename,
        mime=row.mime,
        blob_sha=row.blob_sha,
        byte_size=row.byte_size,
        group_id=row.group_id,
        created_at=row.created_at,
        expires_at=row.expires_at,
        material_id=row.material_id,
    )


@router.post("", response_model=list[CaptureStagingOut], status_code=201)
async def create_capture(
    request: Request,
    files: list[UploadFile] = File(...),
    source_kind: str = Form("upload"),
    group_id: str | None = Form(None),
    client_op_id: str | None = Form(None),
    session: Session = Depends(get_session),
) -> list[CaptureStagingOut]:
    profile = ensure_default_profile(session)
    items: list[CaptureItem] = []
    for upload in files:
        data = await upload.read()
        items.append(
            CaptureItem(filename=upload.filename or "capture", mime=upload.content_type, data=data)
        )
    if client_op_id is None:
        client_ids: list[str | None] = [None] * len(items)
    elif len(items) == 1:
        client_ids = [client_op_id]
    else:
        client_ids = [f"{client_op_id}:{index}" for index in range(len(items))]
    try:
        rows = stage_captures(
            session,
            request.app.state.blobs,
            profile_id=profile.id,
            source_kind=source_kind,
            items=items,
            group_id=group_id,
            client_op_ids=client_ids,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return [_out(row) for row in rows]


@router.get("", response_model=list[CaptureStagingOut])
def list_captures(
    request: Request,
    status: CaptureStatus = CaptureStatus.STAGED,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[CaptureStagingOut]:
    profile = ensure_default_profile(session)
    sweep_expired_captures(session)
    session.commit()
    rows = list_staged_captures(
        session,
        profile_id=profile.id,
        status=status,
        limit=max(1, min(limit, 100)),
    )
    return [_out(row) for row in rows]


@router.post("/assemble", response_model=CaptureStagingOut, status_code=201)
def assemble_capture_pages(
    request: Request,
    body: CaptureAssembleIn,
    session: Session = Depends(get_session),
) -> CaptureStagingOut:
    profile = ensure_default_profile(session)
    try:
        row = assemble_captures(
            session,
            request.app.state.blobs,
            profile_id=profile.id,
            items=[(item.capture_id, item.rotation) for item in body.items],
            title=body.title,
        )
    except CaptureNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except CaptureConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CaptureBlobMissing as error:
        raise HTTPException(status_code=410, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(row)


@router.post("/{capture_id}/commit", response_model=CaptureCommitOut)
def commit_capture_endpoint(
    request: Request,
    capture_id: str,
    body: CaptureCommitIn,
    session: Session = Depends(get_session),
) -> CaptureCommitOut:
    profile = ensure_default_profile(session)
    try:
        result = commit_capture(
            session,
            request.app.state.blobs,
            request.app.state.jobs,
            capture_id=capture_id,
            profile_id=profile.id,
            course_id=body.course_id,
            folder_id=body.folder_id,
            node_id=body.node_id,
            title=body.title,
        )
    except CaptureNotFound as error:
        raise HTTPException(status_code=404, detail="capture not found") from error
    except CaptureConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CaptureBlobMissing as error:
        raise HTTPException(status_code=410, detail=str(error)) from error
    except UnsupportedMaterialError as error:
        raise HTTPException(
            status_code=422,
            detail={"reason": "unsupported_type", "suffix": error.suffix},
        ) from error
    except (CourseError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return CaptureCommitOut(
        capture_id=result.capture_id,
        material_id=result.material_id,
        job_id=result.job_id,
        deduped=result.deduped,
        status="committed",
    )


@router.delete("/{capture_id}", response_model=CaptureStagingOut)
def discard_capture_endpoint(
    capture_id: str,
    session: Session = Depends(get_session),
) -> CaptureStagingOut:
    profile = ensure_default_profile(session)
    try:
        row = discard_capture(session, capture_id=capture_id, profile_id=profile.id)
    except CaptureNotFound as error:
        raise HTTPException(status_code=404, detail="capture not found") from error
    session.commit()
    return _out(row)
