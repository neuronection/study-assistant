from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class EventType(StrEnum):
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"
    MESSAGES_SNAPSHOT = "MESSAGES_SNAPSHOT"
    ACTIVITY_SNAPSHOT = "ACTIVITY_SNAPSHOT"
    ACTIVITY_DELTA = "ACTIVITY_DELTA"
    CUSTOM = "CUSTOM"
    RAW = "RAW"


class BaseEvent(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )

    type: str
    timestamp: float | None = None
    raw_event: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class RunStarted(BaseEvent):
    type: Literal["RUN_STARTED"] = "RUN_STARTED"
    thread_id: str
    run_id: str


class RunFinished(BaseEvent):
    type: Literal["RUN_FINISHED"] = "RUN_FINISHED"
    thread_id: str
    run_id: str


class RunError(BaseEvent):
    type: Literal["RUN_ERROR"] = "RUN_ERROR"
    message: str
    code: str | None = None


class StepStarted(BaseEvent):
    type: Literal["STEP_STARTED"] = "STEP_STARTED"
    step_name: str


class StepFinished(BaseEvent):
    type: Literal["STEP_FINISHED"] = "STEP_FINISHED"
    step_name: str


class TextMessageStart(BaseEvent):
    type: Literal["TEXT_MESSAGE_START"] = "TEXT_MESSAGE_START"
    message_id: str
    role: str


class TextMessageContent(BaseEvent):
    type: Literal["TEXT_MESSAGE_CONTENT"] = "TEXT_MESSAGE_CONTENT"
    message_id: str
    delta: str


class TextMessageEnd(BaseEvent):
    type: Literal["TEXT_MESSAGE_END"] = "TEXT_MESSAGE_END"
    message_id: str


class ToolCallStart(BaseEvent):
    type: Literal["TOOL_CALL_START"] = "TOOL_CALL_START"
    tool_call_id: str
    tool_call_name: str
    parent_message_id: str | None = None


class ToolCallArgs(BaseEvent):
    type: Literal["TOOL_CALL_ARGS"] = "TOOL_CALL_ARGS"
    tool_call_id: str
    delta: str


class ToolCallEnd(BaseEvent):
    type: Literal["TOOL_CALL_END"] = "TOOL_CALL_END"
    tool_call_id: str


class ToolCallResult(BaseEvent):
    type: Literal["TOOL_CALL_RESULT"] = "TOOL_CALL_RESULT"
    message_id: str | None = None
    tool_call_id: str
    content: str
    role: str | None = "tool"


class StateSnapshot(BaseEvent):
    type: Literal["STATE_SNAPSHOT"] = "STATE_SNAPSHOT"
    snapshot: dict[str, Any]


class StateDelta(BaseEvent):
    type: Literal["STATE_DELTA"] = "STATE_DELTA"
    delta: list[dict[str, Any]]


class MessagesSnapshot(BaseEvent):
    type: Literal["MESSAGES_SNAPSHOT"] = "MESSAGES_SNAPSHOT"
    messages: list[dict[str, Any]]


class ActivitySnapshot(BaseEvent):
    type: Literal["ACTIVITY_SNAPSHOT"] = "ACTIVITY_SNAPSHOT"
    message_id: str
    activity_type: str
    content: dict[str, Any]


class ActivityDelta(BaseEvent):
    type: Literal["ACTIVITY_DELTA"] = "ACTIVITY_DELTA"
    message_id: str
    activity_type: str
    patch: list[dict[str, Any]]


class Custom(BaseEvent):
    type: Literal["CUSTOM"] = "CUSTOM"
    name: str
    value: Any


class Raw(BaseEvent):
    type: Literal["RAW"] = "RAW"
    event: dict[str, Any]


def serialize(event: BaseEvent) -> dict[str, Any]:
    return event.model_dump(by_alias=True, exclude_none=True)


def serialize_many(events: list[BaseEvent]) -> list[dict[str, Any]]:
    return [serialize(event) for event in events]
