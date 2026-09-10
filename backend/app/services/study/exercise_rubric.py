import json
from typing import Any

from sqlalchemy.orm import Session

from ...ai.gateway import LLMGateway
from ...ai.runner import AuditRef, TaskRunner
from ...ai.skills import GRADE_FREEFORM_SYSTEM
from ...ai.structured import RubricOut
from ...domain.models import ExerciseStep
from ...math.equivalence import equivalent, parse_math

RUBRIC_TASK = "grade"
RUBRIC_SKILL = "grade.freeform"
MAX_REPAIR_ROUNDS = 2

RUBRIC_KINDS = ("explain", "error_spot", "correct_solution")
VERDICTS = ("correct", "partial", "incorrect")


class RubricError(ValueError):
    pass


def _error_spot_problems(payload: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    lines = payload.get("lines")
    if not isinstance(lines, list) or not 2 <= len(lines) <= 12:
        problems.append("error_spot: 2-12 lines required")
        return problems
    flaw_index = payload.get("flaw_index")
    if not isinstance(flaw_index, int) or not 0 <= flaw_index < len(lines):
        problems.append("error_spot: flaw_index out of range")
        return problems
    answers_flawed = payload.get("answers_flawed")
    answers_correct = payload.get("answers_correct")
    for name in ("answers_flawed", "answers_correct"):
        value = payload.get(name)
        if not isinstance(value, list) or len(value) != len(lines):
            problems.append(f"error_spot: {name} must align with lines")
            return problems
    if not isinstance(answers_flawed, list) or not isinstance(answers_correct, list):
        return problems
    for index, (flawed, correct) in enumerate(
        zip(answers_flawed, answers_correct, strict=False)
    ):
        if not isinstance(flawed, str) or not isinstance(correct, str):
            problems.append(f"error_spot: line {index} answers must be strings")
            return problems
        try:
            parse_math(flawed)
            parse_math(correct)
        except Exception:
            problems.append(f"error_spot: line {index} answers must parse as math")
            return problems
    for index, (flawed, correct) in enumerate(
        zip(answers_flawed, answers_correct, strict=False)
    ):
        same = equivalent(flawed, correct).equivalent
        if index == flaw_index and same:
            problems.append(
                f"error_spot: line {index} must be provably wrong "
                "(flawed answer equivalent to the correct one)"
            )
        elif index != flaw_index and not same:
            problems.append(
                f"error_spot: line {index} differs between the two versions "
                "(only the flawed line may change)"
            )
    if problems:
        return problems
    correct_line = payload.get("correct_line")
    if not isinstance(correct_line, str) or not correct_line.strip():
        problems.append("error_spot: correct_line (the fixed line text) required")
    requires_fix = payload.get("requires_fix", False)
    if not isinstance(requires_fix, bool):
        problems.append("error_spot: requires_fix must be a boolean")
    return problems


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
        problems.extend(_error_spot_problems(payload))
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
        result["requires_fix"] = bool(payload.get("requires_fix", False))
    if kind == "explain":
        result["prompt_md"] = str(payload.get("prompt_md", ""))
    return result


def _spot_response(response: str) -> dict[str, Any] | None:
    try:
        value = json.loads(response)
    except (ValueError, TypeError):
        return None
    if isinstance(value, dict):
        picked = value.get("picked")
        fix = value.get("fix")
        if isinstance(picked, list) and all(
            isinstance(entry, int) and not isinstance(entry, bool) for entry in picked
        ):
            return {"picked": picked, "fix": fix if isinstance(fix, str) else None}
        return None
    if isinstance(value, list) and all(
        isinstance(entry, int) and not isinstance(entry, bool) for entry in value
    ):
        return {"picked": value, "fix": None}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"picked": [value], "fix": None}
    return None


def _spot_correct_answer(payload: dict[str, Any]) -> str | None:
    flaw_index = payload.get("flaw_index")
    answers = payload.get("answers_correct")
    if isinstance(flaw_index, int) and isinstance(answers, list) and 0 <= flaw_index < len(answers):
        answer = answers[flaw_index]
        if isinstance(answer, str) and answer.strip():
            return answer
    direct = payload.get("correct_answer")
    if isinstance(direct, str) and direct.strip():
        return direct
    return None


def rubric_deterministic_check(
    kind: str, payload: dict[str, Any], response: str
) -> tuple[bool, str] | None:
    if kind == "error_spot":
        spot = _spot_response(response)
        if spot is None:
            return None
        flaw = payload.get("flaw_index")
        if spot["picked"] != [flaw]:
            return False, "error_spot: wrong line(s) picked"
        if not payload.get("requires_fix", False):
            return True, "error_spot: correct"
        correct_answer = _spot_correct_answer(payload)
        if correct_answer is None:
            return True, "error_spot: correct"
        fix = str(spot.get("fix") or "").strip()
        if not fix:
            return (
                False,
                "error_spot: flawed line found — now supply the corrected line",
            )
        if equivalent(fix, correct_answer).equivalent:
            return True, "error_spot: correct (flawed line + equivalent correction)"
        return False, "error_spot: the correction is not equivalent to the true line"
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
