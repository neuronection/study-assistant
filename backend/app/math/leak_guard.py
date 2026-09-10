import re
from dataclasses import dataclass

from ..math.equivalence import equivalent

_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\$(.+?)\$")
_NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")

_SIMPLE_TOKEN_RE = re.compile(r"[+\-*/^()]")


@dataclass(frozen=True)
class LeakCheck:
    leaks: bool
    expression: str | None
    detail: str


def extract_math(text: str) -> list[str]:
    found: list[str] = []
    for match in _DISPLAY_MATH_RE.finditer(text):
        found.append(match.group(1).strip())
    stripped = _DISPLAY_MATH_RE.sub(" ", text)
    for match in _INLINE_MATH_RE.finditer(stripped):
        found.append(match.group(1).strip())
    plain = _INLINE_MATH_RE.sub(" ", stripped)
    for match in _NUMBER_RE.finditer(plain):
        found.append(match.group(1))
    return [entry for entry in found if entry]


def _is_trivial_number(value: str) -> bool:
    try:
        return abs(float(value)) <= 10 and "." not in value
    except ValueError:
        return False


def check_leak(hint_text: str, expected: str) -> LeakCheck:
    for expression in extract_math(hint_text):
        if _is_trivial_number(expression):
            continue
        if _SIMPLE_TOKEN_RE.search(expression) or len(expression) > 3:
            result = equivalent(expression, expected)
            if result.equivalent:
                return LeakCheck(
                    True, expression, f"hint contains answer-equivalent math ({expression})"
                )
        else:
            import re as _re

            if _re.escape(expression.lower()) in _re.escape(expected.lower()) and not (
                _is_trivial_number(expression)
            ):
                return LeakCheck(
                    True, expression, f"hint contains the answer token ({expression})"
                )
    return LeakCheck(False, None, "no leak detected")
