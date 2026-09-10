from typing import Any

from ...domain.models import Question

LETTERS = "ABCDEFGH"


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def answer_key_text(question: Question) -> str:
    """Deterministic human-readable correct answer for the printable key."""
    answer = question.answer or {}
    qtype = question.type
    if qtype == "single":
        index = answer.get("index")
        if isinstance(index, int) and 0 <= index < len(LETTERS):
            return LETTERS[index]
        return str(index)
    if qtype == "truefalse":
        return "True" if answer.get("value") else "False"
    if qtype == "multi":
        indices = answer.get("indices")
        if isinstance(indices, list):
            return ", ".join(
                LETTERS[int(index)]
                for index in indices
                if isinstance(index, int) and 0 <= index < len(LETTERS)
            )
        return str(indices)
    if qtype == "text":
        value = str(answer.get("value", ""))
        accept = [str(item) for item in answer.get("accept", [])]
        if accept:
            return f"{value} (also accepted: {', '.join(accept)})"
        return value
    if qtype == "numeric":
        raw_value = answer.get("value")
        rendered = _format_number(float(raw_value)) if raw_value is not None else "?"
        tolerance = answer.get("tolerance")
        if tolerance is not None:
            rendered += f" (±{_format_number(float(tolerance))})"
        return rendered
    if qtype == "equation":
        expected: Any | None = None
        if question.sympy_check is not None:
            expected = question.sympy_check.get("expected")
        if expected is None:
            expected = answer.get("value")
        return str(expected) if expected is not None else "?"
    if qtype == "numberline":
        parts: list[str] = []
        for point in answer.get("points", []):
            point_value = point.get("value") if isinstance(point, dict) else point
            if isinstance(point_value, (int, float)):
                parts.append(_format_number(float(point_value)))
        for interval in answer.get("intervals", []):
            if isinstance(interval, dict) and "lo" in interval and "hi" in interval:
                parts.append(
                    f"{_format_number(float(interval['lo']))}-{_format_number(float(interval['hi']))}"
                )
        return ", ".join(parts) if parts else "?"
    if qtype == "table_fill":
        rows = answer.get("rows", [])
        rendered_rows: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            cells: list[str] = []
            for cell in row.get("cells", []):
                if isinstance(cell, dict) and cell.get("kind") in (
                    "text",
                    "numeric",
                    "equation",
                ):
                    cell_value = cell.get("value")
                    cells.append(str(cell_value) if cell_value is not None else "?")
                elif isinstance(cell, dict):
                    cells.append(str(cell.get("value", "")))
                else:
                    cells.append(str(cell))
            rendered_rows.append(" | ".join(cells))
        return "; ".join(rendered_rows) if rendered_rows else "?"
    if qtype == "composite":
        parts = answer.get("parts", [])
        rendered_parts: list[str] = []
        for index, part in enumerate(parts, start=1):
            if not isinstance(part, dict):
                continue
            rendered_parts.append(f"({index}) {_part_key(part)}")
        return " ".join(rendered_parts) if rendered_parts else "?"
    if qtype == "graph_read":
        mode = answer.get("mode")
        if mode == "point" and answer.get("point_x") is not None:
            return f"x = {_format_number(float(answer['point_x']))}"
        if answer.get("expression") is not None:
            return str(answer["expression"])
        return "?"
    if qtype == "code":
        tests = answer.get("tests", [])
        rendered_cases: list[str] = []
        for index, test in enumerate(tests, start=1):
            if not isinstance(test, dict):
                continue
            case_expected = test.get("expected_stdout", test.get("expected"))
            rendered_cases.append(f"case {index}: {case_expected!r}")
        return "; ".join(rendered_cases) if rendered_cases else "?"
    return "?"


def _part_key(part: dict[str, Any]) -> str:
    kind = str(part.get("kind", part.get("type", "")))
    if kind == "choice":
        index = part.get("index")
        return LETTERS[int(index)] if isinstance(index, int) and 0 <= index < len(LETTERS) else "?"
    if "value" in part:
        value = part["value"]
        if isinstance(value, (int, float)):
            return _format_number(float(value))
        return str(value)
    if "indices" in part and isinstance(part["indices"], list):
        return ", ".join(
            LETTERS[int(index)] for index in part["indices"] if isinstance(index, int)
        )
    return "?"
