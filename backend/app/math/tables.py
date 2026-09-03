from typing import Any

from .equivalence import equivalent, parse_math

CELL_KINDS = ("text", "numeric", "equation", "locked")
MAX_ROWS = 10
MAX_COLUMNS = 8
DEFAULT_TOLERANCE = 1e-6


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _cell_kind(cell: Any) -> str | None:
    if isinstance(cell, dict):
        kind = cell.get("kind")
        if isinstance(kind, str):
            return kind
    return None


def _cell_value(cell: Any) -> str | None:
    if isinstance(cell, dict):
        value = cell.get("value")
        if isinstance(value, str):
            return value
    return None


def _normalize_text(value: str) -> str:
    import re

    lowered = value.strip().lower()
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return re.sub(r"\s+", " ", lowered)


def validate_table_answer(answer: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    headers = answer.get("headers")
    rows = answer.get("rows")
    if not isinstance(headers, list) or not headers:
        problems.append("headers must be a non-empty list")
        return problems
    if not isinstance(rows, list) or not rows:
        problems.append("rows must be a non-empty list")
        return problems
    if len(headers) > MAX_COLUMNS:
        problems.append(f"at most {MAX_COLUMNS} columns allowed")
    if len(rows) > MAX_ROWS:
        problems.append(f"at most {MAX_ROWS} rows allowed")
    for index, header in enumerate(headers):
        if not isinstance(header, str) or not header.strip():
            problems.append(f"header {index}: must be a non-empty string")
    fillable = 0
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"row {row_index}: not an object")
            continue
        label = row.get("label")
        if not isinstance(label, str) or not label.strip():
            problems.append(f"row {row_index}: label must be a non-empty string")
        cells = row.get("cells")
        if not isinstance(cells, list) or len(cells) != len(headers):
            problems.append(f"row {row_index}: cells must align with headers")
            continue
        for cell_index, cell in enumerate(cells):
            kind = _cell_kind(cell)
            if kind not in CELL_KINDS:
                problems.append(
                    f"cell ({row_index}, {cell_index}): kind must be one of "
                    + "|".join(CELL_KINDS)
                )
                continue
            value = _cell_value(cell)
            if kind == "locked":
                if value is None or not value.strip():
                    problems.append(
                        f"cell ({row_index}, {cell_index}): locked cells need text"
                    )
                continue
            fillable += 1
            if value is None or not value.strip():
                problems.append(
                    f"cell ({row_index}, {cell_index}): expected value required"
                )
                continue
            if kind == "numeric":
                try:
                    float(value)
                except ValueError:
                    problems.append(
                        f"cell ({row_index}, {cell_index}): numeric value must "
                        "parse as a number"
                    )
                tolerance = cell.get("tolerance") if isinstance(cell, dict) else None
                if tolerance is not None and (
                    not _is_number(tolerance) or float(tolerance) < 0
                ):
                    problems.append(
                        f"cell ({row_index}, {cell_index}): tolerance must be "
                        "a non-negative number"
                    )
            elif kind == "equation":
                try:
                    parse_math(value)
                except Exception:
                    problems.append(
                        f"cell ({row_index}, {cell_index}): equation value must "
                        "parse as math"
                    )
    if fillable == 0:
        problems.append("at least one fillable cell is required")
    return problems


def table_public_input(answer: dict[str, Any]) -> dict[str, Any] | None:
    headers = answer.get("headers")
    rows = answer.get("rows")
    if not isinstance(headers, list) or not isinstance(rows, list):
        return None
    grid: list[list[dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        cells = row.get("cells")
        row_cells: list[dict[str, Any]] = []
        if not isinstance(cells, list):
            return None
        for cell in cells:
            kind = _cell_kind(cell)
            if kind == "locked":
                row_cells.append({"kind": "locked", "text": _cell_value(cell) or ""})
            elif kind in ("text", "numeric", "equation"):
                row_cells.append({"kind": kind})
            else:
                return None
        grid.append(row_cells)
    return {
        "widget": "table_fill",
        "headers": [str(header) for header in headers],
        "row_labels": [
            str(row.get("label", "")) if isinstance(row, dict) else ""
            for row in rows
        ],
        "cells": grid,
    }


def _grade_cell(cell: dict[str, Any], response_value: str) -> bool:
    kind = cell.get("kind")
    value = _cell_value(cell) or ""
    given = response_value.strip()
    if kind == "text":
        accepted = [value]
        extra = cell.get("accept")
        if isinstance(extra, list):
            accepted += [str(entry) for entry in extra if isinstance(entry, str)]
        return _normalize_text(given) in {_normalize_text(entry) for entry in accepted}
    if kind == "numeric":
        try:
            number = float(given.replace(",", "."))
        except ValueError:
            return False
        expected = float(value)
        raw_tolerance = cell.get("tolerance")
        tolerance_value = DEFAULT_TOLERANCE
        if isinstance(raw_tolerance, (int, float)) and not isinstance(
            raw_tolerance, bool
        ):
            tolerance_value = float(raw_tolerance)
        return abs(number - expected) <= tolerance_value
    if kind == "equation":
        if not given:
            return False
        return equivalent(given, value).equivalent
    return False


def grade_table_fill(answer: dict[str, Any], response: Any) -> dict[str, Any]:
    """Per-cell deterministic grading. Returns correct/partial/feedback/tags."""
    rows = answer.get("rows", [])
    if not isinstance(response, list) or len(response) != len(rows):
        return {
            "correct": False,
            "partial_credit": 0.0,
            "feedback": ["answer is not a valid table payload"],
            "error_tags": ["malformed"],
        }
    fillable = 0
    correct_cells = 0
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        cells = row.get("cells", [])
        row_response = response[row_index]
        values = row_response if isinstance(row_response, list) else []
        for cell_index, cell in enumerate(cells):
            kind = _cell_kind(cell)
            if kind in ("text", "numeric", "equation"):
                fillable += 1
                given = (
                    str(values[cell_index])
                    if isinstance(values, list)
                    and cell_index < len(values)
                    and values[cell_index] is not None
                    else ""
                )
                if _grade_cell(cell, given):
                    correct_cells += 1
    if fillable == 0:
        return {
            "correct": False,
            "partial_credit": 0.0,
            "feedback": ["question has no fillable cells"],
            "error_tags": ["config"],
        }
    partial = round(correct_cells / fillable, 4)
    feedback = [f"{correct_cells}/{fillable} cells correct"]
    tags: list[str] = []
    if partial < 1.0:
        tags.append("wrong_cell")
    return {
        "correct": correct_cells == fillable,
        "partial_credit": 1.0 if correct_cells == fillable else partial,
        "feedback": feedback,
        "error_tags": tags,
    }
