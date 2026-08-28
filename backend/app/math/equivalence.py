import random
import re
from dataclasses import dataclass

import sympy
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

SamplePoints = list[dict[str, complex]]

_TRANSFORMATIONS = (*standard_transformations, implicit_multiplication_application)

_FRAC_RE = re.compile(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_SQRT_RE = re.compile(r"\\sqrt\s*\{([^{}]*)\}")
_SQRT_N_RE = re.compile(r"\\sqrt\s*\[(\d+)\]\s*\{([^{}]*)\}")


@dataclass(frozen=True)
class ChainResult:
    equivalent: bool
    stage: str
    detail: str


def _normalize_latex(text: str) -> str:
    cleaned = text.strip().strip("$")
    for latex, replacement in [
        (r"\left", ""),
        (r"\right", ""),
        (r"\cdot", "*"),
        (r"\times", "*"),
        (r"\div", "/"),
        (r"\lvert", "|"),
        (r"\rvert", "|"),
        (r"\,", " "),
        (r"\quad", " "),
        (r"\qquad", " "),
    ]:
        cleaned = cleaned.replace(latex, replacement)
    cleaned = _SQRT_N_RE.sub(r"((\2)**(1/\1))", cleaned)
    cleaned = _SQRT_RE.sub(r"(sqrt(\1))", cleaned)
    cleaned = _FRAC_RE.sub(r"((\1)/(\2))", cleaned)
    cleaned = cleaned.replace(r"\pi", "pi")
    cleaned = re.sub(
        r"\\[{[]((?:[^,\[\]()]|,|\([^()]*\))*)\\[}\]]",
        r"__SET__(\1)",
        cleaned,
    )
    cleaned = _abs_to_abs(cleaned)
    cleaned = cleaned.replace("{", "(").replace("}", ")")
    cleaned = cleaned.replace("^", "**").replace("\\", "")
    return cleaned


def _abs_to_abs(text: str) -> str:
    result: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "|":
            result.append(text[index])
            index += 1
            continue
        depth = 1
        paren = 0
        cursor = index + 1
        while cursor < length and depth > 0:
            character = text[cursor]
            if character == "|":
                depth -= 1
            elif character in "([{":
                paren += 1
            elif character in ")]}":
                paren -= 1
            cursor += 1
        if depth != 0 or paren != 0:
            result.append(text[index])
            index += 1
            continue
        result.append(f" Abs({text[index + 1 : cursor - 1]})")
        index = cursor
    return "".join(result)


def _split_top_level(text: str) -> list[str]:
    is_set = text.startswith("__SET__(") and text.endswith(")")
    body = text[len("__SET__(") : -1] if is_set else text
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for character in body:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character in (",", ";") and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    parts.append("".join(current).strip())
    parts = [part for part in parts if part]
    return parts if parts else [text]


def _split_equation(statement: str) -> tuple[str, str] | None:
    depth = 0
    for index, character in enumerate(statement):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "=" and depth == 0:
            previous = statement[index - 1] if index > 0 else ""
            following = statement[index + 1] if index + 1 < len(statement) else ""
            if previous in "=<>!" or following == "=":
                continue
            return statement[:index], statement[index + 1 :]
    return None


def _parse_statement(statement: str, locals_map: dict[str, object]) -> sympy.Expr:
    equation = _split_equation(statement)
    if equation is None:
        return parse_expr(
            statement,
            local_dict=locals_map,
            transformations=_TRANSFORMATIONS,
            evaluate=True,
        )
    lhs, rhs = equation
    left = parse_expr(
        lhs.strip(),
        local_dict=locals_map,
        transformations=_TRANSFORMATIONS,
        evaluate=True,
    )
    right = parse_expr(
        rhs.strip(),
        local_dict=locals_map,
        transformations=_TRANSFORMATIONS,
        evaluate=True,
    )
    return sympy.sympify(left - right)


def parse_math(text: str) -> sympy.Expr:
    cleaned = _normalize_latex(text)
    if not cleaned or not re.search(r"[0-9a-zA-Z]", cleaned):
        raise ValueError("empty expression")
    locals_map: dict[str, object] = {
        name: sympy.Symbol(name) for name in ("x", "y", "t", "n", "u", "v")
    }
    is_set = cleaned.startswith("__SET__(") and cleaned.endswith(")")
    parts = _split_top_level(cleaned)
    parsed = [sympy.sympify(_parse_statement(part, locals_map)) for part in parts]
    parsed = sympy.FiniteSet(*parsed) if is_set or len(parsed) > 1 else parsed[0]
    if sympy.Symbol("i") in parsed.free_symbols:
        parsed = parsed.subs(sympy.Symbol("i"), sympy.I)
    if sympy.Symbol("e") in parsed.free_symbols:
        parsed = parsed.subs(sympy.Symbol("e"), sympy.E)
    return sympy.sympify(parsed)


def _free_symbols(expr: sympy.Expr) -> list[sympy.Symbol]:
    return sorted(expr.free_symbols, key=lambda symbol: symbol.name)


def _sample_points(
    symbols: list[sympy.Symbol], count: int = 12
) -> SamplePoints:
    rng = random.Random(20260819)
    points: SamplePoints = []
    for _ in range(count):
        point: dict[str, complex] = {}
        for symbol in symbols:
            real = rng.uniform(0.35, 3.1)
            imag = rng.uniform(0.1, 0.9)
            point[str(symbol)] = complex(real, imag)
        points.append(point)
    return points


def _safe_eval(expr: sympy.Expr, point: dict[str, complex]) -> complex | None:
    try:
        value = complex(expr.subs({sympy.Symbol(k): v for k, v in point.items()}))
        if value != value or abs(value) > 1e12:
            return None
        return value
    except Exception:
        return None


def _symbolic_stage(student: sympy.Expr, expected: sympy.Expr) -> bool:
    try:
        if isinstance(student, sympy.Set) or isinstance(expected, sympy.Set):
            if isinstance(student, sympy.Set) != isinstance(expected, sympy.Set):
                return False
            simplified = sympy.simplify(student) if isinstance(student, sympy.Set) else student
            simplified_expected = (
                sympy.simplify(expected) if isinstance(expected, sympy.Set) else expected
            )
            if simplified == simplified_expected:
                return True
            difference_set = simplified.symmetric_difference(simplified_expected)
            return bool(sympy.simplify(difference_set).is_empty)
        return bool(sympy.simplify(student - expected) == 0)
    except Exception:
        return False


def _numeric_equal(student: sympy.Expr, expected: sympy.Expr) -> bool:
    return _close(complex(student), complex(expected))


def _close(left: complex, right: complex, tolerance: float = 1e-9) -> bool:
    scale = max(1.0, abs(left), abs(right))
    return abs(left - right) <= tolerance * scale


def _sampling_stage(student: sympy.Expr, expected: sympy.Expr) -> bool:
    if isinstance(student, sympy.Set) or isinstance(expected, sympy.Set):
        return False
    difference = sympy.sympify(student - expected)
    if difference == 0:
        return True
    symbols = sorted(
        set(_free_symbols(student)) | set(_free_symbols(expected)),
        key=lambda symbol: symbol.name,
    )
    if not symbols:
        return _numeric_equal(student, expected)
    checked = 0
    for point in _sample_points(symbols):
        left = _safe_eval(student, point)
        right = _safe_eval(expected, point)
        if left is None or right is None:
            continue
        checked += 1
        if not _close(left, right):
            return False
    return checked > 0


def _solveset_stage(
    student_text: str, expected_text: str, student: sympy.Expr, expected: sympy.Expr
) -> bool:
    if "=" not in student_text or "=" not in expected_text:
        return False
    try:
        variable = sympy.Symbol("x")
        if variable not in student.free_symbols or variable not in expected.free_symbols:
            return False
        left = sympy.solveset(sympy.Eq(student, 0), variable, sympy.S.Reals)
        right = sympy.solveset(sympy.Eq(expected, 0), variable, sympy.S.Reals)
        if left is sympy.S.EmptySet or right is sympy.S.EmptySet:
            return False
        return bool(left == right)
    except Exception:
        return False


def equivalent(student_text: str, expected_text: str) -> ChainResult:
    try:
        student = parse_math(student_text)
        expected = parse_math(expected_text)
    except Exception as error:
        return ChainResult(False, "parse", f"cannot parse input ({type(error).__name__})")
    if _symbolic_stage(student, expected):
        return ChainResult(True, "simplify", "symbolically identical")
    if _sampling_stage(student, expected):
        return ChainResult(True, "sampling", "equal at sampled points")
    if _solveset_stage(student_text, expected_text, student, expected):
        return ChainResult(True, "solveset", "same solution set")
    return ChainResult(False, "none", "no stage proved equivalence")


def expressions_equivalent(student_text: str, expected_text: str) -> bool:
    return equivalent(student_text, expected_text).equivalent
