from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.vocab import CourseOrigin, GoalUnit
from ..domain.models import Course, Exercise, FsrsState, PlanItem, utcnow
from ..services.platform import metrics
from ..services.platform.profiles import ensure_default_profile
from ..services.study.exercise_kinds import CARD_KINDS
from .deps import get_session

router = APIRouter(prefix="/study", tags=["study"])

MAX_REVIEW_COURSES = 5
MAX_PLAN_ROWS = 10
MAX_WEAK_CELLS = 3


class StudyPlanRowOut(BaseModel):
    item_id: int
    title: str
    course_id: int
    course_title: str
    due_date: str
    overdue: bool


class StudyWeakCellOut(BaseModel):
    course_id: int
    course_title: str
    concept: str
    skill: str
    n: int
    accuracy: float
    weakness_score: float


class StudyNextOut(BaseModel):
    due_cards: int
    review_courses: list[str]
    plan_rows: list[StudyPlanRowOut]
    weak_cells: list[StudyWeakCellOut]
    goal_unit: str
    goal_done: int
    goal_target: int
    streak: int


def _review_course_titles(session: Session, profile_id: int) -> list[str]:
    now = utcnow()
    rows = session.execute(
        select(Course.title)
        .join(Exercise, Exercise.course_id == Course.id)
        .outerjoin(FsrsState, FsrsState.card_id == Exercise.id)
        .where(
            Exercise.profile_id == profile_id,
            Exercise.kind.in_(CARD_KINDS),
            (FsrsState.id.is_(None)) | (FsrsState.due_at <= now),
            Course.origin != CourseOrigin.SCRATCH.value,
        )
        .distinct()
        .limit(MAX_REVIEW_COURSES)
    ).all()
    return [row[0] for row in rows]


def _weak_cells(
    session: Session,
    profile_id: int,
    course: int | None,
) -> list[StudyWeakCellOut]:
    candidates: list[int] = []
    if course is not None:
        candidates.append(course)
    exam_entries = sorted(
        metrics.exam_status(session, profile_id),
        key=lambda entry: (
            entry["days_left"] is None,
            entry["days_left"] if entry["days_left"] is not None else 0,
        ),
    )
    for entry in exam_entries:
        candidates.append(entry["course_id"])
    for (course_id,) in session.execute(select(Course.id).order_by(Course.id)).all():
        candidates.append(course_id)

    seen: set[int] = set()
    ordered: list[int] = []
    for course_id in candidates:
        if course_id not in seen:
            seen.add(course_id)
            ordered.append(course_id)

    titles: dict[int, str] = {}
    for course_id, title in session.execute(
        select(Course.id, Course.title)
    ).all():
        titles[course_id] = title
    cells: list[StudyWeakCellOut] = []
    for course_id in ordered:
        rows = metrics.answer_rows(session, profile_id, course_id)
        matrix = [
            cell
            for cell in metrics.weakness_matrix(rows)
            if cell["enough_data"]
        ]
        matrix.sort(key=lambda cell: -cell["weakness_score"])
        for cell in matrix:
            cells.append(
                StudyWeakCellOut(
                    course_id=course_id,
                    course_title=titles.get(course_id, ""),
                    concept=cell["concept"],
                    skill=cell["skill"],
                    n=cell["n"],
                    accuracy=cell["accuracy"],
                    weakness_score=cell["weakness_score"],
                )
            )
            if len(cells) >= MAX_WEAK_CELLS:
                return cells
    return cells


@router.get("/next", response_model=StudyNextOut)
def study_next(
    course: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    now = utcnow()
    today = now.date()

    plan_rows = session.execute(
        select(PlanItem, Course)
        .join(Course, PlanItem.course_id == Course.id)
        .where(
            PlanItem.profile_id == profile.id,
            PlanItem.done_at.is_(None),
            PlanItem.due_date <= today,
        )
        .order_by(PlanItem.due_date, PlanItem.sort_key, PlanItem.id)
        .limit(MAX_PLAN_ROWS)
    ).all()

    overview = metrics.overview(session, profile.id)
    unit = GoalUnit(overview["unit"])
    today_entry = overview["today"]
    if unit == GoalUnit.MINUTES:
        goal_done = int(today_entry["study_seconds"] // 60)
        goal_target = int(overview["minutes_per_day"])
    else:
        goal_done = int(today_entry["answers_n"])
        goal_target = int(overview["answers_per_day"])

    return {
        "due_cards": metrics.due_cards_count(session, profile.id),
        "review_courses": _review_course_titles(session, profile.id),
        "plan_rows": [
            StudyPlanRowOut(
                item_id=item.id,
                title=item.title,
                course_id=item.course_id,
                course_title=course.title,
                due_date=item.due_date.isoformat(),
                overdue=item.due_date < today,
            )
            for item, course in plan_rows
        ],
        "weak_cells": _weak_cells(session, profile.id, course),
        "goal_unit": unit.value,
        "goal_done": goal_done,
        "goal_target": goal_target,
        "streak": int(overview["streak"]),
    }
