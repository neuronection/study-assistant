import re
from dataclasses import dataclass, field
from typing import Any

from ...domain.models import Question
from ...math.composite import grade_composite
from ...math.equivalence import equivalent
from ...math.graphs import grade_graph_read
from ...math.regions import grade_regions
from ...math.tables import grade_table_fill

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class GradeResult:
    correct: bool
    partial_credit: float
    graded_by: str
    feedback: list[dict[str, Any]] = field(default_factory=list)
    error_tags: list[str] = field(default_factory=list)


def _text_result(correct: bool, detail: str, graded_by: str) -> GradeResult:
    return GradeResult(
        correct=correct,
        partial_credit=1.0 if correct else 0.0,
        graded_by=graded_by,
        feedback=[{"type": "text", "md": detail}],
    )


def _normalize_text(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return _WHITESPACE_RE.sub(" ", lowered)


def grade_single(response: Any, answer: dict[str, Any]) -> GradeResult:
    try:
        chosen = int(response)
    except (TypeError, ValueError):
        return _text_result(False, "no option selected", "deterministic")
    correct_index = int(answer["index"])
    ok = chosen == correct_index
    return _text_result(ok, "correct" if ok else "incorrect", "deterministic")


def grade_truefalse(response: Any, answer: dict[str, Any]) -> GradeResult:
    truthy = response in (True, 1, "1", "true", "True", "TRUE")
    falsy = response in (False, 0, "0", "false", "False", "FALSE")
    if not truthy and not falsy:
        return _text_result(False, "answer must be true or false", "deterministic")
    ok = truthy == bool(answer["value"])
    return _text_result(ok, "correct" if ok else "incorrect", "deterministic")


def grade_multi(response: Any, answer: dict[str, Any]) -> GradeResult:
    if not isinstance(response, list):
        return _text_result(False, "no options selected", "deterministic")
    chosen = {int(item) for item in response}
    correct_set = {int(item) for item in answer["indices"]}
    if chosen == correct_set:
        return _text_result(True, "all correct options selected", "deterministic")
    selected_correct = len(chosen & correct_set)
    selected_wrong = len(chosen - correct_set)
    missed = len(correct_set - chosen)
    union = len(chosen | correct_set)
    credit = len(chosen & correct_set) / union if union else 0.0
    return GradeResult(
        correct=False,
        partial_credit=round(credit, 4),
        graded_by="deterministic",
        feedback=[
            {
                "type": "text",
                "md": f"{selected_correct} correct, {selected_wrong} wrong, {missed} missed",
            }
        ],
        error_tags=["incomplete_selection"] if selected_correct and not selected_wrong else [],
    )


def grade_text(response: Any, answer: dict[str, Any]) -> GradeResult:
    if not isinstance(response, str):
        return _text_result(False, "empty answer", "deterministic")
    accepted = [answer.get("value", "")]
    accepted += list(answer.get("accept", []))
    normalized = _normalize_text(response)
    for candidate in accepted:
        if normalized == _normalize_text(str(candidate)):
            return _text_result(True, "correct", "deterministic")
    return _text_result(False, "incorrect", "deterministic")


def grade_numeric(response: Any, answer: dict[str, Any]) -> GradeResult:
    try:
        value = float(str(response).replace(",", ".").strip())
    except (TypeError, ValueError):
        return _text_result(False, "answer is not a number", "deterministic")
    expected = float(answer["value"])
    tolerance = float(answer.get("tolerance", 1e-6))
    if answer.get("relative"):
        ok = abs(value - expected) <= tolerance * max(1.0, abs(expected))
    else:
        ok = abs(value - expected) <= tolerance
    return _text_result(ok, "correct" if ok else "incorrect", "deterministic")


def grade_equation(
    response: Any, answer: dict[str, Any], sympy_check: dict[str, Any] | None
) -> GradeResult:
    if not isinstance(response, str) or not response.strip():
        return _text_result(False, "empty answer", "deterministic")
    expected = None
    if sympy_check is not None:
        expected = sympy_check.get("expected")
    if expected is None:
        expected = answer.get("value")
    if expected is None:
        return _text_result(False, "question has no reference answer", "config")
    result = equivalent(response, str(expected))
    detail = f"{result.stage}: {result.detail}"
    return _text_result(result.equivalent, detail, "symPy")


def grade_numberline(response: Any, answer: dict[str, Any]) -> GradeResult:
    result = grade_regions(answer, response)
    return GradeResult(
        correct=result.correct,
        partial_credit=result.partial_credit,
        graded_by="deterministic",
        feedback=[{"type": "text", "md": line} for line in result.feedback],
        error_tags=list(result.error_tags),
    )


def grade_table(response: Any, answer: dict[str, Any]) -> GradeResult:
    result = grade_table_fill(answer, response)
    return GradeResult(
        correct=result["correct"],
        partial_credit=result["partial_credit"],
        graded_by="deterministic",
        feedback=[{"type": "text", "md": line} for line in result["feedback"]],
        error_tags=list(result["error_tags"]),
    )


def grade_composite_question(response: Any, answer: dict[str, Any]) -> GradeResult:
    result = grade_composite(answer, response)
    return GradeResult(
        correct=result["correct"],
        partial_credit=result["partial_credit"],
        graded_by="deterministic",
        feedback=[{"type": "text", "md": line} for line in result["feedback"]],
        error_tags=list(result["error_tags"]),
    )


def grade_graph(response: Any, answer: dict[str, Any]) -> GradeResult:
    result = grade_graph_read(answer, response)
    return GradeResult(
        correct=result["correct"],
        partial_credit=result["partial_credit"],
        graded_by="deterministic",
        feedback=[{"type": "text", "md": line} for line in result["feedback"]],
        error_tags=list(result["error_tags"]),
    )


def grade(question: Question, response: Any) -> GradeResult:
    answer = question.answer or {}
    graders = {
        "single": lambda: grade_single(response, answer),
        "truefalse": lambda: grade_truefalse(response, answer),
        "multi": lambda: grade_multi(response, answer),
        "text": lambda: grade_text(response, answer),
        "numeric": lambda: grade_numeric(response, answer),
        "equation": lambda: grade_equation(response, answer, question.sympy_check),
        "numberline": lambda: grade_numberline(response, answer),
        "table_fill": lambda: grade_table(response, answer),
        "composite": lambda: grade_composite_question(response, answer),
        "graph_read": lambda: grade_graph(response, answer),
    }
    grader = graders.get(question.type)
    if grader is None:
        return _text_result(False, f"unsupported type '{question.type}'", "config")
    return grader()
