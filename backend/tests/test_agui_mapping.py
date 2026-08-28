from typing import Any

from app.agui import ChatStreamAdapter, map_stream, serialize_many


def test_map_stream_parity_snapshot() -> None:
    legacy: list[dict[str, Any]] = [
        {"type": "stream_start"},
        {"type": "stream_delta", "delta": "The "},
        {"type": "stream_delta", "delta": "derivative is $3x^2$."},
        {"type": "tool_round", "phase": "math"},
        {"type": "stream_delta", "delta": " Done."},
        {
            "type": "assistant_message",
            "message": {"id": 7, "role": "assistant", "markdown": "final"},
        },
    ]
    payloads = serialize_many(map_stream(legacy, thread_id="t1", run_id="r1"))
    assert payloads == [
        {"type": "RUN_STARTED", "threadId": "t1", "runId": "r1"},
        {"type": "TEXT_MESSAGE_START", "messageId": "r1:assistant", "role": "assistant"},
        {"type": "TEXT_MESSAGE_CONTENT", "messageId": "r1:assistant", "delta": "The "},
        {
            "type": "TEXT_MESSAGE_CONTENT",
            "messageId": "r1:assistant",
            "delta": "derivative is $3x^2$.",
        },
        {"type": "STEP_STARTED", "stepName": "tool:math"},
        {"type": "TOOL_CALL_START", "toolCallId": "r1:tool:0", "toolCallName": "tools:math"},
        {"type": "TOOL_CALL_END", "toolCallId": "r1:tool:0"},
        {"type": "STEP_FINISHED", "stepName": "tool:math"},
        {"type": "TEXT_MESSAGE_CONTENT", "messageId": "r1:assistant", "delta": " Done."},
        {"type": "TEXT_MESSAGE_END", "messageId": "r1:assistant"},
        {"type": "RUN_FINISHED", "threadId": "t1", "runId": "r1"},
    ]


def test_map_stream_unknown_event_falls_through_as_custom() -> None:
    legacy: list[dict[str, Any]] = [
        {"type": "stream_start"},
        {"type": "some_future_event", "payload": 1},
    ]
    payloads = serialize_many(map_stream(legacy, thread_id="t", run_id="r"))
    custom = next(p for p in payloads if p["type"] == "CUSTOM")
    assert custom["name"] == "some_future_event"
    assert custom["value"] == {"type": "some_future_event", "payload": 1}


def test_tool_call_maps_to_start_args_end_result() -> None:
    legacy: list[dict[str, Any]] = [
        {"type": "stream_start"},
        {
            "type": "tool_call",
            "name": "CALC",
            "argument": "sin(pi/6)",
            "result": "0.5",
            "phase": "math",
        },
        {"type": "assistant_message", "message": {}},
    ]
    payloads = serialize_many(map_stream(legacy, thread_id="t", run_id="r"))
    assert {"type": "STEP_STARTED", "stepName": "tool:math"} in payloads
    assert {
        "type": "TOOL_CALL_START",
        "toolCallId": "r:tool:0",
        "toolCallName": "CALC",
    } in payloads
    assert {
        "type": "TOOL_CALL_ARGS",
        "toolCallId": "r:tool:0",
        "delta": "sin(pi/6)",
    } in payloads
    assert {"type": "TOOL_CALL_END", "toolCallId": "r:tool:0"} in payloads
    assert {
        "type": "TOOL_CALL_RESULT",
        "toolCallId": "r:tool:0",
        "content": "0.5",
        "role": "tool",
    } in payloads


def test_turn_error_maps_to_run_error() -> None:
    legacy: list[dict[str, Any]] = [
        {"type": "stream_start"},
        {"type": "turn_error", "detail": "provider offline"},
    ]
    payloads = serialize_many(map_stream(legacy, thread_id="t", run_id="r"))
    assert {"type": "RUN_ERROR", "message": "provider offline"} in payloads
    assert not any(p["type"] == "RUN_FINISHED" for p in payloads)


def test_adapter_finish_closes_open_message_and_run() -> None:
    adapter = ChatStreamAdapter(thread_id="t", run_id="r")
    events = adapter.feed({"type": "stream_start"})
    events += adapter.feed({"type": "stream_delta", "delta": "hi"})
    events += adapter.finish()
    types = [event.type for event in events]
    assert types == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]


def test_adapter_is_idempotent_across_assistant_message_and_finish() -> None:
    adapter = ChatStreamAdapter(thread_id="t", run_id="r")
    adapter.feed({"type": "stream_start"})
    adapter.feed({"type": "assistant_message", "message": {}})
    assert adapter.finish() == []
