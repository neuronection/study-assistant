"""Family chat-flow event builders (guidelines ai-features §5, plan 24 V2).

The chat turn emits the transport-agnostic family vocabulary natively on
the ``chat:<id>`` WS topic (event name in the ``type`` field); payload
fields follow the frozen §5 table. Node labels stay client-side (i18n):
``node_started`` carries the node id only. ``flow_interrupted`` carries no
run id so it reads as a broadcast stop (the library reducer gates on
``'run_id' in event``).
"""

from typing import Any

from ..core.vocab import FlowEvent

CHAT_FLOW = "chat"

CHAT_FLOW_STEPS: list[dict[str, str]] = [
    {"id": "thinking", "label": "Thinking"},
    {"id": "tools", "label": "Tool work"},
    {"id": "answer", "label": "Answer"},
]


def flow_started_event(run_id: str) -> dict[str, Any]:
    return {
        "type": FlowEvent.FLOW_STARTED,
        "flow": CHAT_FLOW,
        "run_id": run_id,
        "steps": [dict(step) for step in CHAT_FLOW_STEPS],
    }


def node_started_event(node: str) -> dict[str, Any]:
    return {"type": FlowEvent.NODE_STARTED, "node": node}


def delta_event(text: str, kind: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"type": FlowEvent.DELTA, "text": text}
    if kind is not None:
        event["kind"] = kind
    return event


def tool_call_event(entry: dict[str, Any]) -> dict[str, Any]:
    """Project a persisted tool-call entry onto the §5 ``tool_call`` event.

    The entry itself (``argument``/``phase``/``start_ms``/``quiz``…) stays
    the storage shape on ``chat_messages.tool_calls``; only the frozen wire
    fields leave this function.
    """
    name = str(entry.get("name") or "tool")
    event: dict[str, Any] = {
        "type": FlowEvent.TOOL_CALL,
        "id": f"{name}@{entry.get('start_ms') or 0}",
        "name": name,
        "status": str(entry.get("status") or "done"),
        "args": str(entry.get("argument") or ""),
    }
    if entry.get("result") is not None:
        event["result"] = entry["result"]
    if entry.get("title") is not None:
        event["title"] = entry["title"]
    if entry.get("duration_ms") is not None:
        event["duration_ms"] = entry["duration_ms"]
    return event


def flow_finished_event(
    run_id: str,
    message_id: int,
    model: str | None = None,
    total_ms: int | None = None,
    tool_count: int | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": FlowEvent.FLOW_FINISHED,
        "run_id": run_id,
        "result_ref": str(message_id),
    }
    if model is not None:
        event["model"] = model
    if total_ms is not None:
        event["total_ms"] = total_ms
    if tool_count is not None:
        event["tool_count"] = tool_count
    return event


def flow_interrupted_event(reason: str, partial: bool) -> dict[str, Any]:
    return {
        "type": FlowEvent.FLOW_INTERRUPTED,
        "reason": reason,
        "partial": partial,
    }


def flow_failed_event(code: str, message: str, retryable: bool = True) -> dict[str, Any]:
    return {
        "type": FlowEvent.FLOW_FAILED,
        "code": code,
        "message": message,
        "retryable": retryable,
    }
