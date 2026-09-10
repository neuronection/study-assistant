from typing import Any

WIDGET_SPECS: dict[str, dict[str, Any]] = {
    "chart": {
        "description": "an interactive Plotly chart",
        "props": {"plotly": "object {data, layout} (required)"},
    },
    "geo": {
        "description": "an interactive JSXGraph geometry construction (draggable)",
        "props": {"jsxgraph": "string, JessieCode construction (required)"},
    },
    "checklist": {
        "description": "a checklist the student ticks (multi- or single-select)",
        "props": {
            "prompt": "string (required)",
            "items": "list of strings (required, 1-20)",
            "multiple": "boolean (optional; false = single-select)",
        },
    },
    "choice": {
        "description": "a single-choice (radio) question",
        "props": {
            "prompt": "string (required)",
            "options": "list of strings (required, 2-20)",
        },
    },
    "slider": {
        "description": "a numeric range slider",
        "props": {
            "prompt": "string (required)",
            "min": "number (optional, default 0)",
            "max": "number (required)",
            "step": "number (optional)",
            "unit": "string (optional)",
        },
    },
    "equation_input": {
        "description": "a text/equation input field",
        "props": {
            "prompt": "string (required)",
            "placeholder": "string (optional)",
        },
    },
    "numberline": {
        "description": "a clickable number line to mark points",
        "props": {
            "min": "number (required)",
            "max": "number (required)",
            "label": "string (optional)",
        },
    },
}

WIDGET_NAMES: frozenset[str] = frozenset(WIDGET_SPECS)

MAX_PROMPT = 500
MAX_ITEMS = 20
MAX_ITEM = 200
MAX_JSXGRAPH = 20000


def build_widget_doc() -> str:
    lines: list[str] = []
    for name, spec in WIDGET_SPECS.items():
        props = ", ".join(f"{key}: {value}" for key, value in spec["props"].items())
        lines.append(f"- {name} — {spec['description']}. props: {props}.")
    return "\n".join(lines)


WIDGET_DOC: str = build_widget_doc()

CHAT_WIDGET_DOC: str = (
    "You may include interactive UI in your answer as fenced blocks the app renders: "
    "a ```chart fence holding a Plotly figure {\"data\": ..., \"layout\": ...}, or a "
    "```widget fence holding {\"widget\": <name>, \"id\": \"wN\", \"props\": {...}} "
    "(id unique per answer). Widget kinds:\n" + WIDGET_DOC
)

EXGEN_WIDGET_DOC: str = (
    "Any step may carry an optional \"widgets\" array of widget blocks "
    "[{\"type\": \"widget\", \"widget\": <name>, \"id\": \"wN\", \"props\": {...}}] "
    "(id unique within the exercise). Widget kinds:\n" + WIDGET_DOC
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_items(items: Any, min_items: int) -> list[str]:
    if not isinstance(items, list):
        return ["expected a list of items"]
    problems: list[str] = []
    if len(items) < min_items:
        problems.append(f"expected at least {min_items} item(s)")
    if len(items) > MAX_ITEMS:
        problems.append(f"expected at most {MAX_ITEMS} items")
    for item in items:
        if not isinstance(item, str) or not item.strip():
            problems.append("items must be non-empty strings")
            break
        if len(item) > MAX_ITEM:
            problems.append("an item exceeds the length limit")
    return problems


def _validate_prompt(name: str, props: dict[str, Any]) -> list[str]:
    prompt = props.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return [f"{name} requires a 'prompt' string"]
    if len(prompt) > MAX_PROMPT:
        return [f"{name} 'prompt' exceeds the length limit"]
    return []


def _validate_props(name: str, props: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if name in {"checklist", "choice", "slider", "equation_input"}:
        problems.extend(_validate_prompt(name, props))
    if name == "checklist":
        problems.extend(_validate_items(props.get("items"), min_items=1))
        multiple = props.get("multiple")
        if multiple is not None and not isinstance(multiple, bool):
            problems.append("checklist 'multiple' must be a boolean")
    elif name == "choice":
        problems.extend(_validate_items(props.get("options"), min_items=2))
    elif name == "slider":
        if not _is_number(props.get("max")):
            problems.append("slider requires a numeric 'max'")
        for key in ("min", "step"):
            if key in props and not _is_number(props[key]):
                problems.append(f"slider '{key}' must be numeric")
        if (
            _is_number(props.get("min"))
            and _is_number(props.get("max"))
            and float(props["min"]) >= float(props["max"])
        ):
            problems.append("slider 'min' must be less than 'max'")
    elif name == "equation_input":
        placeholder = props.get("placeholder")
        if placeholder is not None and (
            not isinstance(placeholder, str) or len(placeholder) > MAX_ITEM
        ):
            problems.append("equation_input 'placeholder' must be a short string")
    elif name == "numberline":
        for key in ("min", "max"):
            if not _is_number(props.get(key)):
                problems.append(f"numberline requires a numeric '{key}'")
        if (
            _is_number(props.get("min"))
            and _is_number(props.get("max"))
            and float(props["min"]) >= float(props["max"])
        ):
            problems.append("numberline 'min' must be less than 'max'")
    elif name == "chart":
        if not isinstance(props.get("plotly"), dict):
            problems.append("chart requires a 'plotly' object")
    elif name == "geo":
        source = props.get("jsxgraph")
        if not isinstance(source, str) or not source.strip():
            problems.append("geo requires a 'jsxgraph' string")
        elif len(source) > MAX_JSXGRAPH:
            problems.append("geo 'jsxgraph' exceeds the length limit")
    return problems


def validate_widget_block(block: Any) -> list[str]:
    if not isinstance(block, dict):
        return ["widget block must be an object"]
    problems: list[str] = []
    if block.get("type") != "widget":
        problems.append("block is not a widget")
    name = block.get("widget")
    if name not in WIDGET_NAMES:
        problems.append(f"unknown widget {name!r}")
        return problems
    widget_id = block.get("id")
    if not isinstance(widget_id, str) or not widget_id.strip():
        problems.append("widget 'id' must be a non-empty string")
    props = block.get("props")
    if not isinstance(props, dict):
        problems.append("widget 'props' must be an object")
    else:
        problems.extend(_validate_props(name, props))
    state = block.get("state")
    if state is not None and not isinstance(state, dict):
        problems.append("widget 'state' must be an object")
    return problems


def validate_widget_blocks(blocks: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(blocks, list):
        return problems
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "widget":
            problems.extend(validate_widget_block(block))
    return problems


def read_widget_state(state_document: Any, widget_id: str) -> Any:
    if not isinstance(state_document, dict):
        return None
    return state_document.get(widget_id)
