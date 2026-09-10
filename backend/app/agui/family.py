"""Family event vocabulary mapper (guidelines §5, plan 10 Phase 6.2).

Translates the study chat-turn WS events (`stream_start` / `phase` /
`stream_delta` / `tool_call` / `assistant_message` / `turn_error`) into the
transport-agnostic family vocabulary (`flow_started` / `node_started` /
`node_finished` / `delta` / `flow_finished` / `flow_failed`), emitted
additively alongside the legacy names so existing consumers keep working.
Pure mapping: no transport, no state. `stream_interrupted` has no family
equivalent and maps to nothing.
"""

from typing import Any

from ..core.vocab import FlowEvent

CHAT_FLOW = "chat"

CHAT_FLOW_STEPS: list[dict[str, str]] = [
    {"id": "thinking", "label": "Thinking"},
    {"id": "tools", "label": "Tool work"},
    {"id": "answer", "label": "Answer"},
]


def to_family_events(event: dict[str, Any]) -> list[dict[str, Any]]:
    kind = event.get("type")
    if kind == "stream_start":
        return [
            {
                "type": FlowEvent.FLOW_STARTED,
                "flow": CHAT_FLOW,
                "run_id": event.get("run_id"),
                "steps": [dict(step) for step in CHAT_FLOW_STEPS],
            }
        ]
    if kind == "phase":
        phase = str(event.get("phase") or "")
        if not phase:
            return []
        return [
            {
                "type": FlowEvent.NODE_STARTED,
                "flow": CHAT_FLOW,
                "id": phase,
                "label": phase,
            }
        ]
    if kind == "tool_call":
        phase = str(event.get("phase") or "")
        name = str(event.get("name") or "")
        detail: dict[str, Any] = {"name": name, "argument": event.get("argument")}
        if event.get("result") is not None:
            detail["result"] = event.get("result")
        if event.get("title") is not None:
            detail["title"] = event.get("title")
        return [
            {
                "type": FlowEvent.NODE_FINISHED,
                "flow": CHAT_FLOW,
                "id": f"tool:{phase}" if phase else f"tool:{name}",
                "label": name,
                "outcome": str(event.get("status") or "done"),
                "detail": detail,
            }
        ]
    if kind == "stream_delta":
        family: dict[str, Any] = {
            "type": FlowEvent.DELTA,
            "flow": CHAT_FLOW,
            "text": event.get("delta") or "",
        }
        if event.get("kind") == "reasoning":
            family["kind"] = "reasoning"
        return [family]
    if kind == "assistant_message":
        trace = event.get("trace") or {}
        message = event.get("message") or {}
        return [
            {
                "type": FlowEvent.FLOW_FINISHED,
                "flow": CHAT_FLOW,
                "run_id": trace.get("run_id"),
                "result": {"message_id": message.get("id")},
            }
        ]
    if kind == "turn_error":
        return [
            {
                "type": FlowEvent.FLOW_FAILED,
                "flow": CHAT_FLOW,
                "code": "turn_error",
                "message": str(event.get("detail") or ""),
                "retryable": False,
            }
        ]
    return []
