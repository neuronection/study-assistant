import json
import math
import re
from typing import Any

import sympy

_ALLOWED_NAMES: dict[str, Any] = {
    name: getattr(math, name)
    for name in (
        "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sinh", "cosh",
        "tanh", "exp", "log", "log10", "log2", "sqrt", "pow", "floor", "ceil",
        "fabs", "factorial", "gcd", "degrees", "radians", "pi", "e", "tau",
    )
}

_ALLOWED_RE = re.compile(r"^[0-9a-zA-Z_+\-*/%^().,\s]+$")

MAX_EXPR_LEN = 200


def calculate(expression: str) -> str:
    expression = expression.strip()
    if not expression or len(expression) > MAX_EXPR_LEN or not _ALLOWED_RE.match(expression):
        return "error: invalid expression"
    if re.search(r"__[a-z]+__", expression):
        return "error: invalid expression"
    try:
        value = eval(
            expression.replace("^", "**"), {"__builtins__": {}}, _ALLOWED_NAMES
        )
    except Exception as error:
        return f"error: {type(error).__name__}"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "error: non-finite result"
    if isinstance(value, int):
        return str(value)
    return f"{value:.12g}"


SYMPY_ACTIONS = ("solve", "simplify", "diff", "integrate", "expand", "factor", "limit")

PLOT_POINTS = 201
PLOT_X_MIN = -10.0
PLOT_X_MAX = 10.0
PLOT_Y_CAP = 1e6


def plot_function(expression: str) -> str:
    expression = expression.strip()
    if not expression or len(expression) > MAX_EXPR_LEN:
        return "error: invalid expression"
    try:
        symbol = sympy.Symbol("x")
        parsed = sympy.sympify(expression, locals={"x": symbol})
        function = sympy.lambdify(symbol, parsed, "math")
    except Exception:
        return "error: cannot parse expression"
    step = (PLOT_X_MAX - PLOT_X_MIN) / (PLOT_POINTS - 1)
    xs = [round(PLOT_X_MIN + step * index, 3) for index in range(PLOT_POINTS)]
    ys: list[float | None] = []
    for value in xs:
        try:
            result = float(function(value))
        except Exception:
            ys.append(None)
            continue
        if math.isnan(result) or math.isinf(result) or abs(result) > PLOT_Y_CAP:
            ys.append(None)
        else:
            ys.append(round(result, 6))
    return json.dumps(
        {"data": [{"type": "scatter", "mode": "lines", "x": xs, "y": ys}]},
        ensure_ascii=False,
    )


def native_tool_schemas(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    for tool in catalog:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for argument in tool.get("arguments", []):
            name = argument["name"]
            properties[name] = {
                "type": argument.get("type", "string"),
                "description": argument.get("description", ""),
            }
            if argument.get("required"):
                required.append(name)
        parameters: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            parameters["required"] = required
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": parameters,
                },
            }
        )
    return schemas


def build_tool_doc(catalog: list[dict[str, Any]]) -> str:
    sections = [
        "Use these tools when they help. Emit EXACTLY one tool line, nothing else:"
    ]
    for tool in catalog:
        args = " ".join(f"<{argument['name']}>" for argument in tool["arguments"])
        body = f"{tool['name']} {args}".strip()
        lines = [body, f"  {tool['description'].splitlines()[0]}"]
        if tool.get("example"):
            lines.append(f"  Example: {tool['example']}")
        for argument in tool["arguments"]:
            if argument.get("description"):
                lines.append(f"    {argument['name']}: {argument['description']}")
        sections.append("\n".join(lines))
    sections.append("If no tool is needed, answer normally without any tool line.")
    return "\n\n".join(sections)


def run_sympy(action: str, expression: str) -> str:
    expression = expression.strip()
    if "=" in expression and action == "solve":
        left, _, right = expression.partition("=")
        expression = f"({left}) - ({right})"
    try:
        parsed = sympy.sympify(
            expression,
            locals={"x": sympy.Symbol("x"), "t": sympy.Symbol("t"), "n": sympy.Symbol("n")},
            evaluate=True,
        )
    except Exception as error:
        return f"error: cannot parse expression ({type(error).__name__})"
    try:
        if action == "solve":
            result = sympy.solve(parsed, sympy.Symbol("x"))
        elif action == "simplify":
            result = sympy.simplify(parsed)
        elif action == "diff":
            result = sympy.diff(parsed, sympy.Symbol("x"))
        elif action == "integrate":
            result = sympy.integrate(parsed, sympy.Symbol("x"))
        elif action == "expand":
            result = sympy.expand(parsed)
        elif action == "factor":
            result = sympy.factor(parsed)
        elif action == "limit":
            result = sympy.limit(parsed, sympy.Symbol("x"), 0)
        else:
            return f"error: unknown action '{action}'"
    except Exception as error:
        return f"error: {type(error).__name__}"
    return str(sympy.sstr(result))[:2000]


RESOURCE_TOOL_KEYWORDS = (
    "COURSES",
    "NODE_OVERVIEW",
    "NODE_QUIZZES",
    "NODE_EXERCISES",
    "NODE_NOTES",
)

TOOL_LINE_RE = re.compile(
    r"^[ \t]*(CALC|SYMPY|READ|STATE|PLOT|"
    + "|".join(RESOURCE_TOOL_KEYWORDS)
    + r")(?:[ \t]+(.+))?[ \t]*$",
    re.MULTILINE,
)


def run_tool_line(kind: str, argument: str) -> str:
    if kind == "CALC":
        return calculate(argument)
    if kind == "SYMPY":
        parts = argument.strip().split(None, 1)
        if len(parts) != 2 or parts[0] not in SYMPY_ACTIONS:
            return "error: expected 'SYMPY <action> <expression>'"
        return run_sympy(parts[0], parts[1])
    if kind == "PLOT":
        return plot_function(argument)
    return "error: unknown tool"


def extract_tool_calls(text: str) -> list[tuple[str, str]]:
    return [
        (match.group(1), (match.group(2) or "").strip())
        for match in TOOL_LINE_RE.finditer(text)
    ]


def strip_tool_lines(text: str) -> str:
    return TOOL_LINE_RE.sub("", text).strip()


CHAT_TOOL_CATALOG: list[dict[str, Any]] = [
    {
        "name": "CALC",
        "description": "Numeric evaluation of an arithmetic expression "
        "(trig, log, powers, constants).",
        "example": "CALC sin(pi/6)",
        "arguments": [
            {
                "name": "expression",
                "type": "string",
                "required": True,
                "description": "Arithmetic expression; ^ means power; "
                "math constants like pi and e available",
            }
        ],
        "response": "The evaluated number, or an error line "
        "(invalid expression, non-finite result).",
        "scope": "Chat answers — runs sandboxed (math allowlist, no builtins) "
        "when the tutor verifies nontrivial math.",
    },
    {
        "name": "SYMPY",
        "description": "Exact symbolic computation via SymPy: solve, simplify, "
        "diff, integrate, expand, factor or limit an expression.",
        "example": "SYMPY diff x**2*sin(x)",
        "arguments": [
            {
                "name": "action",
                "type": "string",
                "required": True,
                "description": f"One of: {', '.join(SYMPY_ACTIONS)}",
            },
            {
                "name": "expression",
                "type": "string",
                "required": True,
                "description": "SymPy-parseable expression in x (t, n also "
                "declared); solve accepts expr=0 or a bare expr for roots",
            },
        ],
        "response": "The exact symbolic result (string), or an error line "
        "(parse failure, unknown action).",
        "scope": "Chat answers — deterministic verification; results are fed "
        "back to the model and stripped from the stored answer.",
    },
    {
        "name": "READ",
        "description": "Fetch the full content of an item from the reference "
        "manifest by its handle. Use it before answering when the excerpt you "
        "have is not enough.",
        "example": "READ M12",
        "arguments": [
            {
                "name": "handle",
                "type": "string",
                "required": True,
                "description": "A handle listed in the conversation's "
                "referenceable-items manifest, e.g. M12 or N3",
            }
        ],
        "response": "The item's content (char-budgeted), or an error line "
        "(unknown handle, not offered in this conversation, budget spent).",
        "scope": "Chat answers — deterministic fetch from your own course "
        "items; content goes to the model only and is never stored in the "
        "answer. Up to 3 READs per turn.",
    },
    {
        "name": "STATE",
        "description": "Read the current value of an interactive widget the tutor "
        "showed earlier in this conversation (a checklist, slider, choice, "
        "numberline, etc.) by its widget id.",
        "example": "STATE w1",
        "arguments": [
            {
                "name": "widget_id",
                "type": "string",
                "required": True,
                "description": "The id of a widget previously emitted in this "
                "conversation (e.g. w1).",
            }
        ],
        "response": "The widget's state as JSON, or an error line (unknown widget "
        "id, no state recorded yet, budget spent).",
        "scope": "Chat answers — deterministic read of widget state; results go to "
        "the model only and are never stored in the answer.",
    },
    {
        "name": "PLOT",
        "description": "Plot a function of x and get chart data; wrap the returned "
        "JSON in a ```chart fence in your answer so the student sees the graph.",
        "example": "PLOT sin(x)/x",
        "arguments": [
            {
                "name": "expression",
                "type": "string",
                "required": True,
                "description": "A SymPy-parseable expression in x to plot over "
                "[-10, 10], e.g. sin(x)/x or x**2*sin(x)",
            }
        ],
        "response": "A compact JSON chart spec (plotly scatter, sampled deterministically) "
        "to render in a ```chart fence, or an error line.",
        "scope": "Chat answers — deterministic SymPy sampling; the model includes the "
        "returned JSON verbatim in a ```chart fence.",
    },
]

CHAT_TOOL_DOC = build_tool_doc(CHAT_TOOL_CATALOG)
