from typing import Any

import sympy

from .equivalence import parse_math

MODES = ("value", "point")
MIN_SAMPLES = 20
MAX_SAMPLES = 400
DEFAULT_SAMPLES = 96


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_float(value: Any) -> float | None:
    return float(value) if _is_number(value) else None


def graph_domain(answer: dict[str, Any]) -> tuple[float, float, int]:
    x_min = _as_float(answer.get("x_min")) or -10.0
    x_max = _as_float(answer.get("x_max")) or 10.0
    samples = answer.get("samples", DEFAULT_SAMPLES)
    if not isinstance(samples, int) or not MIN_SAMPLES <= samples <= MAX_SAMPLES:
        samples = DEFAULT_SAMPLES
    return x_min, x_max, samples


def build_graph_data(
    expression: str, x_min: float, x_max: float, samples: int
) -> tuple[list[float], list[float]]:
    expr = parse_math(expression)
    x = sympy.Symbol("x")
    fn = sympy.lambdify(x, expr, modules=["math"])
    xs: list[float] = []
    ys: list[float] = []
    step = (x_max - x_min) / (samples - 1)
    for index in range(samples):
        value = x_min + index * step
        y = fn(value)
        y_f = float(y)
        if y_f != y_f or y_f in (float("inf"), float("-inf")):
            raise ValueError(f"expression is not finite at x={value}")
        xs.append(round(value, 6))
        ys.append(round(y_f, 6))
    return xs, ys


def graph_figure(xs: list[float], ys: list[float]) -> dict[str, Any]:
    return {
        "data": [
            {
                "x": xs,
                "y": ys,
                "mode": "lines",
                "type": "scatter",
                "line": {"color": "#2563eb", "width": 2},
            }
        ],
        "layout": {"showlegend": False, "xaxis": {"zeroline": True}, "yaxis": {"zeroline": True}},
    }


def _evaluate_at(expression: str, point_x: float) -> float:
    expr = parse_math(expression)
    value = expr.subs(sympy.Symbol("x"), sympy.Float(point_x))
    result = float(value.evalf())
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError("expression is not finite at the target point")
    return result


def nearest_index(xs: list[float], point_x: float) -> int:
    return min(range(len(xs)), key=lambda index: abs(xs[index] - point_x))


def materialize_graph_answer(answer: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Compute every graded number deterministically from the expression.

    The model authors only the expression, the domain and the target x; the
    expected value / data-point index / default tolerance are computed here.
    """
    problems: list[str] = []
    expression = answer.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        return answer, ["expression required"]
    mode = answer.get("mode")
    if mode not in MODES:
        return answer, ["mode must be value or point"]
    try:
        x_min, x_max, samples = graph_domain(answer)
        if _as_float(answer.get("x_min")) is None or _as_float(answer.get("x_max")) is None:
            raise ValueError
        if x_min >= x_max:
            raise ValueError
    except (TypeError, ValueError):
        return answer, ["domain needs numeric x_min < x_max"]
    raw_point_x = _as_float(answer.get("point_x"))
    if raw_point_x is None or not x_min <= raw_point_x <= x_max:
        return answer, ["point_x must be a number inside the domain"]
    try:
        build_graph_data(expression, x_min, x_max, samples)
    except Exception:
        return answer, ["expression is not finite over the whole domain"]
    try:
        exact = _evaluate_at(expression, raw_point_x)
    except Exception:
        return answer, ["expression does not evaluate at point_x"]

    materialized = dict(answer)
    if mode == "value":
        tolerance = _as_float(answer.get("tolerance"))
        if tolerance is None or tolerance <= 0:
            try:
                _, ys = build_graph_data(expression, x_min, x_max, samples)
                span = max(ys) - min(ys)
            except Exception:
                span = 2.0
            materialized["tolerance"] = round(max(span * 0.02, 1e-6), 6)
        else:
            materialized["tolerance"] = tolerance
        materialized["value"] = round(exact, 6)
    else:
        xs, _ = build_graph_data(expression, x_min, x_max, samples)
        materialized["point_index"] = nearest_index(xs, raw_point_x)
    return materialized, problems


def validate_graph_answer(answer: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    expression = answer.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        problems.append("expression required")
        return problems
    mode = answer.get("mode")
    if mode not in MODES:
        problems.append("mode must be value or point")
        return problems
    try:
        x_min, x_max, samples = graph_domain(answer)
        if _as_float(answer.get("x_min")) is None or _as_float(answer.get("x_max")) is None:
            raise ValueError
        if x_min >= x_max:
            raise ValueError
        build_graph_data(expression, x_min, x_max, samples)
    except (TypeError, ValueError):
        problems.append("domain needs numeric x_min < x_max")
        return problems
    except Exception:
        problems.append("expression is not finite over the whole domain")
        return problems
    point_x = _as_float(answer.get("point_x"))
    if point_x is None or not x_min <= point_x <= x_max:
        problems.append("point_x must be a number inside the domain")
        return problems
    if mode == "value":
        value = _as_float(answer.get("value"))
        if value is not None:
            try:
                exact = _evaluate_at(expression, point_x)
            except Exception:
                problems.append("expression does not evaluate at point_x")
                return problems
            tolerance = _as_float(answer.get("tolerance"))
            limit = tolerance if tolerance is not None and tolerance > 0 else 0.0
            if abs(value - exact) > max(limit, 1e-6):
                problems.append(
                    "declared value does not match the computed f(point_x)"
                )
        tolerance = answer.get("tolerance")
        if tolerance is not None:
            parsed = _as_float(tolerance)
            if parsed is None or parsed <= 0:
                problems.append("tolerance must be a positive number")
    else:
        index = answer.get("point_index")
        if index is not None:
            if not isinstance(index, int) or isinstance(index, bool):
                problems.append("point_index must be an integer")
            else:
                xs, _ = build_graph_data(expression, x_min, x_max, samples)
                expected = nearest_index(xs, point_x)
                if index != expected:
                    problems.append(
                        "declared point_index does not match the nearest sample"
                    )
    return problems


def grade_graph_read(answer: dict[str, Any], response: Any) -> dict[str, Any]:
    mode = answer.get("mode")
    if not isinstance(response, dict):
        return {
            "correct": False,
            "partial_credit": 0.0,
            "feedback": ["answer is not a valid graph payload"],
            "error_tags": ["malformed"],
        }
    if mode == "value":
        value = _as_float(response.get("value"))
        if value is None:
            return {
                "correct": False,
                "partial_credit": 0.0,
                "feedback": ["answer must be a number"],
                "error_tags": ["malformed"],
            }
        expected = _as_float(answer.get("value")) or 0.0
        tolerance = _as_float(answer.get("tolerance")) or 0.05
        ok = abs(value - expected) <= tolerance
        return {
            "correct": ok,
            "partial_credit": 1.0 if ok else 0.0,
            "feedback": ["correct" if ok else "incorrect"],
            "error_tags": [] if ok else ["wrong_value"],
        }
    if mode == "point":
        index = response.get("index")
        if not isinstance(index, int) or isinstance(index, bool):
            return {
                "correct": False,
                "partial_credit": 0.0,
                "feedback": ["answer must name a point on the graph"],
                "error_tags": ["malformed"],
            }
        ok = index == answer.get("point_index")
        return {
            "correct": ok,
            "partial_credit": 1.0 if ok else 0.0,
            "feedback": ["correct" if ok else "incorrect"],
            "error_tags": [] if ok else ["wrong_point"],
        }
    return {
        "correct": False,
        "partial_credit": 0.0,
        "feedback": ["question has an unknown graph mode"],
        "error_tags": ["config"],
    }
