import csv
import io
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import (
    AnalyticsExportFormat,
    GoalUnit,
    ItemFlag,
    RecommendationKind,
    SpeedLabel,
    SpeedQuadrant,
)
from ..services.platform import metrics
from ..services.platform.profiles import ensure_default_profile
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
    cost_usd: float
    models: dict[str, int]
    monthly_cap_usd: float | None = None


class CostsOut(BaseModel):
    month: str
    per_task: list[CostTaskOut]
    total_usd: float


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
    from ..domain.models import AiInteraction, TaskAssignment

    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = session.execute(
        select(
            AiInteraction.task,
            AiInteraction.model,
            func.count(),
            func.coalesce(func.sum(AiInteraction.input_tokens), 0),
            func.coalesce(func.sum(AiInteraction.output_tokens), 0),
            func.coalesce(func.sum(AiInteraction.cost_usd), 0.0),
        )
        .where(
            AiInteraction.context_type == "gateway",
            AiInteraction.created_at >= month_start,
        )
        .group_by(AiInteraction.task, AiInteraction.model)
    ).all()
    caps = {
        assignment_row.task: (assignment_row.params or {}).get("monthly_cap_usd")
        for assignment_row in session.scalars(select(TaskAssignment))
    }
    per_task: dict[str, dict[str, Any]] = {}
    for task, model, calls, tokens_in, tokens_out, cost in rows:
        entry = per_task.setdefault(
            str(task),
            {
                "task": task,
                "calls": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "models": {},
            },
        )
        entry["calls"] += int(calls)
        entry["tokens_in"] += int(tokens_in)
        entry["tokens_out"] += int(tokens_out)
        entry["cost_usd"] = round(entry["cost_usd"] + float(cost), 6)
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
                "cost_usd": 0.0,
                "models": {},
            },
        )
        entry["monthly_cap_usd"] = caps.get(task_def.task)
        tasks_out.append(entry)
    for leftover in per_task.values():
        leftover["monthly_cap_usd"] = caps.get(str(leftover["task"]))
        tasks_out.append(leftover)
    return {
        "month": month_start.date().isoformat(),
        "per_task": tasks_out,
        "total_usd": round(sum(entry["cost_usd"] for entry in tasks_out), 6),
    }
