from typing import Any

from app.math.code import code_public_input, grade_code, validate_code_answer

CODE_ANSWER: dict[str, Any] = {
    "starter_code": "def is_palindrome(s):\n    ...",
    "reference_solution": "def is_palindrome(s):\n    return s == s[::-1]",
    "tests": [
        {"call": "is_palindrome('abba')", "expected": True},
        {"call": "is_palindrome('abc')", "expected": False},
        {"call": "print(is_palindrome('abba'))", "expected": None, "expected_stdout": "True\n"},
    ],
}


def payload(*results: dict[str, Any]) -> dict[str, Any]:
    return {"results": list(results)}


class TestValidation:
    def test_valid_answer_passes(self) -> None:
        assert validate_code_answer(CODE_ANSWER) == []

    def test_tests_bounds(self) -> None:
        assert validate_code_answer({**CODE_ANSWER, "tests": []}) != []

    def test_reference_required(self) -> None:
        problems = validate_code_answer({**CODE_ANSWER, "reference_solution": ""})
        assert any("reference_solution" in problem for problem in problems)

    def test_call_and_expected_required(self) -> None:
        problems = validate_code_answer({**CODE_ANSWER, "tests": [{"call": "f()"}]})
        assert any("expected" in problem for problem in problems)

    def test_timeout_must_be_positive(self) -> None:
        problems = validate_code_answer({**CODE_ANSWER, "timeout_ms": -1})
        assert any("timeout_ms" in problem for problem in problems)


class TestPublicInput:
    def test_exposes_tests_not_reference(self) -> None:
        grid = code_public_input(CODE_ANSWER)
        assert grid is not None
        assert grid["widget"] == "code"
        assert grid["starter_code"].startswith("def is_palindrome")
        assert grid["tests"][0] == {
            "call": "is_palindrome('abba')",
            "expected": True,
            "expected_stdout": None,
        }
        assert "reference_solution" not in grid

    def test_garbage_returns_none(self) -> None:
        assert code_public_input({"tests": "no"}) is None


class TestGrading:
    def test_all_cases_pass(self) -> None:
        result = grade_code(
            CODE_ANSWER,
            payload(
                {"passed": True, "output": "true"},
                {"passed": True, "output": "false"},
                {"passed": True, "output": "null", "stdout": "True"},
            ),
        )
        assert result["correct"] is True
        assert result["partial_credit"] == 1.0

    def test_failing_case(self) -> None:
        result = grade_code(
            CODE_ANSWER,
            payload(
                {"passed": True, "output": "true"},
                {"passed": False, "output": "true"},
                {"passed": True, "output": "null", "stdout": "True"},
            ),
        )
        assert result["correct"] is False
        assert result["partial_credit"] == round(2 / 3, 4)
        assert "failing_test" in result["error_tags"]

    def test_backend_reverifies_outputs(self) -> None:
        result = grade_code(
            CODE_ANSWER,
            payload(
                {"passed": True, "output": "false"},
                {"passed": True, "output": "false"},
                {"passed": True, "output": "null", "stdout": "True"},
            ),
        )
        assert result["correct"] is False
        assert result["partial_credit"] == round(2 / 3, 4)

    def test_stdout_mismatch(self) -> None:
        result = grade_code(
            CODE_ANSWER,
            payload(
                {"passed": True, "output": "true"},
                {"passed": True, "output": "false"},
                {"passed": True, "output": "null", "stdout": "False"},
            ),
        )
        assert result["correct"] is False

    def test_string_normalization(self) -> None:
        answer: dict[str, Any] = {
            "reference_solution": "def f():\n    return 'hi'",
            "tests": [{"call": "f()", "expected": "hi"}],
        }
        result = grade_code(answer, payload({"passed": True, "output": "\"hi\""}))
        assert result["correct"] is True

    def test_malformed(self) -> None:
        bad_payloads: list[Any] = ["hello", None, {"results": []}]
        for bad in bad_payloads:
            result = grade_code(CODE_ANSWER, bad)
            assert result["correct"] is False
            assert result["partial_credit"] == 0.0
