from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..services import metrics
from ..services.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/analytics", tags=["analytics"])


class GoalIn(BaseModel):
    answers_per_day: int = Field(ge=1, le=500)


@router.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    result = metrics.overview(session, profile.id)
    session.commit()
    return result


@router.get("/exams")
def exams(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return metrics.exam_status(session, profile.id)


@router.get("/diagnostics")
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


@router.get("/recommendations")
def recommendations(
    course_id: int | None = None, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return metrics.recommendations(session, profile.id, course_id)


@router.get("/items")
def items(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return metrics.item_analysis(session, profile.id)


@router.put("/goal")
def set_goal(
    body: GoalIn, session: Session = Depends(get_session)
) -> dict[str, int]:
    profile = ensure_default_profile(session)
    value = metrics.set_goal(session, profile.id, body.answers_per_day)
    session.commit()
    return {"answers_per_day": value}


@router.post("/materialize")
def materialize(session: Session = Depends(get_session)) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    try:
        metrics.materialize(session, profile.id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"status": "ok"}


@router.get("/costs")
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
