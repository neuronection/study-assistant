from app.agui.events import (
    Custom,
    EventType,
    RunError,
    RunFinished,
    RunStarted,
    StateDelta,
    StepStarted,
    TextMessageContent,
    TextMessageStart,
    ToolCallResult,
    ToolCallStart,
    serialize,
)


def test_run_started_serializes_camel_case() -> None:
    event = RunStarted(thread_id="t1", run_id="r1")
    assert serialize(event) == {"type": "RUN_STARTED", "threadId": "t1", "runId": "r1"}


def test_nested_identifiers_serialize_camel_case() -> None:
    event = ToolCallStart(
        tool_call_id="tc1",
        tool_call_name="tools:math",
        parent_message_id="m1",
    )
    payload = serialize(event)
    assert payload == {
        "type": "TOOL_CALL_START",
        "toolCallId": "tc1",
        "toolCallName": "tools:math",
        "parentMessageId": "m1",
    }


def test_every_event_type_uses_the_agui_vocabulary() -> None:
    events = [
        RunStarted(thread_id="t", run_id="r"),
        RunFinished(thread_id="t", run_id="r"),
        RunError(message="boom"),
        StepStarted(step_name="tool:math"),
        TextMessageStart(message_id="m", role="assistant"),
        TextMessageContent(message_id="m", delta="hi"),
        ToolCallStart(tool_call_id="tc", tool_call_name="CALC"),
        ToolCallResult(tool_call_id="tc", content="4"),
        StateDelta(delta=[]),
    ]
    assert [serialize(event)["type"] for event in events] == [
        EventType.RUN_STARTED.value,
        EventType.RUN_FINISHED.value,
        EventType.RUN_ERROR.value,
        EventType.STEP_STARTED.value,
        EventType.TEXT_MESSAGE_START.value,
        EventType.TEXT_MESSAGE_CONTENT.value,
        EventType.TOOL_CALL_START.value,
        EventType.TOOL_CALL_RESULT.value,
        EventType.STATE_DELTA.value,
    ]


def test_none_fields_are_dropped_on_serialize() -> None:
    event = RunStarted(thread_id="t", run_id="r", metadata={"k": "v"})
    assert "timestamp" not in serialize(event)
    assert serialize(event)["metadata"] == {"k": "v"}


def test_unknown_fields_are_preserved() -> None:
    event = Custom(name="future_event", value={"x": 1})
    payload = serialize(event)
    assert payload == {"type": "CUSTOM", "name": "future_event", "value": {"x": 1}}
