"""Family vocabulary wall for the chat stream (plan 24 V2).

Every event the chat turn publishes on the ``chat:<id>`` WS topic must be
a family §5 event — the legacy dual-emit names are gone, and nothing new
may reintroduce them (the wire assertions below fail on any non-family
``type``). Builder unit tests pin the frozen payload fields.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.ai.flow_events import FlowEvent
from app.ai.flow_events_chat import (
    CHAT_FLOW_STEPS,
    delta_event,
    flow_failed_event,
    flow_finished_event,
    flow_interrupted_event,
    flow_started_event,
    node_started_event,
    tool_call_event,
)
from app.main import create_app

FAMILY_TYPES = frozenset(member.value for member in FlowEvent)


def test_flow_started_carries_flow_run_id_and_steps() -> None:
    event = flow_started_event("run-1")
    assert event == {
        "type": "flow_started",
        "flow": "chat",
        "run_id": "run-1",
        "steps": [dict(step) for step in CHAT_FLOW_STEPS],
    }
    assert {step["id"] for step in event["steps"]} == {"thinking", "tools", "answer"}


def test_node_started_carries_the_node_id_only() -> None:
    assert node_started_event("reading") == {"type": "node_started", "node": "reading"}


def test_delta_event_keeps_reasoning_kind_optional() -> None:
    assert delta_event("hello") == {"type": "delta", "text": "hello"}
    assert delta_event("hm", "reasoning") == {
        "type": "delta",
        "text": "hm",
        "kind": "reasoning",
    }


def test_tool_call_event_projects_the_persisted_entry() -> None:
    entry = {
        "name": "CALC",
        "argument": "2*21",
        "phase": "math",
        "status": "done",
        "start_ms": 42,
        "duration_ms": 7,
        "result": "42",
        "quiz": {"question": "ignored on the wire"},
    }
    assert tool_call_event(entry) == {
        "type": "tool_call",
        "id": "CALC@42",
        "name": "CALC",
        "status": "done",
        "args": "2*21",
        "result": "42",
        "duration_ms": 7,
    }
    assert tool_call_event({"name": "SEARCH", "argument": "chain rule"}) == {
        "type": "tool_call",
        "id": "SEARCH@0",
        "name": "SEARCH",
        "status": "done",
        "args": "chain rule",
    }


def test_terminal_events_carry_the_frozen_fields() -> None:
    assert flow_finished_event("run-2", 7, model="mock", total_ms=120, tool_count=1) == {
        "type": "flow_finished",
        "run_id": "run-2",
        "result_ref": "7",
        "model": "mock",
        "total_ms": 120,
        "tool_count": 1,
    }
    assert flow_finished_event("run-3", 9) == {
        "type": "flow_finished",
        "run_id": "run-3",
        "result_ref": "9",
    }
    assert flow_interrupted_event("user", True) == {
        "type": "flow_interrupted",
        "reason": "user",
        "partial": True,
    }
    assert flow_failed_event("turn_error", "boom") == {
        "type": "flow_failed",
        "code": "turn_error",
        "message": "boom",
        "retryable": True,
    }


@contextmanager
def chat_harness(tmp_path: Path) -> Iterator[tuple[TestClient, int]]:
    from app.core.config import Settings

    app = create_app(
        Settings(
            data_dir=tmp_path,
            config_dir=tmp_path / "config",
            spa_dist=tmp_path / "no-spa",
            log_level="WARNING",
        ),
        gateway=ScriptedGateway(["The answer, with care."]),
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        session_id = int(client.post("/api/v1/chat/sessions", json={}).json()["id"])
        yield client, session_id


def drain_turn(ws: Any, timeout: float = 30.0) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ws.send_json({"type": "ping"})
        message = ws.receive_json()
        while message.get("type") != "pong":
            events.append(message["payload"])
            message = ws.receive_json()
        if any(event.get("type") == "flow_finished" for event in events):
            return events
    raise AssertionError(f"flow_finished never arrived; events so far: {events!r}")


def test_chat_turn_publishes_family_events_only(tmp_path: Path) -> None:
    with chat_harness(tmp_path) as (client, session_id), client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "subscribe", "topic": f"chat:{session_id}"})
        ws.receive_json()
        client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"content": "hello"},
        )
        events = drain_turn(ws)

    types = [event["type"] for event in events]
    assert set(types) <= FAMILY_TYPES, f"non-family event on the chat topic: {types!r}"
    assert types[0] == "flow_started"
    assert events[0]["flow"] == "chat"
    assert events[0]["run_id"]
    assert "node_started" in types
    assert types[-1] == "flow_finished"
    assert events[-1]["result_ref"]
