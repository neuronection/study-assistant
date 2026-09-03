from typing import Any

from app.math.tables import grade_table_fill, table_public_input, validate_table_answer

TRUTH_TABLE: dict[str, Any] = {
    "headers": ["p", "q", "p and q"],
    "rows": [
        {
            "label": "row 1",
            "cells": [
                {"kind": "locked", "value": "true"},
                {"kind": "locked", "value": "true"},
                {"kind": "text", "value": "true"},
            ],
        },
        {
            "label": "row 2",
            "cells": [
                {"kind": "locked", "value": "true"},
                {"kind": "locked", "value": "false"},
                {"kind": "text", "value": "false", "accept": ["f", "no"]},
            ],
        },
        {
            "label": "row 3",
            "cells": [
                {"kind": "equation", "value": "x**2 + 2*x"},
                {"kind": "numeric", "value": "4", "tolerance": 0.5},
                {"kind": "text", "value": "true"},
            ],
        },
    ],
}


def response(grid: list[list[Any]]) -> Any:
    return grid


class TestValidation:
    def test_valid_answer_passes(self) -> None:
        assert validate_table_answer(TRUTH_TABLE) == []

    def test_headers_and_rows_required(self) -> None:
        assert validate_table_answer({}) != []
        assert validate_table_answer({"headers": [], "rows": []}) != []

    def test_row_must_align_with_headers(self) -> None:
        problems = validate_table_answer(
            {
                "headers": ["a", "b"],
                "rows": [{"label": "r", "cells": [{"kind": "text", "value": "x"}]}],
            }
        )
        assert any("align" in problem for problem in problems)

    def test_at_least_one_fillable_cell(self) -> None:
        problems = validate_table_answer(
            {
                "headers": ["a"],
                "rows": [{"label": "r", "cells": [{"kind": "locked", "value": "x"}]}],
            }
        )
        assert any("fillable" in problem for problem in problems)

    def test_unknown_cell_kind_rejected(self) -> None:
        problems = validate_table_answer(
            {
                "headers": ["a"],
                "rows": [{"label": "r", "cells": [{"kind": "boolean", "value": "x"}]}],
            }
        )
        assert any("kind" in problem for problem in problems)

    def test_numeric_value_must_parse(self) -> None:
        problems = validate_table_answer(
            {
                "headers": ["a"],
                "rows": [
                    {"label": "r", "cells": [{"kind": "numeric", "value": "1/2"}]}
                ],
            }
        )
        assert any("numeric" in problem for problem in problems)

    def test_equation_value_must_parse(self) -> None:
        problems = validate_table_answer(
            {
                "headers": ["a"],
                "rows": [
                    {"label": "r", "cells": [{"kind": "equation", "value": "x^^2"}]}
                ],
            }
        )
        assert any("equation" in problem for problem in problems)

    def test_negative_tolerance_rejected(self) -> None:
        problems = validate_table_answer(
            {
                "headers": ["a"],
                "rows": [
                    {
                        "label": "r",
                        "cells": [
                            {"kind": "numeric", "value": "1", "tolerance": -1}
                        ],
                    }
                ],
            }
        )
        assert any("tolerance" in problem for problem in problems)


class TestPublicInput:
    def test_locked_cells_expose_text_only(self) -> None:
        grid = table_public_input(TRUTH_TABLE)
        assert grid is not None
        assert grid["headers"] == ["p", "q", "p and q"]
        assert grid["cells"][0][0] == {"kind": "locked", "text": "true"}
        assert grid["cells"][0][2] == {"kind": "text"}
        assert grid["cells"][2][0] == {"kind": "equation"}
        assert "value" not in grid["cells"][2][0]

    def test_garbage_returns_none(self) -> None:
        assert table_public_input({"headers": "no"}) is None


class TestGrading:
    def test_all_cells_correct(self) -> None:
        result = grade_table_fill(
            TRUTH_TABLE,
            [["", "", "True"], ["", "", "f"], ["x^2+2x", "4.2", "TRUE"]],
        )
        assert result["correct"] is True
        assert result["partial_credit"] == 1.0
        assert result["error_tags"] == []

    def test_text_accept_alternatives(self) -> None:
        result = grade_table_fill(
            TRUTH_TABLE, [["", "", "true"], ["", "", "no"], ["", "", ""]]
        )
        assert result["partial_credit"] == round(2 / 5, 4)

    def test_numeric_tolerance_window(self) -> None:
        result = grade_table_fill(
            TRUTH_TABLE, [["", "", ""], ["", "", ""], ["", "3.6", ""]]
        )
        assert result["partial_credit"] == round(1 / 5, 4)

    def test_equation_graded_by_chain(self) -> None:
        result = grade_table_fill(
            TRUTH_TABLE, [["", "", ""], ["", "", ""], ["2x+x**2", "", ""]]
        )
        assert result["partial_credit"] == round(1 / 5, 4)

    def test_empty_response_scores_zero(self) -> None:
        result = grade_table_fill(TRUTH_TABLE, [["", "", ""], ["", "", ""], ["", "", ""]])
        assert result["correct"] is False
        assert result["partial_credit"] == 0.0
        assert "wrong_cell" in result["error_tags"]

    def test_malformed_response_scores_zero(self) -> None:
        payloads: list[Any] = ["hello", None, [[], []]]
        for payload in payloads:
            result = grade_table_fill(TRUTH_TABLE, payload)
            assert result["correct"] is False
            assert result["partial_credit"] == 0.0
            assert result["error_tags"] == ["malformed"]
