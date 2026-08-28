from typing import Any

from app.domain.models import Question
from app.services.grading import grade


def make_question(
    qtype: str, answer: dict[str, Any], sympy_check: dict[str, Any] | None = None
) -> Question:
    return Question(type=qtype, answer=answer, sympy_check=sympy_check)


def test_single_correct_and_incorrect() -> None:
    question = make_question("single", {"index": 2})
    assert grade(question, 2).correct is True
    assert grade(question, 0).correct is False
    assert grade(question, "not-an-index").correct is False


def test_truefalse() -> None:
    question = make_question("truefalse", {"value": True})
    assert grade(question, True).correct is True
    assert grade(question, False).correct is False


def test_multi_exact_full_credit() -> None:
    question = make_question("multi", {"indices": [0, 2]})
    assert grade(question, [2, 0]).correct is True
    assert grade(question, [2, 0]).partial_credit == 1.0


def test_multi_partial_credit() -> None:
    question = make_question("multi", {"indices": [0, 1, 2]})
    result = grade(question, [0, 1, 3])
    assert result.correct is False
    assert 0 < result.partial_credit < 1
    assert result.partial_credit == 2 / 4


def test_text_normalized_comparison() -> None:
    question = make_question("text", {"value": "Chain Rule", "accept": ["the chain rule"]})
    assert grade(question, "chain rule").correct is True
    assert grade(question, "THE  CHAIN RULE!").correct is True
    assert grade(question, "product rule").correct is False


def test_numeric_tolerance() -> None:
    question = make_question("numeric", {"value": 3.14, "tolerance": 0.01})
    assert grade(question, "3.145").correct is True
    assert grade(question, "3.5").correct is False
    assert grade(question, "abc").correct is False


def test_numeric_relative_tolerance() -> None:
    question = make_question("numeric", {"value": 1000, "tolerance": 0.01, "relative": True})
    assert grade(question, "1010").correct is True
    assert grade(question, "1030").correct is False


def test_equation_via_sympy_check() -> None:
    question = make_question(
        "equation",
        {"value": "2*x*sin(x) + x^2*cos(x)"},
        sympy_check={"expected": "2*x*sin(x) + x**2*cos(x)"},
    )
    assert grade(question, "x^2 cos(x) + 2x sin(x)").correct is True
    assert grade(question, "2x").correct is False


def test_unsupported_type() -> None:
    question = make_question("hologram", {})
    result = grade(question, None)
    assert result.correct is False
    assert result.graded_by == "config"
