from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.vocab import PlanItemKind, PlanItemOrigin
from ..domain.models import Course, PlanItem, utcnow
from ..services.knowledge.tree import TreeService
from ..services.platform.profiles import ensure_default_profile
from ..services.study import adaptive_plan
from ..services.study.ics_import import (
    IcsEvent,
    IcsImportError,
    IcsPreview,
    apply_preview,
    parse_ics,
)
from ..services.study.planner import (
    PlannerError,
    build_course_ics,
    generate_plan,
    upcoming_items,
)
from .deps import get_session

router = APIRouter(prefix="/plan", tags=["plan"])

upcoming_router = APIRouter(tags=["plan"])

courses_plan_router = APIRouter(tags=["courses"])


class PlanItemOut(BaseModel):
    id: str
    course_id: str
    node_id: str | None
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
    node_id: str | None = None
    detail: str | None = Field(default=None, max_length=500)


class PlanItemUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    kind: PlanItemKind | None = None
    due_date: date | None = None
    done: bool | None = None


class PlanGenerateOut(BaseModel):
    created: int
    items: list[PlanItemOut]


class IcsEventOut(BaseModel):
    uid: str
    title: str
    date: date
    time: str | None
    detail: str
    kind: PlanItemKind


class IcsExamCandidateOut(BaseModel):
    uid: str
    title: str
    date: date


class IcsPreviewOut(BaseModel):
    events: list[IcsEventOut]
    exam_candidates: list[IcsExamCandidateOut]
    total_events: int
    skipped: int


class IcsImportOut(BaseModel):
    created: int
    updated: int
    exam_date: date | None = None


class UpcomingItemOut(BaseModel):
    id: str
    course_id: str
    course_title: str
    node_id: str | None
    title: str
    detail: str | None
    kind: PlanItemKind
    due_date: str
    origin: PlanItemOrigin


def _item_out(item: PlanItem) -> PlanItemOut:
    return PlanItemOut(
        id=item.id,
        course_id=item.course_id,
        node_id=item.node_id,
        title=item.title,
        detail=item.detail,
        kind=PlanItemKind(item.kind),
        due_date=item.due_date,
        done_at=item.done_at.isoformat() if item.done_at else None,
        origin=PlanItemOrigin(item.origin),
        sort_key=item.sort_key,
    )


@router.get("/upcoming", response_model=list[UpcomingItemOut])
def plan_upcoming(days: int = 7, session: Session = Depends(get_session)) -> list[UpcomingItemOut]:
    profile = ensure_default_profile(session)
    return [UpcomingItemOut(**entry) for entry in upcoming_items(session, profile.id, days)]


async def _read_calendar(file: UploadFile) -> str:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="the calendar file is empty")
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="calendar exceeds the 2 MB limit")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=422, detail="calendar must be UTF-8 text") from error


def _owned_course(session: Session, course_id: str) -> Course:
    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    return course


def _event_out(event: IcsEvent) -> IcsEventOut:
    detail_parts = [
        part
        for part in (event.start.strftime("%H:%M") if event.start else None, event.location)
        if part
    ]
    return IcsEventOut(
        uid=event.uid,
        title=event.summary,
        date=event.day,
        time=event.start.strftime("%H:%M") if event.start else None,
        detail=" · ".join(detail_parts),
        kind=PlanItemKind.MILESTONE if event.exam else PlanItemKind.STUDY,
    )


def _preview_out(preview: IcsPreview) -> IcsPreviewOut:
    return IcsPreviewOut(
        events=[_event_out(event) for event in preview.events],
        exam_candidates=[
            IcsExamCandidateOut(uid=event.uid, title=event.summary, date=event.day)
            for event in preview.exam_candidates
        ],
        total_events=preview.total_events,
        skipped=preview.skipped,
    )


@courses_plan_router.post(
    "/courses/{course_id}/plan/import-ics/preview", response_model=IcsPreviewOut
)
async def preview_course_ics(
    course_id: str,
    file: UploadFile,
    session: Session = Depends(get_session),
) -> IcsPreviewOut:
    _owned_course(session, course_id)
    text = await _read_calendar(file)
    try:
        return _preview_out(parse_ics(text))
    except IcsImportError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@courses_plan_router.post("/courses/{course_id}/plan/import-ics", response_model=IcsImportOut)
async def import_course_ics(
    course_id: str,
    file: UploadFile,
    confirm_exam: bool = False,
    session: Session = Depends(get_session),
) -> IcsImportOut:
    course = _owned_course(session, course_id)
    text = await _read_calendar(file)
    try:
        preview = parse_ics(text)
        created, updated, exam_date = apply_preview(
            session, course, preview, confirm_exam=confirm_exam
        )
    except IcsImportError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return IcsImportOut(created=created, updated=updated, exam_date=exam_date)


@courses_plan_router.get("/courses/{course_id}/plan.ics")
def export_course_plan_ics(course_id: str, session: Session = Depends(get_session)) -> Response:
    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    ics = build_course_ics(session, course)
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="plan-{course_id}.ics"'},
    )


@courses_plan_router.get("/courses/{course_id}/plan", response_model=list[PlanItemOut])
def list_course_plan(course_id: str, session: Session = Depends(get_session)) -> list[PlanItemOut]:
    profile = ensure_default_profile(session)
    items = session.scalars(
        select(PlanItem)
        .where(PlanItem.course_id == course_id, PlanItem.profile_id == profile.id)
        .order_by(PlanItem.due_date, PlanItem.sort_key, PlanItem.id)
    )
    return [_item_out(item) for item in items]


@courses_plan_router.post("/courses/{course_id}/plan", response_model=PlanItemOut, status_code=201)
def create_plan_item(
    course_id: str, body: PlanItemCreateIn, session: Session = Depends(get_session)
) -> PlanItemOut:
    profile = ensure_default_profile(session)
    if body.node_id is not None:
        try:
            placement = TreeService(session).placement_node(course_id, body.node_id)
        except Exception as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if placement is None:
            raise HTTPException(status_code=422, detail="node not in this course")
    item = PlanItem(
        profile_id=profile.id,
        course_id=course_id,
        node_id=body.node_id,
        title=body.title.strip()[:300] or "Plan item",
        detail=body.detail,
        kind=body.kind.value,
        due_date=body.due_date,
        origin=PlanItemOrigin.MANUAL.value,
        sort_key=0,
    )
    session.add(item)
    session.commit()
    return _item_out(item)


@courses_plan_router.patch("/courses/{course_id}/plan/{item_id}", response_model=PlanItemOut)
def update_plan_item(
    course_id: str,
    item_id: str,
    body: PlanItemUpdateIn,
    session: Session = Depends(get_session),
) -> PlanItemOut:
    profile = ensure_default_profile(session)
    item = session.get(PlanItem, item_id)
    if item is None or item.course_id != course_id or item.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="plan item not found")
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="title cannot be empty")
        item.title = title[:300]
    if body.kind is not None:
        item.kind = body.kind.value
    if body.due_date is not None:
        item.due_date = body.due_date
    if body.done is not None:
        item.done_at = utcnow() if body.done else None
    session.commit()
    return _item_out(item)


@courses_plan_router.delete("/courses/{course_id}/plan/{item_id}", status_code=204)
def delete_plan_item(course_id: str, item_id: str, session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    item = session.get(PlanItem, item_id)
    if item is None or item.course_id != course_id or item.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="plan item not found")
    session.delete(item)
    session.commit()


@courses_plan_router.post("/courses/{course_id}/plan/generate", response_model=PlanGenerateOut)
def generate_course_plan(
    course_id: str, session: Session = Depends(get_session)
) -> PlanGenerateOut:
    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    try:
        items = generate_plan(session, course, profile.id)
    except PlannerError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return PlanGenerateOut(created=len(items), items=[_item_out(item) for item in items])


class WeekPlanItemOut(BaseModel):
    day: date
    course_id: str
    course_title: str
    kind: str
    title: str
    detail: str | None
    minutes: int
    evidence: str
    fixed: bool


class WeekPlanDayOut(BaseModel):
    day: date
    minutes: int
    items: list[WeekPlanItemOut]


class WeekPlanPreviewOut(BaseModel):
    start: date
    end: date
    capacity_minutes: list[int]
    light_week: bool
    days: list[WeekPlanDayOut]
    overflow: int
    existing_generated: int
    total_minutes: int


class WeekPlanCommitOut(BaseModel):
    created: int
    replaced: int


class WeekPlanIn(BaseModel):
    start: date | None = None


class CapacityIn(BaseModel):
    minutes: list[int] = Field(min_length=7, max_length=7)
    blackout_dates: list[str] = Field(default_factory=list)
    light_week: bool = False


class CapacityOut(CapacityIn):
    pass


def _week_out(preview: adaptive_plan.WeekPreview) -> WeekPlanPreviewOut:
    return WeekPlanPreviewOut(
        start=preview.start,
        end=preview.end,
        capacity_minutes=preview.capacity.minutes,
        light_week=preview.capacity.light_week,
        days=[
            WeekPlanDayOut(
                day=day,
                minutes=sum(item.minutes for item in items),
                items=[
                    WeekPlanItemOut(
                        day=item.day,
                        course_id=item.course_id,
                        course_title=item.course_title,
                        kind=item.kind,
                        title=item.title,
                        detail=item.detail,
                        minutes=item.minutes,
                        evidence=item.evidence,
                        fixed=item.fixed,
                    )
                    for item in items
                ],
            )
            for day, items in preview.days
        ],
        overflow=preview.overflow,
        existing_generated=preview.existing_generated,
        total_minutes=preview.total_minutes,
    )


@router.post("/week/preview", response_model=WeekPlanPreviewOut)
def preview_week_plan(
    body: WeekPlanIn | None = None,
    session: Session = Depends(get_session),
) -> WeekPlanPreviewOut:
    profile = ensure_default_profile(session)
    preview = adaptive_plan.preview_week(
        session,
        profile.id,
        start=body.start if body is not None else None,
        preferences=dict(profile.preferences or {}),
    )
    return _week_out(preview)


@router.post("/week/commit", response_model=WeekPlanCommitOut)
def commit_week_plan(
    body: WeekPlanIn | None = None,
    session: Session = Depends(get_session),
) -> WeekPlanCommitOut:
    profile = ensure_default_profile(session)
    preview = adaptive_plan.preview_week(
        session,
        profile.id,
        start=body.start if body is not None else None,
        preferences=dict(profile.preferences or {}),
    )
    created, replaced = adaptive_plan.commit_week(session, profile.id, preview)
    session.commit()
    return WeekPlanCommitOut(created=created, replaced=replaced)


@router.get("/capacity", response_model=CapacityOut)
def get_planner_capacity(session: Session = Depends(get_session)) -> CapacityOut:
    profile = ensure_default_profile(session)
    capacity = adaptive_plan.load_capacity(session, profile.id, dict(profile.preferences or {}))
    return CapacityOut(
        minutes=capacity.minutes,
        blackout_dates=[day.isoformat() for day in sorted(capacity.blackout_dates)],
        light_week=capacity.light_week,
    )


@router.put("/capacity", response_model=CapacityOut)
def put_planner_capacity(
    body: CapacityIn,
    session: Session = Depends(get_session),
) -> CapacityOut:
    profile = ensure_default_profile(session)
    if any(minute < 0 or minute > 720 for minute in body.minutes):
        raise HTTPException(status_code=422, detail="minutes must be between 0 and 720")
    prefs = dict(profile.preferences or {})
    prefs["planner_capacity"] = {
        "minutes": body.minutes,
        "blackout_dates": body.blackout_dates,
        "light_week": body.light_week,
    }
    from ..domain.preferences import PreferencesError, validate_preferences

    try:
        validate_preferences(prefs)
    except PreferencesError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    profile.preferences = prefs
    session.commit()
    return CapacityOut(**body.model_dump())
