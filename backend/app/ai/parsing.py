import json
import re
from typing import Any

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?|```\s*$", re.DOTALL)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def strip_code_fence(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


def extract_json_object(text: str, error: type[ValueError]) -> dict[str, Any]:
    match = _JSON_RE.search(text)
    if match is None:
        raise error("model returned no JSON")
    try:
        parsed = json.loads(match.group(0))
    except ValueError as exc:
        raise error("model returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise error("model JSON is not an object")
    return parsed


def blocks_to_md(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "text" and block.get("md"):
            parts.append(str(block["md"]))
        elif block.get("latex"):
            parts.append(f"${block['latex']}$")
    return "\n".join(parts)


_ANSWER_FENCE_RE = re.compile(r"```(chart|widget)\s*\n(.*?)```", re.DOTALL)


def parse_answer_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    position = 0
    for match in _ANSWER_FENCE_RE.finditer(markdown):
        prefix = markdown[position : match.start()]
        if prefix.strip():
            blocks.append({"type": "text", "md": prefix})
        kind = match.group(1)
        body = match.group(2).strip()
        try:
            payload = json.loads(body)
        except ValueError:
            blocks.append({"type": "text", "md": match.group(0)})
            position = match.end()
            continue
        if kind == "chart":
            blocks.append({"type": "chart", "plotly": payload})
        elif isinstance(payload, dict) and payload.get("widget"):
            blocks.append({"type": "widget", **payload})
        else:
            blocks.append({"type": "text", "md": match.group(0)})
        position = match.end()
    suffix = markdown[position:]
    if suffix.strip():
        blocks.append({"type": "text", "md": suffix})
    if not blocks:
        blocks.append({"type": "text", "md": markdown})
    return blocks
