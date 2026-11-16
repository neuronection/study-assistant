from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ...core.vocab import CourseOrigin, PlanItemKind, PlanItemOrigin
from ...domain.models import (
    Course,
    Exercise,
    PlanItem,
    StudySession,
    utcnow,
)
from ...domain.models import (
    FsrsState as FsrsStateModel,
)
from ..knowledge.tree import TreeService
from ..platform.metrics import answer_rows, weakness_matrix
from .exercise_kinds import CARD_KINDS

WEEK_DAYS = 7
DEFAULT_MINUTES = 60
MAX_ITEMS_PER_DAY = 4
WEAK_ACCURACY = 0.7


@dataclass(frozen=True)
class Capacity:
    minutes: list[int]
    blackout_dates: set[date]
    light_week: bool

    def for_day(self, day: date) -> int:
        if day in self.blackout_dates:
            return 0
        minutes = self.minutes[day.weekday()]
        return minutes // 2 if self.light_week else minutes


@dataclass(frozen=True)
class WeekItem:
    day: date
    course_id: str
    course_title: str
    kind: str
    title: str
    detail: str | None
    minutes: int
    evidence: str
    fixed: bool = False


@dataclass
class WeekPreview:
    start: date
    end: date
    capacity: Capacity
    days: list[tuple[date, list[WeekItem]]]
    overflow: int
    existing_generated: int
    total_minutes: int


def _default_minutes(session: Session, profile_id: str) -> list[int]:
    since = utcnow() - timedelta(days=14)
    rows = session.execute(
        select(StudySession.duration_sec).where(
            StudySession.profile_id == profile_id,
            StudySession.started_at >= since,
        )
    ).scalars()
    values = [value for value in rows if value > 0]
    if not values:
        return [DEFAULT_MINUTES] * WEEK_DAYS
    average = max(15, min(240, int(median(values) / 60)))
    return [average] * WEEK_DAYS


def load_capacity(
    session: Session, profile_id: str, preferences: dict[str, Any] | None = None
) -> Capacity:
    raw = (preferences or {}).get("planner_capacity") or {}
    minutes = raw.get("minutes")
    if not isinstance(minutes, list) or len(minutes) != WEEK_DAYS:
        minutes = _default_minutes(session, profile_id)
    blackout: set[date] = set()
    for value in raw.get("blackout_dates", []) or []:
        try:
            blackout.add(date.fromisoformat(str(value)))
        except ValueError:
            continue
    return Capacity(
        minutes=list(minutes),
        blackout_dates=blackout,
        light_week=bool(raw.get("light_week")),
    )


def _exam_score(exam_date: date | None, today: date) -> int:
    if exam_date is None:
        return 0
    days = (exam_date - today).days
    if days < 0:
        return 0
    return max(0, 30 - days) * 2


def _weak_concepts(session: Session, profile_id: str, course_id: str) -> list[str]:
    rows = answer_rows(session, profile_id, course_id=course_id)
    cells = [
        cell
        for cell in weakness_matrix(rows)
        if cell.get("n", 0) >= 3 and float(cell.get("accuracy", 1.0)) < WEAK_ACCURACY
    ]
    cells.sort(key=lambda cell: float(cell.get("accuracy", 1.0)))
    return [str(cell["concept"]) for cell in cells[:2]]


def _first_untouched_node(
    session: Session, course_id: str, profile_id: str
) -> tuple[str, str] | None:
    tree = TreeService(session).tree(course_id, profile_id)
    stack = list(tree)
    while stack:
        entry = stack.pop(0)
        stack[:0] = entry.get("children", [])
        if entry.get("is_root"):
            continue
        counts = entry.get("counts") or {}
        if (
            counts.get("studied", 0) == 0
            and counts.get("notes", 0) == 0
            and counts.get("quizzes", 0) == 0
            and counts.get("exercises", 0) == 0
        ):
            return str(entry["id"]), str(entry["title"])
    return None


def _due_count(session: Session, course_id: str) -> int:
    now = utcnow()
    return int(
        session.scalar(
            select(func.count(Exercise.id))
            .outerjoin(FsrsStateModel, FsrsStateModel.card_id == Exercise.id)
            .where(
                Exercise.course_id == course_id,
                Exercise.kind.in_(CARD_KINDS),
                or_(
                    FsrsStateModel.id.is_(None),
                    FsrsStateModel.due_at <= now,
                ),
            )
        )
        or 0
    )


@dataclass
class _Candidate:
    course_id: str
    course_title: str
    kind: PlanItemKind
    title: str
    detail: str | None
    minutes: int
    evidence: str
    score: int


def preview_week(
    session: Session,
    profile_id: str,
    *,
    start: date | None = None,
    preferences: dict[str, Any] | None = None,
) -> WeekPreview:
    today = utcnow().date()
    first = start or today
    end = first + timedelta(days=WEEK_DAYS - 1)
    capacity = load_capacity(session, profile_id, preferences)
    courses = list(
        session.scalars(
            select(Course).where(
                Course.profile_id == profile_id,
                Course.origin != CourseOrigin.SCRATCH.value,
            )
        )
    )
    candidates: list[_Candidate] = []
    for course in courses:
        exam_score = _exam_score(course.exam_date, today)
        due = _due_count(session, course.id)
        if due:
            candidates.append(
                _Candidate(
                    course.id,
                    course.title,
                    PlanItemKind.REVIEW,
                    f"Review {due} due cards",
                    f"{due} cards due",
                    min(60, max(15, (due + 1) // 2)),
                    f"{due} due cards",
                    100 + due + exam_score,
                )
            )
        for concept in _weak_concepts(session, profile_id, course.id):
            candidates.append(
                _Candidate(
                    course.id,
                    course.title,
                    PlanItemKind.PRACTICE,
                    f"Practice {concept}",
                    "weak concept",
                    25,
                    f"weak: {concept}",
                    80 + exam_score,
                )
            )
        node = _first_untouched_node(session, course.id, profile_id)
        if node is not None:
            node_id, title = node
            candidates.append(
                _Candidate(
                    course.id,
                    course.title,
                    PlanItemKind.STUDY,
                    f"Study {title}",
                    node_id,
                    45,
                    "not studied yet",
                    50 + exam_score,
                )
            )
    candidates.sort(key=lambda entry: (-entry.score, entry.course_title, entry.title))

    fixed = list(
        session.scalars(
            select(PlanItem).where(
                PlanItem.profile_id == profile_id,
                PlanItem.due_date >= first,
                PlanItem.due_date <= end,
                PlanItem.origin != PlanItemOrigin.GENERATED.value,
            )
        )
    )
    existing_generated = int(
        session.scalar(
            select(func.count(PlanItem.id)).where(
                PlanItem.profile_id == profile_id,
                PlanItem.due_date >= first,
                PlanItem.due_date <= end,
                PlanItem.origin == PlanItemOrigin.GENERATED.value,
                PlanItem.done_at.is_(None),
            )
        )
        or 0
    )
    by_day: dict[date, list[WeekItem]] = {first + timedelta(days=i): [] for i in range(WEEK_DAYS)}
    used: dict[date, int] = dict.fromkeys(by_day, 0)
    for item in fixed:
        day = item.due_date
        if day not in by_day:
            continue
        minutes = 25 if item.kind == PlanItemKind.REVIEW.value else 45
        by_day[day].append(
            WeekItem(
                day=day,
                course_id=item.course_id,
                course_title=next(
                    (course.title for course in courses if course.id == item.course_id),
                    "",
                ),
                kind=item.kind,
                title=item.title,
                detail=item.detail,
                minutes=minutes,
                evidence="manual",
                fixed=True,
            )
        )
        used[day] += minutes

    overflow = 0
    per_course_day: dict[tuple[date, str], int] = {}
    for candidate in candidates:
        placed = False
        for day in (first + timedelta(days=i) for i in range(WEEK_DAYS)):
            if len(by_day[day]) >= MAX_ITEMS_PER_DAY:
                continue
            if used[day] + candidate.minutes > capacity.for_day(day):
                continue
            if per_course_day.get((day, candidate.course_id), 0) >= 2:
                continue
            by_day[day].append(
                WeekItem(
                    day=day,
                    course_id=candidate.course_id,
                    course_title=candidate.course_title,
                    kind=candidate.kind.value,
                    title=candidate.title,
                    detail=candidate.detail,
                    minutes=candidate.minutes,
                    evidence=candidate.evidence,
                )
            )
            used[day] += candidate.minutes
            per_course_day[(day, candidate.course_id)] = (
                per_course_day.get((day, candidate.course_id), 0) + 1
            )
            placed = True
            break
        if not placed:
            overflow += 1
    return WeekPreview(
        start=first,
        end=end,
        capacity=capacity,
        days=[(day, by_day[day]) for day in sorted(by_day)],
        overflow=overflow,
        existing_generated=existing_generated,
        total_minutes=sum(item.minutes for items in by_day.values() for item in items),
    )


def commit_week(session: Session, profile_id: str, preview: WeekPreview) -> tuple[int, int]:
    session.execute(
        delete(PlanItem).where(
            PlanItem.profile_id == profile_id,
            PlanItem.due_date >= preview.start,
            PlanItem.due_date <= preview.end,
            PlanItem.origin == PlanItemOrigin.GENERATED.value,
            PlanItem.done_at.is_(None),
        )
    )
    created = 0
    for day, items in preview.days:
        for index, item in enumerate(items):
            if item.fixed:
                continue
            session.add(
                PlanItem(
                    profile_id=profile_id,
                    course_id=item.course_id,
                    title=item.title[:300],
                    detail=(item.detail or item.evidence)[:500],
                    kind=item.kind,
                    due_date=day,
                    origin=PlanItemOrigin.GENERATED.value,
                    sort_key=index,
                )
            )
            created += 1
    return created, preview.existing_generated
