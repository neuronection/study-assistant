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


_JSON_SCHEMA_TYPES = frozenset(
    {"string", "number", "integer", "boolean", "array", "object"}
)


def native_tool_schemas(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    for tool in catalog:
        if tool.get("kind") == "capability":
            continue
        properties: dict[str, Any] = {}
        required: list[str] = []
        for argument in tool.get("arguments", []):
            name = argument["name"]
            json_type = argument.get("type", "string")
            if json_type not in _JSON_SCHEMA_TYPES:
                # human-readable labels like "array of strings" are invalid
                # JSON Schema types and make providers reject the request
                json_type = "string"
            property_schema: dict[str, Any] = {
                "type": json_type,
                "description": argument.get("description", ""),
            }
            if json_type == "array":
                items = argument.get("items")
                property_schema["items"] = (
                    items if isinstance(items, dict) else {"type": "string"}
                )
            properties[name] = property_schema
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
        if tool.get("kind") == "capability":
            continue
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
    "NODE_MATERIALS",
    "NODE_QUIZZES",
    "NODE_EXERCISES",
    "NODE_NOTES",
    "NODE_CONCEPTS",
    "NODE_FLASHCARDS",
    "MISTAKES",
    "PLAN",
    "DUE",
)

TOOL_LINE_RE = re.compile(
    r"^[ \t]*(CALC|SYMPY|READ|STATE|PLOT|SEARCH|FETCH|FIND|DISCOVER|"
    + "|".join(RESOURCE_TOOL_KEYWORDS)
    + r")(?:[ \t]+(.+))?[ \t]*$",
    re.MULTILINE,
)


def run_tool_line(kind: str, argument: str) -> str:
    if kind in CAPABILITY_TOOL_NAMES:
        return (
            "error: HITL capability — propose it in your answer instead; "
            "the student approves the card"
        )
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
    {
        "name": "FIND",
        "description": "Search the student's own library in this course "
        "(materials and notes) by keyword and get titled handles you can READ. "
        "Use it when the student refers to 'my notes on …' or a document that "
        "was not offered in the manifest.",
        "example": "FIND integration by parts",
        "arguments": [
            {
                "name": "query",
                "type": "string",
                "required": True,
                "description": "Keywords to look for in material and note "
                "titles and content",
            }
        ],
        "response": "Up to 10 lines of '<handle> — <title> (kind)' that become "
        "READ-able, or a 'no matches' line.",
        "scope": "Chat answers — course-scoped local search over the student's "
        "own library; results become readable handles; up to 2 FINDs per turn.",
    },
    {
        "name": "SEARCH",
        "description": "Search the web via the configured search provider and get "
        "titled source excerpts with URLs. Use it for current or contested topics; "
        "cite the URLs you actually used in the answer.",
        "example": "SEARCH P vs NP undergraduate curriculum",
        "arguments": [
            {
                "name": "query",
                "type": "string",
                "required": True,
                "description": "A focused web search query",
            }
        ],
        "response": "Up to 5 numbered results (title, URL, excerpt) or an error line "
        "(no search provider configured, provider unreachable, budget spent).",
        "scope": "Chat answers — external research; excerpts go to the model only "
        "and are never stored in the answer; up to 2 SEARCHes per turn.",
    },
    {
        "name": "DISCOVER",
        "description": "Find study material on the open web (web search, "
        "YouTube, site presets like Khan Academy) and get titled source "
        "links with providers. Use it when the student asks to find videos, "
        "courses, exercises or reading on a topic. Pass the literal word "
        "`here` to search for material about the current topic/chapter.",
        "example": "DISCOVER integration by parts video",
        "arguments": [
            {
                "name": "query",
                "type": "string",
                "required": True,
                "description": "A focused discovery query, or `here` to "
                "build one from the current study context",
            }
        ],
        "response": "Up to 5 numbered results (title, provider, URL) or an "
        "error line (no providers configured, providers unreachable, no "
        "course context for `here`, budget spent).",
        "scope": "Chat answers — external material discovery; results go to "
        "the model only and are never stored or auto-imported; the student "
        "can save results in the Discover dialog; up to 2 DISCOVERs per turn.",
    },
    {
        "name": "FETCH",
        "description": "Fetch a web page and get its readable text as markdown "
        "(max 4000 chars). Use it on a specific URL you already have (e.g. from "
        "SEARCH). This is a direct fetch, not a crawler.",
        "example": "FETCH https://example.com/notes",
        "arguments": [
            {
                "name": "url",
                "type": "string",
                "required": True,
                "description": "An http(s) URL to fetch",
            }
        ],
        "response": "The page's readable markdown (char-budgeted), or an error line "
        "(non-URL argument, unreachable page, budget spent).",
        "scope": "Chat answers — external research; page content goes to the model "
        "only and is never stored in the answer; up to 1 FETCH per turn.",
    },
]

CHAT_TOOL_DOC = build_tool_doc(CHAT_TOOL_CATALOG)

CHAT_CAPABILITY_CATALOG: list[dict[str, Any]] = [
    {
        "name": "PROPOSE_EDITS",
        "kind": "capability",
        "hitl": True,
        "description": "Propose study edits as approval cards: create or edit "
        "notes and materials, place or move them on the course tree, cover "
        "concepts, tag notes, set the exam date, add plan items or attach a "
        "web link.",
        "arguments": [],
        "response": "Nothing executes by itself — each proposal becomes a card "
        "in the answer; the student approves or dismisses it and only approval "
        "writes anything.",
        "scope": "Chat answers — human-in-the-loop only (ADR-0015 Class B): "
        "drafted inside ```proposal blocks, validated server-side, applied "
        "through the same endpoints the forms use.",
    },
    {
        "name": "PROPOSE_GENERATIONS",
        "kind": "capability",
        "hitl": True,
        "description": "Propose AI generations as approval cards: a quiz, an "
        "exercise or flashcards from the current material or note, or a "
        "composed material (summary, formula sheet, practice set).",
        "arguments": [],
        "response": "Nothing executes by itself — approval opens the "
        "generation dialog prefilled (or starts the compose job); the "
        "student confirms every run.",
        "scope": "Chat answers — human-in-the-loop only (ADR-0015 Class B): "
        "the model proposes, the dialog's progress and cancel stay with the "
        "student.",
    },
]

CAPABILITY_TOOL_NAMES = frozenset(
    str(entry["name"]) for entry in CHAT_CAPABILITY_CATALOG
)

QUIZ_TOOL: dict[str, Any] = {
    "name": "QUIZ",
    "description": "Quiz-me mode only: ask the student exactly one question. "
    "The server grades the student's answer deterministically (choice match, "
    "math equivalence chain, or accepted text variants) and shows the verdict — "
    "the expected answer is never revealed to you, so never guess or invent it.",
    "example": "QUIZ",
    "arguments": [
        {
            "name": "question",
            "type": "string",
            "required": True,
            "description": "The question text to show the student",
        },
        {
            "name": "choices",
            "type": "array",
            "items": {"type": "string"},
            "required": False,
            "description": "2-6 answer options for a multiple-choice question",
        },
        {
            "name": "expected_index",
            "type": "integer",
            "required": False,
            "description": "With choices: the 0-based index of the correct option "
            "(server-held, never shown to you)",
        },
        {
            "name": "expected_latex",
            "type": "string",
            "required": False,
            "description": "For free-form math answers: the expected expression "
            "in LaTeX (server-held, never shown to you)",
        },
        {
            "name": "expected_text",
            "type": "string",
            "required": False,
            "description": "For free-form short answers: the expected text "
            "(server-held, never shown to you)",
        },
        {
            "name": "accept",
            "type": "array",
            "items": {"type": "string"},
            "required": False,
            "description": "Additional exact text variants to accept as correct "
            "(synonyms only; fixed at question time)",
        },
    ],
    "response": "Confirmation that the question card was presented; the student's "
    "graded answer arrives with their next message.",
    "scope": "Quiz-me sessions only (server-graded; the model never grades and "
    "never sees the expected answer — ADR-121).",
}

QUIZ_NATIVE_SCHEMA = native_tool_schemas([QUIZ_TOOL])
QUIZ_TOOL_DOC = build_tool_doc([QUIZ_TOOL])
