import json
from pathlib import Path
from typing import Any

from app.pipelines.quizgen import validate_question

GOLDEN = Path(__file__).parent / "golden" / "quizgen_validation.json"


def load_golden() -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return parsed


def test_quizgen_validation_golden_set() -> None:
    golden = load_golden()
    assert golden["version"] == 1
    failures: list[str] = []
    for case in golden["cases"]:
        problems = validate_question(case["draft"], 0)
        if problems != case["expect_problems"]:
            failures.append(
                f"{case['name']}: expected {case['expect_problems']}, got {problems}"
            )
    assert not failures, "golden drift:\n" + "\n".join(failures)


def test_golden_covers_every_question_type() -> None:
    golden = load_golden()
    covered = {case["draft"].get("type") for case in golden["cases"]}
    from app.core.vocab import QUESTION_TYPES

    missing = set(QUESTION_TYPES) - covered
    assert not missing, f"golden set never exercises: {sorted(missing)}"
