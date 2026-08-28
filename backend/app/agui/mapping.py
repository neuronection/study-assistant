import uuid
from typing import Any

from .events import (
    BaseEvent,
    Custom,
    RunError,
    RunFinished,
    RunStarted,
    StepFinished,
    StepStarted,
    TextMessageContent,
    TextMessageEnd,
    TextMessageStart,
    ToolCallArgs,
    ToolCallEnd,
    ToolCallResult,
    ToolCallStart,
)


class ChatStreamAdapter:
    def __init__(self, thread_id: str, run_id: str | None = None) -> None:
        self.thread_id = thread_id
        self.run_id = run_id or uuid.uuid4().hex
        self._run_started = False
        self._run_finished = False
        self._message_open = False
        self._message_id = f"{self.run_id}:assistant"
        self._tool_seq = 0

    def feed(self, event: dict[str, Any]) -> list[BaseEvent]:
        kind = event.get("type")
        if kind == "stream_start":
            return self._start()
        if kind == "stream_delta":
            return self._delta(event)
        if kind == "tool_round":
            return self._tool_round(event)
        if kind == "tool_call":
            return self._tool_call(event)
        if kind == "turn_error":
            return self._error(event)
        if kind == "assistant_message":
            return self._assistant_message(event)
        return [Custom(name=str(kind), value=event)]

    def _start(self) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if not self._run_started:
            events.append(RunStarted(thread_id=self.thread_id, run_id=self.run_id))
            self._run_started = True
        if not self._message_open:
            events.append(TextMessageStart(message_id=self._message_id, role="assistant"))
            self._message_open = True
        return events

    def _delta(self, event: dict[str, Any]) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if not self._message_open:
            events.extend(self._start())
        events.append(
            TextMessageContent(
                message_id=self._message_id,
                delta=str(event.get("delta", "")),
            )
        )
        return events

    def _tool_round(self, event: dict[str, Any]) -> list[BaseEvent]:
        phase = str(event.get("phase", ""))
        step_name = f"tool:{phase}"
        tool_call_id = f"{self.run_id}:tool:{self._tool_seq}"
        self._tool_seq += 1
        return [
            StepStarted(step_name=step_name),
            ToolCallStart(tool_call_id=tool_call_id, tool_call_name=f"tools:{phase}"),
            ToolCallEnd(tool_call_id=tool_call_id),
            StepFinished(step_name=step_name),
        ]

    def _tool_call(self, event: dict[str, Any]) -> list[BaseEvent]:
        name = str(event.get("name", "tool"))
        phase = str(event.get("phase", ""))
        tool_call_id = f"{self.run_id}:tool:{self._tool_seq}"
        self._tool_seq += 1
        events: list[BaseEvent] = [
            StepStarted(step_name=f"tool:{phase or name}"),
            ToolCallStart(tool_call_id=tool_call_id, tool_call_name=name),
            ToolCallArgs(tool_call_id=tool_call_id, delta=str(event.get("argument", ""))),
            ToolCallEnd(tool_call_id=tool_call_id),
        ]
        result = event.get("result")
        if result is not None:
            events.append(
                ToolCallResult(tool_call_id=tool_call_id, content=str(result))
            )
        events.append(StepFinished(step_name=f"tool:{phase or name}"))
        return events

    def _error(self, event: dict[str, Any]) -> list[BaseEvent]:
        self._message_open = False
        self._run_finished = True
        return [RunError(message=str(event.get("detail", "unknown error")))]

    def _assistant_message(self, event: dict[str, Any]) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if self._message_open:
            events.append(TextMessageEnd(message_id=self._message_id))
            self._message_open = False
        if self._run_started and not self._run_finished:
            events.append(RunFinished(thread_id=self.thread_id, run_id=self.run_id))
            self._run_finished = True
        return events

    def finish(self) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if self._message_open:
            events.append(TextMessageEnd(message_id=self._message_id))
            self._message_open = False
        if self._run_started and not self._run_finished:
            events.append(RunFinished(thread_id=self.thread_id, run_id=self.run_id))
            self._run_finished = True
        return events


def map_stream(
    events: list[dict[str, Any]],
    thread_id: str,
    run_id: str | None = None,
) -> list[BaseEvent]:
    adapter = ChatStreamAdapter(thread_id=thread_id, run_id=run_id)
    mapped: list[BaseEvent] = []
    for event in events:
        mapped.extend(adapter.feed(event))
    mapped.extend(adapter.finish())
    return mapped
