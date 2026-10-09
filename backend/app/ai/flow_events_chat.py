"""Study's app-side half of the flow-event contract (plan 25 A1).

The vendored family core (``ai/flow_events.py``) builds the §5 payloads;
this module binds study's WS envelope — the event name rides the
``type`` field (ai-features §5 transport mapping) — and owns the
app-specific halves of the split: the chat step list + labels and the
persisted tool-call entry projection (tool-id derivation).
"""

from typing import Any

from . import flow_events as core

CHAT_FLOW_STEPS: list[dict[str, str]] = [
    {"id": "thinking", "label": "Thinking"},
    {"id": "tools", "label": "Tool work"},
    {"id": "answer", "label": "Answer"},
]

_NAME_KEY = "type"


def flow_started_event(run_id: str) -> dict[str, Any]:
    return core.flow_started_event(
        run_id=run_id,
        steps=[dict(step) for step in CHAT_FLOW_STEPS],
        name_key=_NAME_KEY,
    )


def node_started_event(node: str) -> dict[str, Any]:
    return core.node_started_event(node, name_key=_NAME_KEY)


def delta_event(text: str, kind: str | None = None) -> dict[str, Any]:
    return core.delta_event(text, kind, name_key=_NAME_KEY)


def tool_call_event(entry: dict[str, Any]) -> dict[str, Any]:
    """Project a persisted tool-call entry onto the §5 ``tool_call`` event.

    The entry itself (``argument``/``phase``/``start_ms``/``quiz``…) stays
    the storage shape on ``chat_messages.tool_calls``; the tool id is
    derived app-side (``name@start_ms``). Only the frozen §5 wire fields
    leave this function.
    """
    name = str(entry.get("name") or "tool")
    return core.tool_call_event(
        id=f"{name}@{entry.get('start_ms') or 0}",
        name=name,
        status=str(entry.get("status") or "done"),
        args=str(entry.get("argument") or ""),
        result=entry.get("result"),
        title=entry.get("title"),
        duration_ms=entry.get("duration_ms"),
        name_key=_NAME_KEY,
    )


def flow_finished_event(
    run_id: str,
    message_id: int,
    model: str | None = None,
    total_ms: int | None = None,
    tool_count: int | None = None,
) -> dict[str, Any]:
    return core.flow_finished_event(
        run_id=run_id,
        result_ref=str(message_id),
        model=model,
        total_ms=total_ms,
        tool_count=tool_count,
        name_key=_NAME_KEY,
    )


def flow_interrupted_event(reason: str, partial: bool) -> dict[str, Any]:
    return core.flow_interrupted_event(reason, partial, name_key=_NAME_KEY)


def flow_failed_event(code: str, message: str, retryable: bool = True) -> dict[str, Any]:
    return core.flow_failed_event(
        retryable=retryable,
        code=code,
        message=message,
        name_key=_NAME_KEY,
    )
