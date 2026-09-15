from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.vocab import CourseOrigin
from ..domain.models import Course, Exercise, FsrsState, utcnow
from ..services.platform.profiles import ensure_default_profile
from ..services.study.exercise_kinds import CARD_KINDS
from .deps import get_session
from .flashcards import CardOut, card_out

router = APIRouter(prefix="/review", tags=["review"])


class DueCourseGroupOut(BaseModel):
    course_id: int
    course_title: str
    course_color: str | None
    due_count: int
    cards: list[CardOut]


class ReviewDueOut(BaseModel):
    total_due: int
    groups: list[DueCourseGroupOut]


@router.get("/due", response_model=ReviewDueOut)
def review_due(
    per_course: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    now = utcnow()
    statement = (
        select(Exercise, FsrsState, Course)
        .outerjoin(FsrsState, FsrsState.card_id == Exercise.id)
        .join(Course, Exercise.course_id == Course.id)
        .where(
            Exercise.profile_id == profile.id,
            Exercise.kind.in_(CARD_KINDS),
            (FsrsState.id.is_(None)) | (FsrsState.due_at <= now),
            Course.origin != CourseOrigin.SCRATCH.value,
        )
        .options(selectinload(Exercise.steps))
        .order_by(Exercise.id)
    )
    rows = session.execute(statement).all()
    grouped: dict[int, dict[str, Any]] = {}
    for card, state, course in rows:
        entry = grouped.setdefault(
            course.id,
            {
                "course_id": course.id,
                "course_title": course.title,
                "course_color": course.color,
                "due_count": 0,
                "cards": [],
            },
        )
        entry["due_count"] += 1
        if len(entry["cards"]) < per_course:
            entry["cards"].append(card_out(card, state))
    groups = sorted(grouped.values(), key=lambda entry: -entry["due_count"])
    return {
        "total_due": sum(entry["due_count"] for entry in groups),
        "groups": groups,
    }
