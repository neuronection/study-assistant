from dataclasses import dataclass
from typing import Any

import sympy

from ...core.vocab import SolveIntent
from ...domain.payloads import SolveResult, SolveStep
from ...math.equivalence import equivalent
from .parse import Classified


@dataclass
class Outcome:
    result: SolveResult
    expression: sympy.Expr | None = None
    answer_check: str | None = None


def _latex(expr: Any) -> str:
    return str(sympy.latex(expr))


def _step(
    op: str,
    title: str,
    before: str,
    after: str,
    check: str,
    verified: bool,
    detail: str = "",
) -> SolveStep:
    return SolveStep(
        op=op,
        title=title,
        before=before,
        after=after,
        check=check,
        verified=verified,
        detail=detail,
    )


def _equivalent(a: sympy.Expr, b: sympy.Expr) -> bool:
    try:
        return bool(sympy.simplify(a - b) == 0)
    except Exception:
        return False


def _roots(expr: sympy.Expr, variable: sympy.Symbol) -> list[sympy.Expr]:
    values = sympy.solve(expr, variable)
    if isinstance(values, dict):
        return [values.get(variable, sympy.nan)]
    if not isinstance(values, (list, tuple, set)):
        return []
    return [sympy.sympify(value) for value in values]


def _root_checks(expr: sympy.Expr, variable: sympy.Symbol, roots: list[sympy.Expr]) -> bool:
    if not roots:
        return False
    for root in roots:
        try:
            value = sympy.simplify(expr.subs(variable, root))
        except Exception:
            return False
        if value != 0:
            return False
    return True


def _solution_latex(variable: sympy.Symbol, roots: list[sympy.Expr]) -> tuple[str, str]:
    display = ", ".join(f"{variable} = {_latex(root)}" for root in roots)
    check = ", ".join(_latex(root) for root in roots)
    return display, check


def _solve(parsed: Classified) -> Outcome:
    expression = parsed.expression
    variable = parsed.variable
    assert variable is not None
    try:
        degree = sympy.Poly(expression, variable).degree()
    except Exception:
        return _unsupported("The solver could not recognise this as a polynomial equation.")
    if not isinstance(degree, int) or degree < 1 or degree > 2:
        return _unsupported(
            "This first pass solves linear and quadratic equations with one variable."
        )
    roots = _roots(expression, variable)
    verified = _root_checks(expression, variable, roots)
    steps: list[SolveStep] = []
    standard = f"{_latex(expression)} = 0"
    if parsed.equation and parsed.normalized.strip() and parsed.normalized.strip() != standard:
        check = equivalent(parsed.normalized, standard)
        steps.append(
            _step(
                "normalize",
                "Write in standard form",
                parsed.normalized,
                standard,
                "equivalence",
                check.equivalent,
                check.detail,
            )
        )
    if degree == 2:
        factored = sympy.factor(expression)
        if _equivalent(factored, expression) and factored != expression:
            steps.append(
                _step(
                    "factor",
                    "Factor the quadratic",
                    standard,
                    f"{_latex(factored)} = 0",
                    "equivalence",
                    True,
                    "the factored form is equivalent to the standard form",
                )
            )
    if not roots:
        result = SolveResult(
            input=parsed.raw,
            normalized=parsed.normalized,
            intent=SolveIntent.SOLVE.value,
            title="Solve equation",
            answer_latex="No solution",
            answer_text="No solution",
            steps=steps,
            assumptions=[],
            verified=True,
            message=None,
        )
        return Outcome(result=result, expression=expression)
    display, check_value = _solution_latex(variable, roots)
    steps.append(
        _step(
            "solve",
            "Apply the zero-product rule" if degree == 2 else "Isolate the variable",
            f"{_latex(sympy.factor(expression))} = 0" if degree == 2 else standard,
            display,
            "substitution",
            verified,
            "every root satisfies the original equation"
            if verified
            else "not every computed root satisfies the original equation",
        )
    )
    if not verified:
        return _unverified(
            parsed,
            "The computed roots did not pass substitution checks, so no answer is shown.",
        )
    return Outcome(
        result=SolveResult(
            input=parsed.raw,
            normalized=parsed.normalized,
            intent=SolveIntent.SOLVE.value,
            title="Solve equation",
            answer_latex=display,
            answer_text=display.replace("$", ""),
            steps=[step for step in steps if step["verified"]],
            assumptions=[],
            verified=True,
            message=None,
        ),
        expression=expression,
        answer_check=check_value,
    )


def _rewrite(parsed: Classified, intent: SolveIntent, operation: Any) -> Outcome:
    expression = parsed.expression
    try:
        rewritten = sympy.sympify(operation(expression))
    except Exception:
        return _unsupported("SymPy could not complete this rewrite.")
    if rewritten.has(sympy.Integral, sympy.Derivative):
        return _unsupported("This expression stays unevaluated; refusing to show a partial result.")
    verified = _equivalent(expression, rewritten)
    steps = []
    if verified and rewritten != expression:
        steps.append(
            _step(
                intent.value,
                {
                    SolveIntent.SIMPLIFY: "Simplify",
                    SolveIntent.EXPAND: "Expand",
                    SolveIntent.FACTOR: "Factor",
                }.get(intent, "Rewrite"),
                _latex(expression),
                _latex(rewritten),
                "equivalence",
                True,
                "the rewritten expression is equivalent",
            )
        )
    if not verified:
        return _unverified(parsed, "The rewrite did not pass the equivalence check.")
    return Outcome(
        result=SolveResult(
            input=parsed.raw,
            normalized=parsed.normalized,
            intent=intent.value,
            title={
                SolveIntent.SIMPLIFY: "Simplify expression",
                SolveIntent.EXPAND: "Expand expression",
                SolveIntent.FACTOR: "Factor expression",
            }.get(intent, "Rewrite expression"),
            answer_latex=_latex(rewritten),
            answer_text=str(rewritten),
            steps=steps,
            assumptions=[],
            verified=True,
            message=None,
        ),
        expression=expression,
        answer_check=_latex(rewritten),
    )


def _differentiate(parsed: Classified) -> Outcome:
    expression = parsed.expression
    variable = parsed.variable
    assert variable is not None
    try:
        derivative = sympy.sympify(sympy.diff(expression, variable))
    except Exception:
        return _unsupported("SymPy could not differentiate this expression.")
    if derivative.has(sympy.Derivative):
        return _unsupported("The derivative stays unevaluated.")
    verified = _equivalent(derivative, sympy.diff(expression, variable))
    if not verified:
        return _unverified(parsed, "The derivative did not pass its reverse check.")
    before = _latex(expression)
    after = _latex(derivative)
    return Outcome(
        result=SolveResult(
            input=parsed.raw,
            normalized=parsed.normalized,
            intent=SolveIntent.DIFFERENTIATE.value,
            title=f"Differentiate with respect to {variable}",
            answer_latex=after,
            answer_text=str(derivative),
            steps=[
                _step(
                    "differentiate",
                    f"Differentiate with respect to {variable}",
                    before,
                    after,
                    "derivative",
                    True,
                    f"d/d{variable}({after}) = {before}",
                )
            ],
            assumptions=[],
            verified=True,
            message=None,
        ),
        expression=expression,
        answer_check=after,
    )


def _integrate(parsed: Classified) -> Outcome:
    expression = parsed.expression
    variable = parsed.variable
    assert variable is not None
    try:
        antiderivative = sympy.sympify(sympy.integrate(expression, variable))
    except Exception:
        return _unsupported("SymPy could not integrate this expression.")
    if antiderivative.has(sympy.Integral):
        return _unsupported("This integral is outside the curated pattern set for now.")
    verified = _equivalent(sympy.diff(antiderivative, variable), expression)
    if not verified:
        return _unverified(parsed, "The antiderivative did not pass its derivative check.")
    before = _latex(expression)
    after = _latex(antiderivative)
    return Outcome(
        result=SolveResult(
            input=parsed.raw,
            normalized=parsed.normalized,
            intent=SolveIntent.INTEGRATE.value,
            title=f"Integrate with respect to {variable}",
            answer_latex=f"{after} + C",
            answer_text=f"{antiderivative} + C",
            steps=[
                _step(
                    "integrate",
                    f"Find an antiderivative with respect to {variable}",
                    before,
                    after,
                    "antiderivative",
                    True,
                    f"d/d{variable}({after}) = {before}",
                )
            ],
            assumptions=["C is an arbitrary constant."],
            verified=True,
            message=None,
        ),
        expression=expression,
        answer_check=after,
    )


def _evaluate(parsed: Classified) -> Outcome:
    expression = parsed.expression
    if expression.free_symbols:
        return _unsupported("Evaluation needs an expression with no remaining variables.")
    try:
        value = sympy.N(expression, 12)
    except Exception:
        return _unsupported("SymPy could not evaluate this expression.")
    try:
        verified = abs(complex(value) - complex(expression)) <= 1e-9 * max(
            1.0, abs(complex(expression))
        )
    except Exception:
        verified = False
    if not verified:
        return _unverified(parsed, "The numeric evaluation did not pass its check.")
    return Outcome(
        result=SolveResult(
            input=parsed.raw,
            normalized=parsed.normalized,
            intent=SolveIntent.EVALUATE.value,
            title="Evaluate",
            answer_latex=_latex(value),
            answer_text=str(value),
            steps=[],
            assumptions=[],
            verified=True,
            message=None,
        ),
        expression=expression,
        answer_check=_latex(value),
    )


def _unsupported(message: str) -> Outcome:
    return Outcome(
        result=SolveResult(
            input="",
            normalized="",
            intent=SolveIntent.UNSUPPORTED.value,
            title="Unsupported problem",
            answer_latex=None,
            answer_text=None,
            steps=[],
            assumptions=[],
            verified=False,
            message=message,
        )
    )


def _unverified(parsed: Classified, message: str) -> Outcome:
    return Outcome(
        result=SolveResult(
            input=parsed.raw,
            normalized=parsed.normalized,
            intent=parsed.intent.value,
            title="Unverified result",
            answer_latex=None,
            answer_text=None,
            steps=[],
            assumptions=[],
            verified=False,
            message=message,
        )
    )


def solve(parsed: Classified) -> Outcome:
    if parsed.message is not None:
        result = _unsupported(parsed.message).result
        result["input"] = parsed.raw
        result["normalized"] = parsed.normalized
        result["intent"] = parsed.intent.value
        return Outcome(result=result)
    if parsed.intent is SolveIntent.SOLVE:
        return _solve(parsed)
    if parsed.intent is SolveIntent.SIMPLIFY:
        return _rewrite(parsed, SolveIntent.SIMPLIFY, sympy.simplify)
    if parsed.intent is SolveIntent.EXPAND:
        return _rewrite(parsed, SolveIntent.EXPAND, sympy.expand)
    if parsed.intent is SolveIntent.FACTOR:
        return _rewrite(parsed, SolveIntent.FACTOR, sympy.factor)
    if parsed.intent is SolveIntent.DIFFERENTIATE:
        return _differentiate(parsed)
    if parsed.intent is SolveIntent.INTEGRATE:
        return _integrate(parsed)
    if parsed.intent is SolveIntent.EVALUATE:
        return _evaluate(parsed)
    return _unsupported("This problem is outside the verified solver's first set.")
