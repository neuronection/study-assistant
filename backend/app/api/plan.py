from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.vocab import PlanItemKind, PlanItemOrigin
from ..domain.models import Course, PlanItem, utcnow
from ..services.knowledge.tree import TreeService
from ..services.platform.profiles import ensure_default_profile
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
