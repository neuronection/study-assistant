from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.vocab import ChatProposalStatus, CourseOrigin, PlanItemKind
from ..domain.models import (
    ChatMessage,
    ChatProposal,
    ChatSession,
    Course,
    Exercise,
    FsrsState,
    PlanItem,
    utcnow,
)
from ..services.platform import metrics
from ..services.platform.profiles import ensure_default_profile
from ..services.study.exercise_kinds import CARD_KINDS
from .deps import get_session

router = APIRouter(prefix="/notifications", tags=["notifications"])

MAX_DUE_REVIEWS = 10
MAX_PLAN_ITEMS = 10
MAX_EXAMS = 3


class DueReviewEntryOut(BaseModel):
    card_id: int
    kind: str
    course_id: int
    course_title: str


class PlanEntryOut(BaseModel):
    item_id: int
    title: str
    kind: PlanItemKind
    course_id: int
    course_title: str
    due_date: str
    overdue: bool


class ExamEntryOut(BaseModel):
    course_id: int
    course_title: str
    exam_date: str
    days_left: int


class NotificationsOut(BaseModel):
    due_cards: int
    due_reviews: list[DueReviewEntryOut]
    plan_today: list[PlanEntryOut]
    plan_overdue_count: int
    exams: list[ExamEntryOut]
    pending_proposals: int
    generated_at: str


@router.get("", response_model=NotificationsOut)
def notifications(session: Session = Depends(get_session)) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    now = utcnow()
    today = now.date()

    due_statement = (
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
        .order_by(FsrsState.due_at.nulls_first(), Exercise.id)
        .limit(MAX_DUE_REVIEWS)
    )
    due_rows = session.execute(due_statement).all()
    due_reviews = [
        DueReviewEntryOut(
            card_id=card.id,
            kind=card.kind,
            course_id=course.id,
            course_title=course.title,
        )
        for card, _state, course in due_rows
    ]
    due_cards = metrics.due_cards_count(session, profile.id)

    plan_rows = session.execute(
        select(PlanItem, Course)
        .join(Course, PlanItem.course_id == Course.id)
        .where(
            PlanItem.profile_id == profile.id,
            PlanItem.done_at.is_(None),
            PlanItem.due_date <= today,
        )
        .order_by(PlanItem.due_date, PlanItem.sort_key, PlanItem.id)
        .limit(MAX_PLAN_ITEMS)
    ).all()
    plan_today = [
        PlanEntryOut(
            item_id=item.id,
            title=item.title,
            kind=PlanItemKind(item.kind),
            course_id=item.course_id,
            course_title=course.title,
            due_date=item.due_date.isoformat(),
            overdue=item.due_date < today,
        )
        for item, course in plan_rows
    ]
    plan_overdue_count = len(
        session.execute(
            select(PlanItem.id).where(
                PlanItem.profile_id == profile.id,
                PlanItem.done_at.is_(None),
                PlanItem.due_date < today,
            )
        ).all()
    )

    exams = [
        ExamEntryOut(
            course_id=entry["course_id"],
            course_title=entry["course_title"],
            exam_date=entry["exam_date"],
            days_left=entry["days_left"],
        )
        for entry in metrics.exam_status(session, profile.id)[:MAX_EXAMS]
    ]

    pending_proposals = len(
        session.execute(
            select(ChatProposal.id)
            .join(ChatMessage, ChatProposal.message_id == ChatMessage.id)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(
                ChatSession.profile_id == profile.id,
                ChatProposal.status == ChatProposalStatus.PROPOSED.value,
            )
        ).all()
    )

    generated_at = datetime.now(UTC).isoformat()
    return {
        "due_cards": due_cards,
        "due_reviews": due_reviews,
        "plan_today": plan_today,
        "plan_overdue_count": plan_overdue_count,
        "exams": exams,
        "pending_proposals": pending_proposals,
        "generated_at": generated_at,
    }

