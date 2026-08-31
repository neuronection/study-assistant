import json
from typing import Any

from sqlalchemy.orm import Session

from ...ai.gateway import LLMGateway
from ...ai.runner import AuditRef, TaskRunner
from ...ai.skills import GRADE_FREEFORM_SYSTEM
from ...ai.structured import RubricOut
from ...domain.models import ExerciseStep

RUBRIC_TASK = "grade"
RUBRIC_SKILL = "grade.freeform"
MAX_REPAIR_ROUNDS = 2

RUBRIC_KINDS = ("explain", "error_spot", "correct_solution")
VERDICTS = ("correct", "partial", "incorrect")


class RubricError(ValueError):
    pass


def validate_rubric_payload(kind: str, payload: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    rows = payload.get("rubric")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
        problems.append(f"{kind}: 1-8 rubric rows required")
        return problems
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"rubric row {index}: not an object")
            continue
        rubric_id = str(row.get("id", "")).strip()
        text = str(row.get("text", "")).strip()
        if not rubric_id or not text:
            problems.append(f"rubric row {index}: id and text required")
            continue
        if rubric_id in seen:
            problems.append(f"rubric row {index}: duplicate id")
        seen.add(rubric_id)
    if kind == "error_spot":
        lines = payload.get("lines")
        if not isinstance(lines, list) or not 2 <= len(lines) <= 12:
            problems.append("error_spot: 2-12 lines required")
            return problems
        flaw_index = payload.get("flaw_index")
        if not isinstance(flaw_index, int) or not 0 <= flaw_index < len(lines):
            problems.append("error_spot: flaw_index out of range")
    if kind == "correct_solution":
        fix = payload.get("fix")
        if not isinstance(fix, str) or not fix.strip():
            problems.append("correct_solution: fix (expected corrected line) required")
    if kind == "explain" and not str(payload.get("prompt_md", "")).strip():
        problems.append("explain: prompt_md required")
    return problems


def _validate_verdict(draft: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if draft.get("verdict") not in VERDICTS:
        problems.append("verdict must be correct|partial|incorrect")
    score = draft.get("score")
    try:
        value = float(str(score))
        if not 0 <= value <= 1:
            problems.append("score must be 0-1")
    except (TypeError, ValueError):
        problems.append("score must be numeric")
        value = 0.0
    rationale = draft.get("rationale")
    if not isinstance(rationale, list) or not rationale:
        problems.append("rationale rows required")
    elif isinstance(rationale, list):
        for index, row in enumerate(rationale):
            if not isinstance(row, dict) or not str(row.get("rubric_id", "")).strip():
                problems.append(f"rationale row {index}: rubric_id required")
            elif not str(row.get("reason", "")).strip():
                problems.append(f"rationale row {index}: reason required")
    return problems


class RubricGrader:
    def __init__(self, session: Session, gateway: LLMGateway) -> None:
        self._session = session
        self._gateway = gateway

    def grade(
        self,
        step: ExerciseStep,
        payload: dict[str, Any],
        response: str,
        course_id: int | None = None,
    ) -> dict[str, Any]:
        rubric_rows = payload.get("rubric", [])
        prompt = (
            "Grade the student's answer against the rubric.\n\n"
            "Question:\n"
            f"{json.dumps(payload.get('prompt_md', ''), ensure_ascii=False)}\n\n"
            "Rubric rows:\n"
            + "\n".join(
                f"- {row.get('id', '')}: {row.get('text', '')}" for row in rubric_rows
            )
            + "\n\nStudent's answer:\n"
            + response[:4000]
        )
        runner = TaskRunner(self._session, self._gateway)
        result = runner.run_json(
            task=RUBRIC_TASK,
            prompt=prompt,
            validate=_validate_verdict,
            fallback_system=GRADE_FREEFORM_SYSTEM,
            skill_key=RUBRIC_SKILL,
            course_id=course_id,
            max_rounds=MAX_REPAIR_ROUNDS,
            error_type=RubricError,
            audit=AuditRef("grade", None, "rubric grading for exercise step"),
            schema=RubricOut,
        )
        if result.problems:
            raise RubricError(
                "grading failed validation: " + "; ".join(result.problems[:6])
            )
        draft = result.draft
        raw_score = draft.get("score", 0)
        score = min(max(float(raw_score if raw_score is not None else 0.0), 0.0), 1.0)
        verdict = draft.get("verdict", "incorrect")
        return {
            "verdict": verdict,
            "score": score,
            "rationale": draft.get("rationale", []),
            "graded_by": "rubric",
        }


def rubric_public_input(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    widget = "essay" if kind == "explain" else "lines" if kind == "error_spot" else "math"
    result: dict[str, Any] = {"widget": widget, "kind": kind}
    if kind == "error_spot":
        result["lines"] = [str(line) for line in payload.get("lines", [])]
    if kind == "explain":
        result["prompt_md"] = str(payload.get("prompt_md", ""))
    return result


def rubric_deterministic_check(
    kind: str, payload: dict[str, Any], response: str
) -> tuple[bool, str] | None:
    if kind == "error_spot":
        try:
            picked = json.loads(response)
            if not isinstance(picked, list) or not all(
                isinstance(entry, int) for entry in picked
            ):
                return None
            flaw = payload.get("flaw_index")
            if picked == [flaw]:
                return True, "error_spot: correct"
            return False, "error_spot: wrong line(s) picked"
        except (ValueError, TypeError):
            return None
    if kind == "correct_solution":
        fix = str(payload.get("fix", "")).strip()
        if not fix:
            return None
        normalized_response = " ".join(response.split()).strip()
        normalized_fix = " ".join(fix.split()).strip()
        if normalized_response == normalized_fix:
            return True, "correct_solution: matches the expected fix"
        return None
    return None
