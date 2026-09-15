from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import StudySessionKind, StudySessionSource
from ..domain.models import StudySession
from ..services.platform.profiles import ensure_default_profile
from ..services.study import sessions as sessions_service
from .deps import get_session

router = APIRouter(prefix="/study-sessions", tags=["study-sessions"])


class StudySessionStartIn(BaseModel):
    kind: StudySessionKind
    source: StudySessionSource = StudySessionSource.AUTO
    course_id: int | None = None
    node_id: int | None = None
    entity_ref: str | None = Field(default=None, max_length=120)


class StudySessionBeatIn(BaseModel):
    action: Literal["heartbeat", "end"] = "heartbeat"


class StudySessionOut(BaseModel):
    id: int
    kind: StudySessionKind
    source: StudySessionSource
    course_id: int | None
    node_id: int | None
    entity_ref: str | None
    started_at: str
    ended_at: str | None
    duration_sec: int


class StudySessionDayOut(BaseModel):
    day: str
    total_sec: int
    by_kind: dict[str, int]


class StudySessionSummaryOut(BaseModel):
    days: list[StudySessionDayOut]
    today_sec: int
    week_sec: int


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _session_out(row: StudySession) -> StudySessionOut:
    return StudySessionOut(
        id=row.id,
        kind=StudySessionKind(row.kind),
        source=StudySessionSource(row.source),
        course_id=row.course_id,
        node_id=row.node_id,
        entity_ref=row.entity_ref,
        started_at=_iso(row.started_at) or "",
        ended_at=_iso(row.ended_at),
        duration_sec=row.duration_sec,
    )


def _load_session(db: Session, session_id: int, profile_id: int) -> StudySession:
    row = db.get(StudySession, session_id)
    if row is None or row.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="study session not found")
    return row


@router.post("", response_model=StudySessionOut, status_code=201)
def start_study_session(
    body: StudySessionStartIn, session: Session = Depends(get_session)
) -> StudySessionOut:
    profile = ensure_default_profile(session)
    row = sessions_service.start_session(
        session,
        profile.id,
        kind=body.kind,
        source=body.source,
        course_id=body.course_id,
        node_id=body.node_id,
        entity_ref=body.entity_ref,
    )
    session.commit()
    return _session_out(row)


@router.patch("/{session_id}", response_model=StudySessionOut)
def beat_study_session(
    session_id: int,
    body: StudySessionBeatIn,
    session: Session = Depends(get_session),
) -> StudySessionOut:
    profile = ensure_default_profile(session)
    row = _load_session(session, session_id, profile.id)
    sessions_service.beat_session(session, row, end=body.action == "end")
    session.commit()
    return _session_out(row)


@router.get("/summary", response_model=StudySessionSummaryOut)
def study_session_summary(
    days: int = 7, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    return sessions_service.session_summary(session, profile.id, days)
