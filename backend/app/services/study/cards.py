from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.models import Exercise, ExerciseStep
from .exercise_kinds import (
    LEGACY_CARD_KIND_MAP,
    is_card_kind,
    legacy_kind_from_card,
)


def is_card(exercise: Exercise) -> bool:
    return is_card_kind(exercise.kind)


def card_parts(exercise: Exercise) -> dict[str, Any] | None:
    for step in exercise.steps:
        if step.order_idx != 0:
            continue
        expected = step.expected or {}
        return {
            "front": step.prompt,
            "back": expected.get("back", []),
            "kind": legacy_kind_from_card(exercise.kind),
        }
    return None


def card_source(exercise: Exercise) -> tuple[str, str | None]:
    created_from = exercise.created_from or {}
    return (
        str(created_from.get("source", "note")),
        created_from.get("source_ref"),
    )


def front_title(front: list[dict[str, Any]]) -> str:
    parts = [str(block.get("md", "")) for block in front if block.get("md")]
    title = " ".join(part.strip() for part in parts if part.strip())
    return title[:300] if title else "Card"


def create_card_exercise(
    session: Session,
    *,
    profile_id: int,
    course_id: int,
    node_id: int | None,
    kind: str,
    front: list[dict[str, Any]],
    back: list[dict[str, Any]],
    source: str,
    source_ref: str | None = None,
    deck_ref: str | None = None,
) -> Exercise:
    exercise_kind = LEGACY_CARD_KIND_MAP.get(kind)
    if exercise_kind is None:
        raise ValueError(f"unknown card kind: {kind}")
    exercise = Exercise(
        profile_id=profile_id,
        course_id=course_id,
        node_id=node_id,
        title=front_title(front),
        kind=exercise_kind,
        deck_ref=deck_ref,
        created_from={"source": source, "source_ref": source_ref},
    )
    exercise.steps = [
        ExerciseStep(
            order_idx=0,
            prompt=front,
            expected={"kind": exercise_kind, "back": back},
        )
    ]
    session.add(exercise)
    session.flush()
    return exercise


def load_card_steps(session: Session, exercise_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not exercise_ids:
        return {}
    rows = session.execute(
        select(ExerciseStep)
        .where(ExerciseStep.order_idx == 0, ExerciseStep.exercise_id.in_(exercise_ids))
        .order_by(ExerciseStep.order_idx)
    ).scalars()
    result: dict[int, dict[str, Any]] = {}
    for step in rows:
        if step.exercise_id not in result:
            expected = step.expected or {}
            result[step.exercise_id] = {
                "front": step.prompt,
                "back": expected.get("back", []),
            }
    return result
