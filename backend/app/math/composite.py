from typing import Any

import sympy

from .equivalence import equivalent, parse_math

PART_TYPES = ("text", "numeric", "equation")
MAX_PARTS = 4
PART_SYMBOLS = ("a", "b", "c", "d")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def part_symbols(count: int) -> list[sympy.Symbol]:
    return [sympy.Symbol(PART_SYMBOLS[index]) for index in range(count)]


def _part_symbol(part_index: int) -> sympy.Symbol:
    return sympy.Symbol(PART_SYMBOLS[part_index])


def validate_relation(relation: str, part_index: int, parts: list[dict[str, Any]]) -> list[str]:
    """The relation of part `part_index` (0-based) must only use prior parts and
    reproduce the declared value from the declared prior answers."""
    problems: list[str] = []
    try:
        expr = parse_math(relation)
    except Exception:
        problems.append(f"part {part_index}: follow_through must parse as math")
        return problems
    allowed = {symbol.name for symbol in part_symbols(part_index)}
    unknown = {symbol.name for symbol in expr.free_symbols} - allowed
    if unknown:
        problems.append(
            f"part {part_index}: follow_through may only reference prior parts "
            + ", ".join(sorted(allowed))
        )
        return problems
    declared: dict[sympy.Symbol, sympy.Expr] = {}
    for prior_index in range(part_index):
        prior = parts[prior_index]
        raw = str(prior.get("value", ""))
        try:
            declared[_part_symbol(prior_index)] = parse_math(raw)
        except Exception:
            problems.append(f"part {part_index}: prior part {prior_index} value must parse")
            return problems
    try:
        recomputed = expr.subs(declared) if declared else expr
        recomputed = sympy.simplify(recomputed)
        str(recomputed)
    except Exception:
        problems.append(f"part {part_index}: follow_through does not evaluate")
        return problems
    declared_value = str(parts[part_index].get("value", ""))
    if not equivalent(str(recomputed), declared_value).equivalent:
        problems.append(
            f"part {part_index}: follow_through on the declared prior answers "
            "does not reproduce the declared value"
        )
    perturbed = dict(declared)
    first_symbol = _part_symbol(0) if declared else None
    if first_symbol is not None:
        base = declared[first_symbol]
        shifted = (
            sympy.sympify(base) + 1
            if base.is_number
            else sympy.simplify(base + 1)
        )
        perturbed[first_symbol] = shifted
        try:
            sympy.simplify(expr.subs(perturbed))
        except Exception:
            problems.append(
                f"part {part_index}: follow_through fails on a perturbed prior answer"
            )
    return problems


def validate_composite_answer(answer: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    parts = answer.get("parts")
    if not isinstance(parts, list) or not 2 <= len(parts) <= MAX_PARTS:
        problems.append(f"parts must be a list of 2-{MAX_PARTS} sub-questions")
        return problems
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            problems.append(f"part {index}: not an object")
            continue
        ptype = part.get("type")
        if ptype not in PART_TYPES:
            problems.append(f"part {index}: type must be one of " + "|".join(PART_TYPES))
            continue
        value = part.get("value")
        if not isinstance(value, str) or not value.strip():
            problems.append(f"part {index}: expected value required")
            continue
        if ptype == "numeric":
            try:
                float(value)
            except ValueError:
                problems.append(f"part {index}: numeric value must parse as a number")
            tolerance = part.get("tolerance")
            if tolerance is not None and (
                not _is_number(tolerance) or float(tolerance) < 0
            ):
                problems.append(f"part {index}: tolerance must be a non-negative number")
        elif ptype == "equation":
            try:
                parse_math(value)
            except Exception:
                problems.append(f"part {index}: equation value must parse as math")
        relation = part.get("follow_through")
        if isinstance(relation, str) and relation.strip():
            if ptype == "text":
                problems.append(
                    f"part {index}: follow_through is not supported for text parts"
                )
            else:
                problems.extend(validate_relation(relation, index, parts))
    return problems


def composite_public_input(answer: dict[str, Any]) -> dict[str, Any] | None:
    parts = answer.get("parts")
    if not isinstance(parts, list):
        return None
    public: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            return None
        ptype = part.get("type")
        if ptype not in PART_TYPES:
            return None
        public.append({"type": ptype})
    return {"widget": "composite", "parts": public}


def _normalize_text(value: str) -> str:
    import re

    lowered = value.strip().lower()
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return re.sub(r"\s+", " ", lowered)


def _grade_value(ptype: str, expected: str, given: str, tolerance: Any) -> bool:
    if not given.strip():
        return False
    if ptype == "text":
        return _normalize_text(given) == _normalize_text(expected)
    if ptype == "numeric":
        try:
            number = float(given.replace(",", "."))
        except ValueError:
            return False
        try:
            target = float(expected)
        except ValueError:
            return False
        limit = float(tolerance) if _is_number(tolerance) else 1e-6
        return abs(number - target) <= limit
    return equivalent(given, expected).equivalent


def _recompute(relation: str, prior_responses: list[str]) -> str | None:
    try:
        expr = parse_math(relation)
        substitution = {
            _part_symbol(index): parse_math(prior_responses[index])
            for index in range(len(prior_responses))
        }
        recomputed = sympy.simplify(expr.subs(substitution))
        return str(recomputed)
    except Exception:
        return None


def grade_composite(answer: dict[str, Any], response: Any) -> dict[str, Any]:
    """Per-part deterministic grading with follow-through credit.

    Returns correct/partial_credit/feedback/flags where flags marks the
    1-based parts graded through a follow-through relation.
    """
    parts = answer.get("parts", [])
    if not isinstance(response, list) or len(response) != len(parts):
        return {
            "correct": False,
            "partial_credit": 0.0,
            "feedback": ["answer is not a valid composite payload"],
            "error_tags": ["malformed"],
            "flags": [],
        }
    feedback: list[str] = []
    flags: list[int] = []
    correct_parts = 0
    prior_responses: list[str] = []
    prior_correct: list[bool] = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if not isinstance(ptype, str):
            continue
        raw = response[index]
        given = "" if raw is None else str(raw)
        expected = str(part.get("value", ""))
        relation = part.get("follow_through")
        used_follow_through = False
        if (
            isinstance(relation, str)
            and relation.strip()
            and prior_responses
            and not all(prior_correct)
        ):
            recomputed = _recompute(relation, prior_responses)
            if recomputed is not None and _grade_value(
                ptype, recomputed, given, part.get("tolerance")
            ):
                used_follow_through = True
        ok = used_follow_through or _grade_value(
            ptype, expected, given, part.get("tolerance")
        )
        label = f"({chr(ord('a') + index)})"
        if ok and used_follow_through:
            feedback.append(f"part {label}: correct (follow-through)")
            flags.append(index + 1)
        elif ok:
            feedback.append(f"part {label}: correct")
        else:
            feedback.append(f"part {label}: incorrect")
        correct_parts += 1 if ok else 0
        prior_responses.append(given)
        prior_correct.append(ok)
    total = len(parts)
    if total == 0:
        return {
            "correct": False,
            "partial_credit": 0.0,
            "feedback": ["question has no parts"],
            "error_tags": ["config"],
            "flags": [],
        }
    partial = round(correct_parts / total, 4)
    tags = ["follow_through"] if flags else []
    if partial < 1.0:
        tags.append("wrong_part")
    return {
        "correct": correct_parts == total,
        "partial_credit": 1.0 if correct_parts == total else partial,
        "feedback": [", ".join(feedback)],
        "error_tags": tags,
        "flags": flags,
    }
