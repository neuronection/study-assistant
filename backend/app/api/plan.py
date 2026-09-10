from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import PlanItemKind, PlanItemOrigin
from ..services.knowledge.courses import CourseError, commit_genesis  # noqa: F401
from ..services.platform.profiles import ensure_default_profile
from ..services.study.planner import (
    upcoming_items,
)
from .deps import get_session

router = APIRouter(prefix="/plan", tags=["plan"])

upcoming_router = APIRouter(tags=["plan"])


class PlanItemOut(BaseModel):
    id: int
    course_id: int
    node_id: int | None
    title: str
    detail: str | None
    kind: PlanItemKind
    due_date: date
    done_at: str | None
    origin: PlanItemOrigin
    sort_key: int


class PlanItemCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: PlanItemKind = PlanItemKind.STUDY
    due_date: date
    node_id: int | None = None
    detail: str | None = Field(default=None, max_length=500)


class PlanItemUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    kind: PlanItemKind | None = None
    due_date: date | None = None
    done: bool | None = None


class PlanGenerateOut(BaseModel):
    created: int
    items: list[PlanItemOut]


class UpcomingItemOut(BaseModel):
    id: int
    course_id: int
    course_title: str
    node_id: int | None
    title: str
    detail: str | None
    kind: PlanItemKind
    due_date: str
    origin: PlanItemOrigin


@router.get("/upcoming", response_model=list[UpcomingItemOut])
def plan_upcoming(
    days: int = 7, session: Session = Depends(get_session)
) -> list[UpcomingItemOut]:
    profile = ensure_default_profile(session)
    return [
        UpcomingItemOut(**entry) for entry in upcoming_items(session, profile.id, days)
    ]


