from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.vocab import CourseOrigin, GoalUnit, StudyLeechAction
from ..domain.models import Course, CourseFsrsOverride, Exercise, FsrsState, PlanItem, utcnow
from ..services.platform import metrics
from ..services.platform.profiles import ensure_default_profile
from ..services.study import fsrs_settings
from ..services.study.exercise_kinds import CARD_KINDS
from .deps import get_session

router = APIRouter(prefix="/study", tags=["study"])

MAX_REVIEW_COURSES = 5
MAX_PLAN_ROWS = 10
MAX_WEAK_CELLS = 3


class StudyPlanRowOut(BaseModel):
    item_id: str
    title: str
    course_id: str
    course_title: str
    due_date: str
    overdue: bool


class StudyWeakCellOut(BaseModel):
    course_id: str
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


def _review_course_titles(session: Session, profile_id: str) -> list[str]:
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
    profile_id: str,
    course: str | None,
) -> list[StudyWeakCellOut]:
    candidates: list[str] = []
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
        candidates.append(str(entry["course_id"]))
    for (course_id,) in session.execute(
        select(Course.id).order_by(Course.created_at, Course.id)
    ).all():
        candidates.append(str(course_id))

    seen: set[str] = set()
    ordered: list[str] = []
    for course_id in candidates:
        if course_id not in seen:
            seen.add(course_id)
            ordered.append(course_id)

    titles: dict[str, str] = {}
    for course_id, title in session.execute(select(Course.id, Course.title)).all():
        titles[course_id] = title
    cells: list[StudyWeakCellOut] = []
    for course_id in ordered:
        rows = metrics.answer_rows(session, profile_id, course_id)
        matrix = [cell for cell in metrics.weakness_matrix(rows) if cell["enough_data"]]
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
    course: str | None = Query(default=None),
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


class FsrsSettingsIn(BaseModel):
    desired_retention: float | None = Field(default=None, ge=0.70, le=0.97)
    maximum_interval_days: int | None = Field(default=None, ge=30, le=3650)
    new_per_day: int | None = Field(default=None, ge=0, le=999)
    reviews_per_day: int | None = Field(default=None, ge=0, le=9999)
    leech_threshold: int | None = Field(default=None, ge=1, le=20)
    leech_action: StudyLeechAction | None = None
    bury_siblings: bool | None = None
    load_balance: bool | None = None


class FsrsSettingsOut(BaseModel):
    desired_retention: float
    maximum_interval_days: int
    new_per_day: int
    reviews_per_day: int
    leech_threshold: int
    leech_action: str
    bury_siblings: bool
    load_balance: bool
    inherited: bool = True


def _fsrs_out(values: object, inherited: bool) -> FsrsSettingsOut:
    from ..services.study.fsrs_settings import FsrsValues

    assert isinstance(values, FsrsValues)
    return FsrsSettingsOut(
        desired_retention=values.desired_retention,
        maximum_interval_days=values.maximum_interval_days,
        new_per_day=values.new_per_day,
        reviews_per_day=values.reviews_per_day,
        leech_threshold=values.leech_threshold,
        leech_action=values.leech_action,
        bury_siblings=values.bury_siblings,
        load_balance=values.load_balance,
        inherited=inherited,
    )


def _course_for(session: Session, course_id: str, profile_id: str) -> Course:
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile_id:
        raise ValueError("course not found")
    return course


@router.get("/fsrs", response_model=FsrsSettingsOut)
def get_fsrs_settings(session: Session = Depends(get_session)) -> FsrsSettingsOut:
    profile = ensure_default_profile(session)
    return _fsrs_out(fsrs_settings.get_profile(session, profile.id), inherited=True)


@router.put("/fsrs", response_model=FsrsSettingsOut)
def put_fsrs_settings(
    body: FsrsSettingsIn,
    session: Session = Depends(get_session),
) -> FsrsSettingsOut:
    profile = ensure_default_profile(session)
    values = fsrs_settings.update_profile(
        session,
        profile.id,
        values={
            field: getattr(body, field)
            for field in body.model_fields_set
            if getattr(body, field) is not None
        },
    )
    session.commit()
    return _fsrs_out(values, inherited=True)


@router.get("/courses/{course_id}/fsrs", response_model=FsrsSettingsOut)
def get_course_fsrs(
    course_id: str,
    session: Session = Depends(get_session),
) -> FsrsSettingsOut:
    profile = ensure_default_profile(session)
    try:
        _course_for(session, course_id, profile.id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    override = session.scalar(
        select(CourseFsrsOverride).where(CourseFsrsOverride.course_id == course_id)
    )
    return _fsrs_out(
        fsrs_settings.resolve(session, profile.id, course_id),
        inherited=override is None,
    )


@router.put("/courses/{course_id}/fsrs", response_model=FsrsSettingsOut)
def put_course_fsrs(
    course_id: str,
    body: FsrsSettingsIn,
    session: Session = Depends(get_session),
) -> FsrsSettingsOut:
    profile = ensure_default_profile(session)
    try:
        _course_for(session, course_id, profile.id)
        values = fsrs_settings.set_course(
            session,
            course_id,
            values={
                field: getattr(body, field) for field in body.model_fields_set
            },
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    session.commit()
    return _fsrs_out(values, inherited=False)


@router.delete("/courses/{course_id}/fsrs", status_code=204)
def delete_course_fsrs(
    course_id: str,
    session: Session = Depends(get_session),
) -> None:
    profile = ensure_default_profile(session)
    try:
        _course_for(session, course_id, profile.id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    fsrs_settings.clear_course(session, course_id)
    session.commit()
