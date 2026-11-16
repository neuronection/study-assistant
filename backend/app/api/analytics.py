import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.vocab import (
    AnalyticsExportFormat,
    GoalUnit,
    ItemFlag,
    RecommendationKind,
    ReviewSource,
    SpeedLabel,
    SpeedQuadrant,
)
from ..domain.models import AiInteraction, Exercise, FsrsState, ReviewLog, utcnow
from ..services.platform import metrics
from ..services.platform.profiles import ensure_default_profile
from ..services.study import fsrs_settings
from ..services.study.exercise_kinds import CARD_KINDS
from .deps import get_session

router = APIRouter(prefix="/analytics", tags=["analytics"])


class GoalIn(BaseModel):
    unit: GoalUnit | None = None
    answers_per_day: int | None = Field(default=None, ge=1, le=500)
    minutes_per_day: int | None = Field(default=None, ge=1, le=1440)


class DayActivityOut(BaseModel):
    day: str
    answers_n: int
    correct_n: int
    cards_reviewed: int
    minutes: float
    study_seconds: int
    xp: int


class OverviewOut(BaseModel):
    today: DayActivityOut
    unit: GoalUnit
    answers_per_day: int
    minutes_per_day: int
    streak: int
    total_xp: int
    level: int
    due_cards: int
    study_seconds_week: int
    history: list[DayActivityOut]


class MostBehindNodeOut(BaseModel):
    id: str
    title: str


class ExamStatusOut(BaseModel):
    course_id: str
    course_title: str
    exam_date: str
    days_left: int
    total_nodes: int
    engaged_nodes: int
    remaining_nodes: int
    nodes_per_day: float | None
    on_track: bool
    most_behind_node: MostBehindNodeOut | None
    readiness: int | None = None
    readiness_state: str = "not_enough_data"
    trend: str | None = None
    weakest: list[str] = Field(default_factory=list)
    answers_in_scope: int = 0


class WeaknessCellOut(BaseModel):
    concept: str
    concept_id: str | None
    skill: str
    n: int
    accuracy: float
    avg_time_ratio: float | None
    last_seen_at: str
    weakness_score: float
    enough_data: bool


class ErrorTagStatOut(BaseModel):
    tag: str
    total: int
    recent_7d: int
    previous_7d: int
    trend: int
    last_seen_at: str


class SpeedAccuracyCellOut(BaseModel):
    concept: str
    n: int
    accuracy: float
    avg_time_ratio: float
    speed: SpeedLabel
    quadrant: SpeedQuadrant


class DiagnosticsOut(BaseModel):
    weakness_matrix: list[WeaknessCellOut]
    error_profile: list[ErrorTagStatOut]
    speed_accuracy: list[SpeedAccuracyCellOut]
    skills: list[str]


class RecommendationOut(BaseModel):
    kind: RecommendationKind
    priority: int
    title_key: str | None = None
    concept: str | None = None
    skill: str | None = None
    evidence: dict[str, Any]


class ItemStatOut(BaseModel):
    question_id: str
    activity_id: str
    n_attempts: int
    p_correct: float
    discrimination: float | None = None
    distractor_efficiency: float | None = None
    avg_time_ms: int | None
    avg_time_ratio: float | None
    distractor_selection: dict[str, int] | None
    flag: ItemFlag
    elo_outlier: bool = False
    stem_excerpt: str


class AnalyticsExportOut(BaseModel):
    version: int = 1
    generated_at: str
    course_id: str | None = None
    daily: list[DayActivityOut]
    concepts: list[WeaknessCellOut]
    items: list[ItemStatOut]


class GoalOut(BaseModel):
    unit: GoalUnit
    answers_per_day: int
    minutes_per_day: int


class MaterializeOut(BaseModel):
    status: str


class CostTaskOut(BaseModel):
    task: str
    calls: int
    tokens_in: int
    tokens_out: int
    cost_micros: int
    models: dict[str, int]
    monthly_cap_micros: int | None = None


class CostCallOut(BaseModel):
    id: str
    task: str | None
    model: str | None
    resolved_model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_micros: int | None
    price_source: str
    outcome: str | None
    created_at: str


class CostsOut(BaseModel):
    month: str
    per_task: list[CostTaskOut]
    total_micros: int
    recent: list[CostCallOut]


@router.get("/overview", response_model=OverviewOut)
def overview(session: Session = Depends(get_session)) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    result = metrics.overview(session, profile.id)
    session.commit()
    return result


@router.get("/exams", response_model=list[ExamStatusOut])
def exams(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return metrics.exam_status(session, profile.id)


@router.get("/diagnostics", response_model=DiagnosticsOut)
def diagnostics(
    course_id: str | None = None, session: Session = Depends(get_session)
) -> dict[str, Any]:
    from ..services.study.teachback import teach_back_cells

    profile = ensure_default_profile(session)
    rows = metrics.answer_rows(session, profile.id, course_id)
    matrix = metrics.weakness_matrix(rows)
    if course_id is None:
        matrix = matrix + teach_back_cells(session, profile.id)
    error = metrics.error_profile(session, profile.id, course_id)
    speed = metrics.speed_accuracy(rows)
    return {
        "weakness_matrix": matrix,
        "error_profile": error,
        "speed_accuracy": speed,
        "skills": list(metrics.SKILLS),
    }


@router.get("/recommendations", response_model=list[RecommendationOut])
def recommendations(
    course_id: str | None = None, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return metrics.recommendations(session, profile.id, course_id)


@router.get("/items", response_model=list[ItemStatOut])
def items(
    course_id: str | None = None, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return metrics.item_analysis(session, profile.id, course_id)


CSV_COLUMNS = (
    "section",
    "day",
    "answers_n",
    "correct_n",
    "cards_reviewed",
    "minutes",
    "study_seconds",
    "xp",
    "concept",
    "concept_id",
    "skill",
    "n",
    "accuracy",
    "avg_time_ratio",
    "weakness_score",
    "enough_data",
    "question_id",
    "p_correct",
    "discrimination",
    "distractor_efficiency",
    "avg_time_ms",
    "flag",
    "elo_outlier",
    "stem_excerpt",
)


def _export_payload(session: Session, profile_id: str, course_id: str | None) -> dict[str, Any]:
    rows = metrics.answer_rows(session, profile_id, course_id)
    return {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "course_id": course_id,
        "daily": metrics.daily_history(session, profile_id, course_id),
        "concepts": metrics.weakness_matrix(rows),
        "items": metrics.item_analysis(session, profile_id, course_id),
    }


def _csv_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in payload["daily"]:
        rows.append({"section": "daily", **entry})
    for entry in payload["concepts"]:
        rows.append(
            {
                "section": "concept",
                "concept": entry["concept"],
                "concept_id": entry["concept_id"],
                "skill": entry["skill"],
                "n": entry["n"],
                "accuracy": entry["accuracy"],
                "avg_time_ratio": entry["avg_time_ratio"],
                "weakness_score": entry["weakness_score"],
                "enough_data": entry["enough_data"],
            }
        )
    for entry in payload["items"]:
        rows.append({"section": "item", **entry})
    return rows


@router.get("/export", response_model=AnalyticsExportOut)
def export_analytics(
    format: AnalyticsExportFormat = AnalyticsExportFormat.CSV,
    course_id: str | None = None,
    session: Session = Depends(get_session),
) -> Any:
    profile = ensure_default_profile(session)
    payload = _export_payload(session, profile.id, course_id)
    if format == AnalyticsExportFormat.JSON:
        return payload
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(CSV_COLUMNS), extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(_csv_rows(payload))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="study-progress.csv"'},
    )


@router.put("/goal", response_model=GoalOut)
def set_goal(body: GoalIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    if body.unit is None and body.answers_per_day is None and body.minutes_per_day is None:
        raise HTTPException(
            status_code=422, detail="nothing to update: provide unit, answers or minutes"
        )
    result = metrics.set_goal(
        session,
        profile.id,
        unit=body.unit,
        answers_per_day=body.answers_per_day,
        minutes_per_day=body.minutes_per_day,
    )
    session.commit()
    return result


@router.post("/materialize", response_model=MaterializeOut)
def materialize(session: Session = Depends(get_session)) -> dict[str, str]:
    profile = ensure_default_profile(session)
    try:
        metrics.materialize(session, profile.id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"status": "ok"}


@router.get("/costs", response_model=CostsOut)
def costs(session: Session = Depends(get_session)) -> dict[str, Any]:
    ensure_default_profile(session)
    from datetime import UTC, datetime

    from sqlalchemy import func, select

    from ..ai.tasks import TASK_DEFS
    from ..domain.models import TaskAssignment

    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = session.execute(
        select(
            AiInteraction.task,
            AiInteraction.model,
            func.count(),
            func.coalesce(func.sum(AiInteraction.input_tokens), 0),
            func.coalesce(func.sum(AiInteraction.output_tokens), 0),
            func.coalesce(func.sum(AiInteraction.cost_micros), 0),
        )
        .where(
            AiInteraction.context_type == "gateway",
            AiInteraction.created_at >= month_start,
        )
        .group_by(AiInteraction.task, AiInteraction.model)
    ).all()
    caps = {
        assignment_row.task: (assignment_row.params or {}).get("monthly_cap_micros")
        for assignment_row in session.scalars(select(TaskAssignment))
    }
    per_task: dict[str, dict[str, Any]] = {}
    for task, model, calls, tokens_in, tokens_out, cost_micros in rows:
        entry = per_task.setdefault(
            str(task),
            {
                "task": task,
                "calls": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_micros": 0,
                "models": {},
            },
        )
        entry["calls"] += int(calls)
        entry["tokens_in"] += int(tokens_in)
        entry["tokens_out"] += int(tokens_out)
        entry["cost_micros"] += int(cost_micros)
        if model:
            entry["models"][model] = entry["models"].get(model, 0) + int(calls)
    tasks_out = []
    for task_def in TASK_DEFS:
        entry = per_task.pop(
            task_def.task,
            {
                "task": task_def.task,
                "calls": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_micros": 0,
                "models": {},
            },
        )
        entry["monthly_cap_micros"] = caps.get(task_def.task)
        tasks_out.append(entry)
    for leftover in per_task.values():
        leftover["monthly_cap_micros"] = caps.get(str(leftover["task"]))
        tasks_out.append(leftover)

    recent_rows = session.execute(
        select(AiInteraction)
        .where(
            AiInteraction.context_type == "gateway",
            AiInteraction.created_at >= month_start,
        )
        .order_by(AiInteraction.created_at.desc())
        .limit(50)
    ).scalars()
    recent = [
        {
            "id": str(row.id),
            "task": row.task,
            "model": row.model,
            "resolved_model": row.model_external_id,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "cost_micros": row.cost_micros,
            "price_source": row.price_source,
            "outcome": None,
            "created_at": row.created_at.isoformat(),
        }
        for row in recent_rows
    ]
    return {
        "month": month_start.date().isoformat(),
        "per_task": tasks_out,
        "total_micros": sum(entry["cost_micros"] for entry in tasks_out),
        "recent": recent,
    }


class RetentionBucketOut(BaseModel):
    key: str
    reviews: int
    correct: int
    retention: float


class RetentionOut(BaseModel):
    target: float
    reviews: int
    correct: int
    retention: float | None
    lapses: int
    buckets: list[RetentionBucketOut]


@router.get("/retention", response_model=RetentionOut)
def retention(
    days: int = 90,
    session: Session = Depends(get_session),
) -> RetentionOut:
    profile = ensure_default_profile(session)
    since = utcnow() - timedelta(days=max(1, min(days, 365)))
    rows = session.execute(
        select(ReviewLog.rating, ReviewLog.interval_days)
        .join(Exercise, Exercise.id == ReviewLog.card_id)
        .where(
            Exercise.profile_id == profile.id,
            ReviewLog.reviewed_at >= since,
            ReviewLog.source == ReviewSource.REVIEW.value,
        )
    ).all()
    buckets = {
        "young": {"reviews": 0, "correct": 0},
        "mature": {"reviews": 0, "correct": 0},
    }
    correct = 0
    lapses = 0
    for rating, interval_days in rows:
        bucket = "young" if (interval_days or 0) < 21 else "mature"
        buckets[bucket]["reviews"] += 1
        if rating == 1:
            lapses += 1
            continue
        buckets[bucket]["correct"] += 1
        correct += 1
    total = len(rows)
    values = fsrs_settings.get_profile(session, profile.id)
    return RetentionOut(
        target=values.desired_retention,
        reviews=total,
        correct=correct,
        retention=(correct / total) if total else None,
        lapses=lapses,
        buckets=[
            RetentionBucketOut(
                key=key,
                reviews=entry["reviews"],
                correct=entry["correct"],
                retention=(entry["correct"] / entry["reviews"]) if entry["reviews"] else 0.0,
            )
            for key, entry in buckets.items()
        ],
    )


class WorkloadDayOut(BaseModel):
    day: str
    due: int


class WorkloadOut(BaseModel):
    days: list[WorkloadDayOut]
    new_available: int
    total: int
    peak_day: str | None
    peak_count: int


@router.get("/workload", response_model=WorkloadOut)
def workload(
    days: int = 30,
    session: Session = Depends(get_session),
) -> WorkloadOut:
    profile = ensure_default_profile(session)
    horizon = max(1, min(days, 90))
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    until = today + timedelta(days=horizon)
    rows = session.execute(
        select(FsrsState.due_at)
        .join(Exercise, Exercise.id == FsrsState.card_id)
        .where(
            Exercise.profile_id == profile.id,
            Exercise.kind.in_(CARD_KINDS),
            FsrsState.due_at >= today,
            FsrsState.due_at < until,
        )
    ).scalars()
    counts: dict[str, int] = {}
    for due_at in rows:
        day = due_at.date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    series = [
        WorkloadDayOut(
            day=(today + timedelta(days=index)).date().isoformat(),
            due=counts.get((today + timedelta(days=index)).date().isoformat(), 0),
        )
        for index in range(horizon)
    ]
    new_available = int(
        session.scalar(
            select(func.count(Exercise.id))
            .outerjoin(FsrsState, FsrsState.card_id == Exercise.id)
            .where(
                Exercise.profile_id == profile.id,
                Exercise.kind.in_(CARD_KINDS),
                FsrsState.id.is_(None),
            )
        )
        or 0
    )
    peak = max(series, key=lambda entry: entry.due, default=None)
    return WorkloadOut(
        days=series,
        new_available=new_available,
        total=sum(entry.due for entry in series),
        peak_day=peak.day if peak is not None and peak.due > 0 else None,
        peak_count=peak.due if peak is not None else 0,
    )
