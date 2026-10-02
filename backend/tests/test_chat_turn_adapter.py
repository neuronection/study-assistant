import asyncio
import sys
import threading
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk

from app.ai.graphs import chat_turn_adapter
from app.ai.graphs.chat_turn_adapter import ChatTurnEngine, _DeltaPump


def _pump() -> tuple[_DeltaPump, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    return _DeltaPump(events.append, time.monotonic()), events


def test_late_tail_after_round_end_is_flushed_at_teardown() -> None:
    pump, events = _pump()
    pump.close_round(False)
    pump.on_text("the tail arrives without a trailing newline")
    pump.flush()
    assert [event["delta"] for event in events] == []
    pump.flush_round_end()
    assert [event["delta"] for event in events] == ["the tail arrives without a trailing newline"]


def test_concurrent_chunks_and_flushes_lose_no_text() -> None:
    pump, events = _pump()
    chunks = [f"word{i}\n" for i in range(4000)]
    stop = threading.Event()

    def flush_rounds() -> None:
        while not stop.is_set():
            pump.flush()
            pump.close_round(False)

    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    worker = threading.Thread(target=flush_rounds)
    worker.start()
    try:
        for chunk in chunks:
            pump.on_text(chunk)
    finally:
        stop.set()
        worker.join()
        sys.setswitchinterval(previous_interval)
    pump.flush_round_end()
    assert "".join(event["delta"] for event in events) == "".join(chunks)


class _FakeGraph:
    def __init__(self, stream: list[tuple[str, Any]]) -> None:
        self._stream = stream

    async def astream(
        self, _state: Any, _config: Any, stream_mode: Any = None
    ) -> AsyncIterator[tuple[str, Any]]:
        for item in self._stream:
            yield item


def test_tail_delivered_after_last_update_is_flushed_at_teardown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, Any]] = []
    stream: list[tuple[str, Any]] = [
        (
            "messages",
            (AIMessageChunk(content="streamed answer "), {"langgraph_step": 1}),
        ),
        ("updates", {"finalize": {"final_events": [], "message_id": 7}}),
        (
            "messages",
            (AIMessageChunk(content="the tail chunk"), {"langgraph_step": 1}),
        ),
    ]
    monkeypatch.setattr(
        chat_turn_adapter,
        "build_chat_turn_graph",
        lambda deps, check: _FakeGraph(stream),
    )

    def get(_model: Any, _pk: Any) -> Any:
        return SimpleNamespace(id=7)

    session: Any = SimpleNamespace(get=get)
    service: Any = SimpleNamespace()
    gateway: Any = SimpleNamespace()
    chat_session: Any = SimpleNamespace(id=1)
    user_message: Any = SimpleNamespace()
    bus: Any = SimpleNamespace(loop=None)
    engine = ChatTurnEngine(None, bus)
    message = asyncio.run(
        engine._run(
            session,
            service,
            gateway,
            chat_session,
            user_message,
            events.append,
            None,
        )
    )
    assert message is not None
    assert (
        "".join(event["delta"] for event in events if event.get("type") == "stream_delta")
        == "streamed answer the tail chunk"
    )
