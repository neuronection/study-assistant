from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import sympy

from ...core.vocab import SolveIntent
from ...math.equivalence import equivalent
from .parse import Classified


@dataclass(frozen=True)
class Variant:
    index: int
    prompt: str
    kind: str
    answer_display: str
    answer_check: str


def _latex(expr: Any) -> str:
    return str(sympy.latex(expr))


def _equivalent(a: sympy.Expr, b: sympy.Expr) -> bool:
    try:
        return bool(sympy.simplify(a - b) == 0)
    except Exception:
        return False


def _solve_variants(parsed: Classified, seed: int) -> list[Variant]:
    variable = parsed.variable
    expression = parsed.expression
    assert variable is not None
    try:
        roots = sympy.solve(expression, variable)
        leading = sympy.Poly(expression, variable).LC()
    except Exception:
        return []
    if not isinstance(roots, (list, tuple)) or not roots:
        return []
    roots = [sympy.sympify(root) for root in roots]
    variants: list[Variant] = []
    for offset in range(1, 4):
        shift = sympy.Integer(offset + 1)
        shifted = [root + shift for root in roots]
        new_expression = sympy.expand(
            sympy.sympify(leading) * sympy.prod([variable - root for root in shifted])
        )
        if _equivalent(new_expression, expression):
            continue
        display = ", ".join(f"{variable} = {_latex(root)}" for root in shifted)
        check = ", ".join(_latex(root) for root in shifted)
        variants.append(
            Variant(
                index=len(variants),
                prompt=f"Solve: ${_latex(new_expression)} = 0$",
                kind="equation",
                answer_display=display,
                answer_check=check,
            )
        )
    return variants


def _rewrite_variant(
    parsed: Classified,
    operation: Callable[[Any], Any],
    label: str,
    factor: int,
    *,
    answer_suffix: str = "",
) -> Variant | None:
    expression = parsed.expression
    new_expression = sympy.expand(sympy.sympify(factor) * expression)
    if _equivalent(new_expression, expression):
        return None
    try:
        answer = sympy.sympify(operation(new_expression))
    except Exception:
        return None
    if answer.has(sympy.Integral, sympy.Derivative):
        return None
    return Variant(
        index=0,
        prompt=f"{label}: ${_latex(new_expression)}$",
        kind="expression",
        answer_display=f"{_latex(answer)}{answer_suffix}",
        answer_check=_latex(answer),
    )


def build_variants(parsed: Classified, seed: int = 0) -> list[Variant]:
    if parsed.expression is None or parsed.variable is None:
        return []
    if parsed.intent is SolveIntent.SOLVE:
        return _solve_variants(parsed, seed)
    if parsed.intent is SolveIntent.SIMPLIFY:
        operation: Callable[[Any], Any] = sympy.simplify
        label = "Simplify"
    elif parsed.intent is SolveIntent.EXPAND:
        operation = sympy.expand
        label = "Expand"
    elif parsed.intent is SolveIntent.FACTOR:
        operation = sympy.factor
        label = "Factor"
    elif parsed.intent is SolveIntent.DIFFERENTIATE:

        def operation(value: Any) -> Any:
            return sympy.diff(value, parsed.variable)

        label = "Differentiate"
    elif parsed.intent is SolveIntent.INTEGRATE:

        def operation(value: Any) -> Any:
            return sympy.integrate(value, parsed.variable)

        label = "Integrate"
    else:
        return []
    variants: list[Variant] = []
    for factor in (2, 3, 5):
        variant = _rewrite_variant(parsed, operation, label, factor)
        if variant is None:
            continue
        variants.append(
            Variant(
                index=len(variants),
                prompt=variant.prompt,
                kind=variant.kind,
                answer_display=variant.answer_display,
                answer_check=variant.answer_check,
            )
        )
    return variants


def check_variant(expected: str, response: str) -> bool:
    cleaned = response.strip()
    if not cleaned:
        return False
    if "=" in cleaned:
        pieces = [piece.strip() for piece in cleaned.split(",") if piece.strip()]
        cleaned = ", ".join(piece.rsplit("=", 1)[-1].strip() for piece in pieces)
    try:
        return equivalent(cleaned, expected).equivalent
    except Exception:
        return False
