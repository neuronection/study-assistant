from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import ItemFlag, RecommendationKind, SpeedLabel, SpeedQuadrant
from ..services.platform import metrics
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/analytics", tags=["analytics"])


class GoalIn(BaseModel):
    answers_per_day: int = Field(ge=1, le=500)


class DayActivityOut(BaseModel):
    day: str
    answers_n: int
    correct_n: int
    cards_reviewed: int
    minutes: float
    xp: int


class OverviewOut(BaseModel):
    today: DayActivityOut
    goal: int
    streak: int
    total_xp: int
    level: int
    due_cards: int
    history: list[DayActivityOut]


class MostBehindNodeOut(BaseModel):
    id: int
    title: str


class ExamStatusOut(BaseModel):
    course_id: int
    course_title: str
    exam_date: str
    days_left: int
    total_nodes: int
    engaged_nodes: int
    remaining_nodes: int
    nodes_per_day: float | None
    on_track: bool
    most_behind_node: MostBehindNodeOut | None


class WeaknessCellOut(BaseModel):
    concept: str
    concept_id: int | None
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
    question_id: int
    n_attempts: int
    p_correct: float
    avg_time_ms: int | None
    avg_time_ratio: float | None
    distractor_selection: dict[str, int] | None
    flag: ItemFlag
    stem_excerpt: str


class GoalOut(BaseModel):
    answers_per_day: int


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
    course_id: int | None = None, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    rows = metrics.answer_rows(session, profile.id, course_id)
    matrix = metrics.weakness_matrix(rows)
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
    course_id: int | None = None, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return metrics.recommendations(session, profile.id, course_id)


@router.get("/items", response_model=list[ItemStatOut])
def items(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return metrics.item_analysis(session, profile.id)


@router.put("/goal", response_model=GoalOut)
def set_goal(
    body: GoalIn, session: Session = Depends(get_session)
) -> dict[str, int]:
    profile = ensure_default_profile(session)
    value = metrics.set_goal(session, profile.id, body.answers_per_day)
    session.commit()
    return {"answers_per_day": value}


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

    month_start = datetime.now(UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
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
