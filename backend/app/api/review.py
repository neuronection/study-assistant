from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.vocab import CourseOrigin, ReviewOrder, ReviewSource
from ..domain.models import (
    Course,
    Exercise,
    FsrsState,
    ReviewFilter,
    ReviewLog,
    utcnow,
)
from ..services.knowledge.tree import TreeService
from ..services.platform.profiles import ensure_default_profile
from ..services.study import fsrs_settings
from ..services.study.exercise_kinds import CARD_KINDS
from .deps import get_session
from .flashcards import CardOut, card_out

router = APIRouter(prefix="/review", tags=["review"])


class DueCourseGroupOut(BaseModel):
    course_id: str
    course_title: str
    course_color: str | None
    due_count: int
    cards: list[CardOut]


class ReviewDueOut(BaseModel):
    total_due: int
    groups: list[DueCourseGroupOut]
    capped: bool = False
    remaining_today: int | None = None
    preview: bool = False


class ReviewFilterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    course_id: str | None = None
    node_id: str | None = None
    include_not_due: bool = False
    due_window_days: int | None = Field(default=None, ge=1, le=90)
    limit: int | None = Field(default=None, ge=1, le=500)
    sort_order: ReviewOrder = ReviewOrder.DUE
    kinds: list[str] | None = None


class ReviewFilterOut(BaseModel):
    id: str
    name: str
    course_id: str | None
    node_id: str | None
    include_not_due: bool
    due_window_days: int | None
    limit: int | None
    sort_order: str
    kinds: list[str] | None


class PreviewIn(BaseModel):
    rating: int = Field(ge=1, le=4)


def _filter_out(row: ReviewFilter) -> ReviewFilterOut:
    return ReviewFilterOut(
        id=row.id,
        name=row.name,
        course_id=row.course_id,
        node_id=row.node_id,
        include_not_due=row.include_not_due,
        due_window_days=row.due_window_days,
        limit=row.limit,
        sort_order=row.sort_order,
        kinds=list(row.kinds or []) or None,
    )


@router.get("/filters", response_model=list[ReviewFilterOut])
def list_filters(session: Session = Depends(get_session)) -> list[ReviewFilterOut]:
    profile = ensure_default_profile(session)
    rows = session.scalars(
        select(ReviewFilter)
        .where(ReviewFilter.profile_id == profile.id)
        .order_by(ReviewFilter.created_at, ReviewFilter.id)
    )
    return [_filter_out(row) for row in rows]


@router.post("/filters", response_model=ReviewFilterOut, status_code=201)
def create_filter(
    body: ReviewFilterIn,
    session: Session = Depends(get_session),
) -> ReviewFilterOut:
    profile = ensure_default_profile(session)
    if body.course_id is not None:
        course = session.get(Course, body.course_id)
        if course is None or course.profile_id != profile.id:
            raise HTTPException(status_code=404, detail="course not found")
    row = ReviewFilter(
        profile_id=profile.id,
        name=body.name.strip(),
        course_id=body.course_id,
        node_id=body.node_id,
        include_not_due=body.include_not_due,
        due_window_days=body.due_window_days,
        limit=body.limit,
        sort_order=body.sort_order.value,
        kinds=body.kinds,
    )
    session.add(row)
    session.commit()
    return _filter_out(row)


@router.delete("/filters/{filter_id}", status_code=204)
def delete_filter(filter_id: str, session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    row = session.get(ReviewFilter, filter_id)
    if row is None or row.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="filter not found")
    session.delete(row)
    session.commit()


@router.get("/due", response_model=ReviewDueOut)
def review_due(
    per_course: int = Query(default=20, ge=1, le=100),
    course_id: str | None = None,
    node_id: str | None = None,
    include_not_due: bool = False,
    due_window_days: int | None = Query(default=None, ge=1, le=90),
    limit: int | None = Query(default=None, ge=1, le=500),
    sort_order: ReviewOrder = ReviewOrder.DUE,
    filter_id: str | None = None,
    respect_caps: bool = True,
    session: Session = Depends(get_session),
) -> ReviewDueOut:
    profile = ensure_default_profile(session)
    kinds: list[str] | None = None
    if filter_id is not None:
        saved = session.get(ReviewFilter, filter_id)
        if saved is None or saved.profile_id != profile.id:
            raise HTTPException(status_code=404, detail="filter not found")
        course_id = saved.course_id
        node_id = saved.node_id
        include_not_due = saved.include_not_due
        due_window_days = saved.due_window_days
        limit = saved.limit
        sort_order = ReviewOrder(saved.sort_order)
        kinds = list(saved.kinds or []) or None

    now = utcnow()
    window = now + timedelta(days=due_window_days or 7)
    due_condition = (
        or_(FsrsState.id.is_(None), FsrsState.due_at <= window)
        if include_not_due
        else or_(FsrsState.id.is_(None), FsrsState.due_at <= now)
    )
    statement = (
        select(Exercise, FsrsState, Course)
        .outerjoin(FsrsState, FsrsState.card_id == Exercise.id)
        .join(Course, Exercise.course_id == Course.id)
        .where(
            Exercise.profile_id == profile.id,
            Exercise.kind.in_(kinds if kinds is not None else CARD_KINDS),
            due_condition,
        )
        .options(selectinload(Exercise.steps))
    )
    if course_id is not None:
        statement = statement.where(Exercise.course_id == course_id)
    else:
        statement = statement.where(Course.origin != CourseOrigin.SCRATCH.value)
    if node_id is not None:
        try:
            scope = TreeService(session).scoped_node_ids(node_id, include_children=True)
        except Exception as error:
            raise HTTPException(status_code=404, detail="node not found") from error
        statement = statement.where(Exercise.node_id.in_(scope))
    if sort_order is ReviewOrder.DUE:
        statement = statement.order_by(
            FsrsState.due_at.nulls_first(), Exercise.created_at, Exercise.id
        )
    elif sort_order is ReviewOrder.OLDEST:
        statement = statement.order_by(Exercise.created_at, Exercise.id)
    else:
        statement = statement.order_by(func.random())

    rows = list(session.execute(statement).all())
    remaining_today: int | None = None
    capped = False
    if respect_caps:
        values = fsrs_settings.get_profile(session, profile.id)
        if values.reviews_per_day > 0:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            reviewed = (
                session.scalar(
                    select(func.count(ReviewLog.id))
                    .join(Exercise, Exercise.id == ReviewLog.card_id)
                    .where(
                        Exercise.profile_id == profile.id,
                        ReviewLog.reviewed_at >= start,
                        ReviewLog.source == ReviewSource.REVIEW.value,
                    )
                )
                or 0
            )
            remaining_today = max(0, values.reviews_per_day - int(reviewed))
            if remaining_today == 0:
                rows = []
                capped = True
            else:
                rows = rows[:remaining_today]

    grouped: dict[str, dict[str, Any]] = {}
    card_limit = limit or per_course
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
        if len(entry["cards"]) < card_limit:
            entry["cards"].append(card_out(card, state))
    groups = [
        DueCourseGroupOut(**entry)
        for entry in sorted(grouped.values(), key=lambda entry: -entry["due_count"])
    ]
    return ReviewDueOut(
        total_due=sum(entry.due_count for entry in groups),
        groups=groups,
        capped=capped,
        remaining_today=remaining_today,
        preview=include_not_due,
    )


@router.post("/preview/{card_id}")
def preview_card(
    card_id: str,
    body: PreviewIn,
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    profile = ensure_default_profile(session)
    card = session.scalar(
        select(Exercise).where(
            Exercise.id == card_id,
            Exercise.profile_id == profile.id,
            Exercise.kind.in_(CARD_KINDS),
        )
    )
    if card is None:
        raise HTTPException(status_code=404, detail="card not found")
    session.add(
        ReviewLog(
            card_id=card.id,
            rating=body.rating,
            interval_days=0.0,
            elapsed_days=0.0,
            source=ReviewSource.CRAM_PREVIEW.value,
            reviewed_at=utcnow(),
        )
    )
    session.commit()
    return {"logged": True}
