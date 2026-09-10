from typing import Any

from app.math.graphs import (
    build_graph_data,
    grade_graph_read,
    materialize_graph_answer,
    validate_graph_answer,
)

SIN_ANSWER: dict[str, Any] = {
    "expression": "sin(x)",
    "x_min": -6.5,
    "x_max": 6.5,
    "mode": "value",
    "point_x": 2.0,
}


def materialized(answer: dict[str, Any] | None = None) -> dict[str, Any]:
    result, _problems = materialize_graph_answer(answer or SIN_ANSWER)
    return result


class TestMaterialization:
    def test_computes_value_and_tolerance(self) -> None:
        result = materialized()
        assert result["value"] == 0.909297
        assert result["tolerance"] > 0

    def test_computes_point_index(self) -> None:
        result = materialized({**SIN_ANSWER, "mode": "point"})
        xs, _ = build_graph_data("sin(x)", -6.5, 6.5, 96)
        assert result["point_index"] == min(range(len(xs)), key=lambda i: abs(xs[i] - 2.0))

    def test_explicit_tolerance_wins(self) -> None:
        result = materialized({**SIN_ANSWER, "tolerance": 0.5})
        assert result["tolerance"] == 0.5

    def test_rejects_non_finite_expression(self) -> None:
        _result, problems = materialize_graph_answer(
            {
                **SIN_ANSWER,
                "expression": "1/x",
                "x_min": -1,
                "x_max": 1,
                "samples": 21,
                "point_x": 0.5,
            }
        )
        assert any("finite" in problem for problem in problems)

    def test_rejects_point_outside_domain(self) -> None:
        _result, problems = materialize_graph_answer({**SIN_ANSWER, "point_x": 9.0})
        assert any("inside the domain" in problem for problem in problems)


class TestValidation:
    def test_materialized_answer_passes(self) -> None:
        assert validate_graph_answer(materialized()) == []

    def test_wrong_declared_value_rejected(self) -> None:
        answer = materialized()
        answer["value"] = 5.0
        problems = validate_graph_answer(answer)
        assert any("does not match" in problem for problem in problems)

    def test_expression_required(self) -> None:
        assert validate_graph_answer({"mode": "value"}) != []

    def test_unknown_mode_rejected(self) -> None:
        assert validate_graph_answer({**SIN_ANSWER, "mode": "magic"}) != []


class TestGrading:
    def test_value_within_tolerance(self) -> None:
        answer = materialized()
        result = grade_graph_read(answer, {"value": 0.92})
        assert result["correct"] is True
        assert result["partial_credit"] == 1.0

    def test_value_outside_tolerance(self) -> None:
        answer = materialized()
        result = grade_graph_read(answer, {"value": 1.5})
        assert result["correct"] is False
        assert "wrong_value" in result["error_tags"]

    def test_point_match(self) -> None:
        answer = materialized({**SIN_ANSWER, "mode": "point"})
        result = grade_graph_read(answer, {"index": answer["point_index"]})
        assert result["correct"] is True

    def test_point_mismatch(self) -> None:
        answer = materialized({**SIN_ANSWER, "mode": "point"})
        result = grade_graph_read(answer, {"index": answer["point_index"] + 1})
        assert result["correct"] is False
        assert "wrong_point" in result["error_tags"]

    def test_malformed(self) -> None:
        for payload in ("hello", None, {"value": "x"}, {"index": "1"}):
            result = grade_graph_read(materialized(), payload)
            assert result["correct"] is False
            assert result["partial_credit"] == 0.0
