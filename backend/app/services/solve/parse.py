import re
from dataclasses import dataclass

import sympy

from ...core.vocab import SolveIntent
from ...math.equivalence import parse_math

_COMMAND_RE = re.compile(
    r"^(solve|simplify|expand|factor|differentiate|derive|integrate|evaluate|limit|graph)"
    r"\b\s*[:\-]?\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)

_INTEGRAL_RE = re.compile(r"\\int(?:_\{?[^{}]*\}?\^\{?[^{}]*\}?)?")
_DX_RE = re.compile(r"\\?,?\s*d\s*x\b|\\,\s*dx\b")


@dataclass(frozen=True)
class Classified:
    raw: str
    normalized: str
    intent: SolveIntent
    expression: sympy.Expr
    variable: sympy.Symbol | None
    equation: bool
    message: str | None = None


def _strip_integral(text: str) -> str:
    return _DX_RE.sub("", _INTEGRAL_RE.sub("", text)).strip()


def _normalize_latex(text: str) -> str:
    cleaned = text.strip().strip("$").strip()
    cleaned = cleaned.replace(r"\displaystyle", " ")
    cleaned = cleaned.replace(r"\left", "").replace(r"\right", "")
    cleaned = cleaned.replace(r"\cdot", r" \cdot ")
    cleaned = re.sub(
        r"\\(sin|cos|tan|cot|sec|csc|sinh|cosh|tanh|log|ln|exp|sqrt)\b",
        lambda match: f" {match.group(1)} ",
        cleaned,
    )
    cleaned = re.sub(r"\\[,;!:]", " ", cleaned)
    return " ".join(cleaned.split())


def _intent_from_command(command: str | None, body: str) -> SolveIntent | None:
    if command is None:
        return None
    lowered = command.lower()
    if lowered == "derive":
        lowered = "differentiate"
    try:
        return SolveIntent(lowered)
    except ValueError:
        return SolveIntent.UNSUPPORTED


def classify(raw: str) -> Classified:
    text = _normalize_latex(raw)
    if not text:
        return Classified(
            raw=raw,
            normalized=text,
            intent=SolveIntent.UNSUPPORTED,
            expression=sympy.Integer(0),
            variable=None,
            equation=False,
            message="Type or paste a problem first.",
        )
    command = None
    body = text
    match = _COMMAND_RE.match(text)
    if match:
        command = match.group(1)
        body = match.group(2).strip()
    if "\\int" in body:
        intent = SolveIntent.INTEGRATE
        if "\\int_" in body or "\\int^" in body:
            return Classified(
                raw=raw,
                normalized=body,
                intent=SolveIntent.INTEGRATE,
                expression=sympy.Integer(0),
                variable=None,
                equation=False,
                message=(
                    "Definite integrals are not verified yet. Use an indefinite "
                    "integral such as integrate x*cos(x)."
                ),
            )
        body = _strip_integral(body)
    elif command is not None:
        intent = _intent_from_command(command, body) or SolveIntent.UNSUPPORTED
    elif "=" in body:
        intent = SolveIntent.SOLVE
    else:
        intent = SolveIntent.SIMPLIFY

    if intent in (SolveIntent.LIMIT, SolveIntent.GRAPH):
        return Classified(
            raw=raw,
            normalized=body,
            intent=intent,
            expression=sympy.Integer(0),
            variable=None,
            equation=False,
            message=(
                "The Problem Desk does not verify limits or graphs yet. "
                "Try solve, simplify, expand, factor, differentiate, integrate or evaluate."
            ),
        )
    if not body:
        return Classified(
            raw=raw,
            normalized=body,
            intent=SolveIntent.UNSUPPORTED,
            expression=sympy.Integer(0),
            variable=None,
            equation=False,
            message="The problem is empty after the command.",
        )
    try:
        expression = parse_math(body)
    except Exception as error:
        return Classified(
            raw=raw,
            normalized=body,
            intent=SolveIntent.UNSUPPORTED,
            expression=sympy.Integer(0),
            variable=None,
            equation=False,
            message=f"I could not parse that input ({type(error).__name__}).",
        )

    symbols = sorted(expression.free_symbols, key=lambda symbol: symbol.name)
    variable = symbols[0] if len(symbols) == 1 else None
    if len(symbols) > 1:
        return Classified(
            raw=raw,
            normalized=body,
            intent=SolveIntent.UNSUPPORTED,
            expression=expression,
            variable=None,
            equation="=" in body,
            message="This first pass handles one variable at a time.",
        )
    if intent is SolveIntent.SIMPLIFY and variable is None:
        intent = SolveIntent.EVALUATE
    needs_variable = intent in (
        SolveIntent.SOLVE,
        SolveIntent.DIFFERENTIATE,
        SolveIntent.INTEGRATE,
    )
    if needs_variable and variable is None:
        return Classified(
            raw=raw,
            normalized=body,
            intent=SolveIntent.UNSUPPORTED,
            expression=expression,
            variable=None,
            equation="=" in body,
            message="That operation needs one variable, for example x.",
        )
    return Classified(
        raw=raw,
        normalized=body,
        intent=intent,
        expression=expression,
        variable=variable,
        equation="=" in body,
    )
