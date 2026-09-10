from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.models import (
    Concept,
    Exercise,
    ExerciseSession,
    ExerciseStep,
    StepAttempt,
    TreeNode,
)
from ..knowledge.tree import TreeService

TEACH_BACK_RUBRIC = [
    {"id": "definition", "text": "States the core definition correctly"},
    {"id": "intuition", "text": "Explains the intuition in their own words"},
    {"id": "example", "text": "Gives at least one concrete example"},
]
TEACH_BACK_SKILL = "explanation"


def teach_back_subject(
    session: Session,
    *,
    node_id: int | None,
    concept: str | None,
    concept_id: int | None,
) -> str | None:
    if concept_id is not None:
        found = session.get(Concept, concept_id)
        if found is not None:
            return found.name
    if concept:
        return concept
    if node_id is not None:
        node = session.get(TreeNode, node_id)
        if node is not None:
            return node.title
    return None


def create_teach_back(
    session: Session,
    *,
    profile_id: int,
    course_id: int,
    node_id: int | None = None,
    concept: str | None = None,
    concept_id: int | None = None,
) -> Exercise:
    subject = teach_back_subject(
        session, node_id=node_id, concept=concept, concept_id=concept_id
    )
    if subject is None:
        raise ValueError("teach-back needs a concept or node to explain")
    placement = TreeService(session).placement_node(course_id, node_id)
    prompt_md = (
        f"Explain {subject} as if teaching a classmate: give the core "
        "definition, the key intuition in your own words, and one concrete "
        "example."
    )
    exercise = Exercise(
        profile_id=profile_id,
        course_id=course_id,
        node_id=placement,
        title=f"Teach-back: {subject}"[:300],
        kind="explain",
        created_from={"source": "teach-back"},
    )
    session.add(exercise)
    session.flush()
    session.add(
        ExerciseStep(
            exercise_id=exercise.id,
            order_idx=0,
            prompt=[{"type": "text", "md": prompt_md}],
            expected={
                "kind": "explain",
                "prompt_md": prompt_md,
                "rubric": [dict(row) for row in TEACH_BACK_RUBRIC],
                "concept": subject[:200],
                "skill": TEACH_BACK_SKILL,
            },
        )
    )
    session.flush()
    return exercise


def teach_back_cells(session: Session, profile_id: int) -> list[dict[str, Any]]:
    """Rubric results of teach-back exercises as (concept, skill=explanation)
    weakness-matrix samples, so explanation practice is visible in
    diagnostics (plan 53-D)."""
    rows = session.execute(
        select(StepAttempt, ExerciseStep)
        .join(
            ExerciseSession,
            StepAttempt.session_id == ExerciseSession.id,
        )
        .join(Exercise, ExerciseSession.exercise_id == Exercise.id)
        .join(
            ExerciseStep,
            (ExerciseStep.exercise_id == Exercise.id)
            & (ExerciseStep.order_idx == StepAttempt.step_idx),
        )
        .where(
            Exercise.profile_id == profile_id,
            Exercise.kind == "explain",
        )
    ).all()
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for step_attempt, step in rows:
        expected = step.expected if isinstance(step.expected, dict) else {}
        concept = str(expected.get("concept", "")).strip()
        if not concept:
            continue
        key = (concept, TEACH_BACK_SKILL)
        cell = cells.setdefault(
            key,
            {
                "concept": concept,
                "concept_id": None,
                "skill": TEACH_BACK_SKILL,
                "n": 0,
                "correct_n": 0,
                "last_seen_at": step_attempt.created_at.isoformat(),
            },
        )
        cell["n"] += 1
        cell["correct_n"] += 1 if step_attempt.correct else 0
        seen = step_attempt.created_at.isoformat()
        if seen > cell["last_seen_at"]:
            cell["last_seen_at"] = seen
    result: list[dict[str, Any]] = []
    from ..platform.metrics import MIN_CELL_N, _weakness

    for (concept, skill), cell in cells.items():
        n = cell["n"]
        accuracy = cell["correct_n"] / n if n else 0.0
        last_seen = datetime.fromisoformat(cell["last_seen_at"])
        result.append(
            {
                "concept": concept,
                "concept_id": None,
                "skill": skill,
                "n": n,
                "accuracy": round(accuracy, 4),
                "avg_time_ratio": None,
                "last_seen_at": cell["last_seen_at"],
                "weakness_score": round(
                    _weakness(accuracy, n, last_seen), 4
                ),
                "enough_data": n >= MIN_CELL_N,
            }
        )
    return result
