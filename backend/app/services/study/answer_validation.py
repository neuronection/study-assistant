from typing import Any

from ...math.equivalence import expressions_equivalent

PRACTICE_ANSWER_KINDS = ("single", "multi", "truefalse", "numeric", "equation")


def validate_answer_shape(
    kind: str,
    answer: dict[str, Any],
    options: list[Any] | None,
    label: str,
) -> list[str]:
    problems: list[str] = []
    if kind in ("single", "multi"):
        if not isinstance(options, list) or len(options) < 2:
            problems.append(f"{label}: needs at least 2 options")
        elif kind == "single":
            try:
                choice = int(answer.get("index", -1))
                if not 0 <= choice < len(options):
                    problems.append(f"{label}: answer index out of range")
            except (TypeError, ValueError):
                problems.append(f"{label}: single answer needs integer index")
        else:
            indices = answer.get("indices")
            if not isinstance(indices, list) or not indices:
                problems.append(f"{label}: multi answer needs indices list")
            elif any(
                not 0 <= int(i) < len(options) for i in indices if str(i).isdigit()
            ):
                problems.append(f"{label}: multi index out of range")
    elif kind == "truefalse":
        if not isinstance(answer.get("value"), bool):
            problems.append(f"{label}: truefalse answer must be true/false")
    elif kind == "numeric":
        try:
            float(answer.get("value") or "not-a-number")
        except (TypeError, ValueError):
            problems.append(f"{label}: numeric answer needs numeric value")
    elif kind == "equation" and not str(answer.get("value", "")).strip():
        problems.append(f"{label}: equation answer needs value")
    return problems


def validate_distractor_equivalence(
    kind: str,
    answer: dict[str, Any],
    options: list[Any] | None,
    label: str,
) -> list[str]:
    if kind != "equation" or not isinstance(options, list) or len(options) < 2:
        return []
    expected = str(answer.get("value", ""))
    problems: list[str] = []
    for option_index, option in enumerate(options):
        if expressions_equivalent(str(option), expected):
            problems.append(f"{label}: distractor {option_index} equals the answer")
    return problems
