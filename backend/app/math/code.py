import json
from typing import Any

MAX_TESTS = 10
DEFAULT_TIMEOUT_MS = 5000
FLOAT_TOLERANCE = 1e-6


def validate_code_answer(answer: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    tests = answer.get("tests")
    if not isinstance(tests, list) or not 1 <= len(tests) <= MAX_TESTS:
        problems.append(f"tests must be a list of 1-{MAX_TESTS} cases")
        return problems
    reference = answer.get("reference_solution")
    if not isinstance(reference, str) or not reference.strip():
        problems.append("reference_solution required")
    starter = answer.get("starter_code")
    if starter is not None and not isinstance(starter, str):
        problems.append("starter_code must be a string")
    timeout = answer.get("timeout_ms")
    if timeout is not None and (
        not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0
    ):
        problems.append("timeout_ms must be a positive integer")
    for index, test in enumerate(tests):
        if not isinstance(test, dict):
            problems.append(f"test {index}: not an object")
            continue
        call = test.get("call")
        if not isinstance(call, str) or not call.strip():
            problems.append(f"test {index}: call expression required")
        if "expected" not in test:
            problems.append(f"test {index}: expected value required")
        stdout = test.get("expected_stdout")
        if stdout is not None and not isinstance(stdout, str):
            problems.append(f"test {index}: expected_stdout must be a string")
    return problems


def code_public_input(answer: dict[str, Any]) -> dict[str, Any] | None:
    tests = answer.get("tests")
    if not isinstance(tests, list):
        return None
    public_tests: list[dict[str, Any]] = []
    for test in tests:
        if not isinstance(test, dict) or not isinstance(test.get("call"), str):
            return None
        public_tests.append(
            {
                "call": test["call"],
                "expected": test.get("expected"),
                "expected_stdout": test.get("expected_stdout"),
            }
        )
    starter = answer.get("starter_code")
    return {
        "widget": "code",
        "starter_code": starter if isinstance(starter, str) else "",
        "tests": public_tests,
        "timeout_ms": (
            answer["timeout_ms"]
            if isinstance(answer.get("timeout_ms"), int)
            else DEFAULT_TIMEOUT_MS
        ),
    }


def _normalize_output_text(value: str) -> str:
    lines = [line.rstrip() for line in value.strip().splitlines()]
    return "\n".join(lines)


def _values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual or expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        scale = max(1.0, abs(float(expected)))
        return abs(float(actual) - float(expected)) <= FLOAT_TOLERANCE * scale
    if isinstance(expected, str) and isinstance(actual, str):
        return _normalize_output_text(expected) == _normalize_output_text(actual)
    if expected is None or actual is None:
        if expected is actual:
            return True
        return bool(expected == actual)
    if isinstance(expected, list) and isinstance(actual, list):
        same = all(
            _values_match(a, b) for a, b in zip(expected, actual, strict=False)
        )
        return bool(same and len(expected) == len(actual))
    return bool(expected == actual)


def _parse_output(output: Any) -> Any:
    if isinstance(output, str):
        text = output.strip()
        try:
            return json.loads(text)
        except ValueError:
            return _normalize_output_text(text)
    return output


def grade_code(answer: dict[str, Any], response: Any) -> dict[str, Any]:
    """Verify the in-page run's per-case outcomes against the stored tests.

    The code itself never reaches the backend — the payload carries one result
    per test case (passed flag + captured output), and this matcher re-checks
    every captured output against the expected value deterministically.
    """
    tests = answer.get("tests", [])
    if not isinstance(response, dict):
        return _code_result(False, 0.0, ["answer is not a valid code payload"], [])
    results = response.get("results")
    if not isinstance(results, list) or len(results) != len(tests):
        return _code_result(False, 0.0, ["answer does not report every test case"], [])
    passed_count = 0
    for test, result in zip(tests, results, strict=False):
        if not isinstance(result, dict):
            continue
        expected = test.get("expected") if isinstance(test, dict) else None
        expected_stdout = (
            test.get("expected_stdout") if isinstance(test, dict) else None
        )
        claimed = bool(result.get("passed"))
        output_ok = _values_match(expected, _parse_output(result.get("output")))
        stdout_ok = True
        if expected_stdout is not None:
            stdout_ok = _values_match(expected_stdout, _parse_output(result.get("stdout")))
        if claimed and output_ok and stdout_ok:
            passed_count += 1
    total = len(tests)
    partial = round(passed_count / total, 4) if total else 0.0
    correct = passed_count == total and total > 0
    feedback = [f"{passed_count}/{total} test cases passed"]
    return _code_result(
        correct,
        1.0 if correct else partial,
        feedback,
        [] if correct else ["failing_test"],
    )


def _code_result(
    correct: bool, partial: float, feedback: list[str], tags: list[str]
) -> dict[str, Any]:
    return {
        "correct": correct,
        "partial_credit": partial,
        "feedback": feedback,
        "error_tags": tags,
    }
