from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import LectureRetention
from ..domain.models import LectureSession
from ..services.media.lectures import (
    LectureConflict,
    LectureError,
    chunks,
    create_session,
    finalize,
    get_session,
    list_sessions,
    missing_sequences,
    purge_due_text_only,
    purge_text_only_audio,
    put_chunk,
    update_session,
)
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session as get_db

router = APIRouter(prefix="/lectures", tags=["lectures"])


class LectureCreateIn(BaseModel):
    course_id: str
    node_id: str | None = None
    title: str = Field(default="Lecture recording", min_length=1, max_length=300)
    consent_confirmed: bool
    retention: str = Field(default=LectureRetention.AUDIO_AND_TEXT.value, max_length=20)
    mime: str = Field(default="audio/webm", max_length=120)


class LecturePatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: str | None = Field(default=None, max_length=20)
    retention: str | None = Field(default=None, max_length=20)


class LectureChunkOut(BaseModel):
    seq: int
    sha256: str
    size: int


class LectureOut(BaseModel):
    id: str
    course_id: str
    node_id: str | None
    title: str
    status: str
    retention: str
    mime: str
    consent_confirmed: bool
    started_at: datetime
    ended_at: datetime | None
    audio_purged_at: datetime | None
    material_id: str | None
    error: str | None
    created_at: datetime
    chunk_count: int
    missing_sequences: list[int]


class LectureChunkListOut(BaseModel):
    chunks: list[LectureChunkOut]
    missing_sequences: list[int]


class LectureFinalizeOut(BaseModel):
    material_id: str
    status: str


def _out(session: Session, row: LectureSession) -> LectureOut:
    rows = chunks(session, row)
    return LectureOut(
        id=row.id,
        course_id=row.course_id,
        node_id=row.node_id,
        title=row.title,
        status=row.status,
        retention=row.retention,
        mime=row.mime,
        consent_confirmed=row.consent_confirmed,
        started_at=row.started_at,
        ended_at=row.ended_at,
        audio_purged_at=row.audio_purged_at,
        material_id=row.material_id,
        error=row.error,
        created_at=row.created_at,
        chunk_count=len(rows),
        missing_sequences=missing_sequences(session, row),
    )


def _load(session: Session, session_id: str, profile_id: str) -> LectureSession:
    try:
        return get_session(session, session_id, profile_id)
    except LectureError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("", response_model=LectureOut, status_code=201)
def create_lecture(body: LectureCreateIn, session: Session = Depends(get_db)) -> LectureOut:
    profile = ensure_default_profile(session)
    try:
        row = create_session(
            session,
            profile_id=profile.id,
            course_id=body.course_id,
            node_id=body.node_id,
            title=body.title,
            consent_confirmed=body.consent_confirmed,
            retention=body.retention,
            mime=body.mime,
        )
    except LectureError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(session, row)


@router.get("", response_model=list[LectureOut])
def list_lectures(
    request: Request,
    course_id: str | None = None,
    session: Session = Depends(get_db),
) -> list[LectureOut]:
    profile = ensure_default_profile(session)
    purge_due_text_only(session, profile.id, request.app.state.blobs)
    session.commit()
    return [_out(session, row) for row in list_sessions(session, profile.id, course_id)]


@router.get("/{session_id}", response_model=LectureOut)
def get_lecture(
    session_id: str, request: Request, session: Session = Depends(get_db)
) -> LectureOut:
    profile = ensure_default_profile(session)
    purge_due_text_only(session, profile.id, request.app.state.blobs)
    session.commit()
    return _out(session, _load(session, session_id, profile.id))


@router.patch("/{session_id}", response_model=LectureOut)
def patch_lecture(
    session_id: str,
    body: LecturePatchIn,
    session: Session = Depends(get_db),
) -> LectureOut:
    profile = ensure_default_profile(session)
    row = _load(session, session_id, profile.id)
    try:
        update_session(
            session,
            row,
            title=body.title,
            status=body.status,
            retention=body.retention,
        )
    except LectureError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(session, row)


@router.put("/{session_id}/chunks/{seq}", response_model=LectureChunkOut)
async def upload_lecture_chunk(
    session_id: str,
    seq: int,
    request: Request,
    x_chunk_sha256: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> LectureChunkOut:
    profile = ensure_default_profile(session)
    row = _load(session, session_id, profile.id)
    data = await request.body()
    try:
        chunk = put_chunk(
            session,
            blobs=request.app.state.blobs,
            row=row,
            seq=seq,
            data=data,
            sha256=x_chunk_sha256 or "",
        )
    except LectureConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except LectureError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return LectureChunkOut(seq=chunk.seq, sha256=chunk.sha256, size=chunk.size)


@router.get("/{session_id}/chunks", response_model=LectureChunkListOut)
def list_lecture_chunks(
    session_id: str, session: Session = Depends(get_db)
) -> LectureChunkListOut:
    profile = ensure_default_profile(session)
    row = _load(session, session_id, profile.id)
    return LectureChunkListOut(
        chunks=[
            LectureChunkOut(seq=chunk.seq, sha256=chunk.sha256, size=chunk.size)
            for chunk in chunks(session, row)
        ],
        missing_sequences=missing_sequences(session, row),
    )


@router.post("/{session_id}/finalize", response_model=LectureFinalizeOut)
def finalize_lecture(
    session_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> LectureFinalizeOut:
    profile = ensure_default_profile(session)
    row = _load(session, session_id, profile.id)
    try:
        material = finalize(
            session,
            row=row,
            blobs=request.app.state.blobs,
            jobs=request.app.state.jobs,
        )
    except LectureConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except LectureError as error:
        session.commit()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return LectureFinalizeOut(material_id=material.id, status=row.status)


@router.post("/{session_id}/purge-audio", response_model=LectureOut)
def purge_lecture_audio(
    session_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> LectureOut:
    profile = ensure_default_profile(session)
    row = _load(session, session_id, profile.id)
    try:
        purge_text_only_audio(session, row, request.app.state.blobs)
    except LectureConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except LectureError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(session, row)


@router.delete("/{session_id}", status_code=204)
def cancel_lecture(session_id: str, session: Session = Depends(get_db)) -> None:
    profile = ensure_default_profile(session)
    row = _load(session, session_id, profile.id)
    row.status = "cancelled"
    session.commit()
