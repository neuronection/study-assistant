from typing import Any

from app.math.composite import (
    composite_public_input,
    grade_composite,
    validate_composite_answer,
)

MULTI_PART: dict[str, Any] = {
    "parts": [
        {"type": "numeric", "value": "3", "tolerance": 0.01},
        {
            "type": "equation",
            "value": "9",
            "follow_through": "a**2",
        },
        {"type": "text", "value": "increasing"},
    ]
}


def response(*values: str) -> list[str]:
    return list(values)


class TestValidation:
    def test_valid_answer_passes(self) -> None:
        assert validate_composite_answer(MULTI_PART) == []

    def test_parts_count_bounds(self) -> None:
        assert validate_composite_answer({"parts": []}) != []
        assert validate_composite_answer({"parts": [{"type": "text", "value": "x"}]}) != []
        assert validate_composite_answer({"parts": [{"type": "text", "value": "x"}] * 5}) != []

    def test_unknown_part_type(self) -> None:
        problems = validate_composite_answer(
            {"parts": [{"type": "boolean", "value": "x"}, {"type": "text", "value": "y"}]}
        )
        assert any("type" in problem for problem in problems)

    def test_relation_must_reference_only_prior_parts(self) -> None:
        problems = validate_composite_answer(
            {
                "parts": [
                    {"type": "numeric", "value": "3", "follow_through": "a"},
                    {"type": "numeric", "value": "9"},
                ]
            }
        )
        assert any("prior parts" in problem for problem in problems)

    def test_relation_must_reproduce_declared_value(self) -> None:
        problems = validate_composite_answer(
            {
                "parts": [
                    {"type": "numeric", "value": "3"},
                    {"type": "numeric", "value": "10", "follow_through": "a**2"},
                ]
            }
        )
        assert any("does not reproduce" in problem for problem in problems)

    def test_consistent_relation_passes(self) -> None:
        assert (
            validate_composite_answer(
                {
                    "parts": [
                        {"type": "numeric", "value": "3"},
                        {"type": "numeric", "value": "9", "follow_through": "a**2"},
                    ]
                }
            )
            == []
        )

    def test_text_part_cannot_carry_relation(self) -> None:
        problems = validate_composite_answer(
            {
                "parts": [
                    {"type": "numeric", "value": "3"},
                    {"type": "text", "value": "hello", "follow_through": "a"},
                ]
            }
        )
        assert any("not supported for text" in problem for problem in problems)


class TestPublicInput:
    def test_types_only(self) -> None:
        grid = composite_public_input(MULTI_PART)
        assert grid == {
            "widget": "composite",
            "parts": [{"type": "numeric"}, {"type": "equation"}, {"type": "text"}],
        }

    def test_garbage_returns_none(self) -> None:
        assert composite_public_input({"parts": "no"}) is None


class TestGrading:
    def test_all_correct(self) -> None:
        result = grade_composite(MULTI_PART, response("3", "9", "Increasing"))
        assert result["correct"] is True
        assert result["partial_credit"] == 1.0
        assert result["flags"] == []

    def test_follow_through_credit(self) -> None:
        result = grade_composite(MULTI_PART, response("4", "16", "increasing"))
        assert result["correct"] is False
        assert result["partial_credit"] == round(2 / 3, 4)
        assert result["flags"] == [2]
        assert "follow-through" in result["feedback"][0]
        assert "follow_through" in result["error_tags"]

    def test_wrong_value_without_follow_through_fails(self) -> None:
        result = grade_composite(MULTI_PART, response("4", "9", "increasing"))
        assert result["correct"] is False
        assert result["partial_credit"] == round(2 / 3, 4)
        assert result["flags"] == []
        assert "wrong_part" in result["error_tags"]

    def test_equation_relation_follow_through(self) -> None:
        answer: dict[str, Any] = {
            "parts": [
                {"type": "equation", "value": "x**2"},
                {"type": "equation", "value": "2*x", "follow_through": "2*a/x"},
            ]
        }
        result = grade_composite(answer, response("x**3", "2*x**2"))
        assert result["correct"] is False
        assert result["partial_credit"] == 0.5
        assert result["flags"] == [2]

    def test_malformed_response(self) -> None:
        result = grade_composite(MULTI_PART, ["3", "9"])
        assert result["correct"] is False
        assert result["partial_credit"] == 0.0
        assert result["error_tags"] == ["malformed"]
