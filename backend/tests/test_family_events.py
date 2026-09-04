import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.agui.family import to_family_events
from app.core.vocab import ChatEngine
from app.main import create_app

FAMILY_TYPES = frozenset(
    {"flow_started", "node_started", "node_finished", "delta", "flow_finished", "flow_failed"}
)


def test_stream_start_maps_to_flow_started_with_steps() -> None:
    events = to_family_events({"type": "stream_start", "run_id": "r1", "elapsed_ms": 3})
    assert events == [
        {
            "type": "flow_started",
            "flow": "chat",
            "run_id": "r1",
            "steps": [
                {"id": "thinking", "label": "Thinking"},
                {"id": "tools", "label": "Tool work"},
                {"id": "answer", "label": "Answer"},
            ],
        }
    ]


def test_phase_maps_to_node_started_and_tool_call_to_node_finished() -> None:
    assert to_family_events({"type": "phase", "phase": "computing"}) == [
        {"type": "node_started", "flow": "chat", "id": "computing", "label": "computing"}
    ]
    assert to_family_events(
        {
            "type": "tool_call",
            "name": "CALC",
            "argument": "2*21",
            "phase": "math",
            "status": "done",
            "result": "42",
        }
    ) == [
        {
            "type": "node_finished",
            "flow": "chat",
            "id": "tool:math",
            "label": "CALC",
            "outcome": "done",
            "detail": {"name": "CALC", "argument": "2*21", "result": "42"},
        }
    ]


def test_stream_delta_maps_to_delta_with_reasoning_kind() -> None:
    assert to_family_events({"type": "stream_delta", "delta": "hello"}) == [
        {"type": "delta", "flow": "chat", "text": "hello"}
    ]
    assert to_family_events(
        {"type": "stream_delta", "delta": "hm", "kind": "reasoning"}
    ) == [{"type": "delta", "flow": "chat", "text": "hm", "kind": "reasoning"}]


def test_assistant_message_and_turn_error_map_to_flow_endpoints() -> None:
    assert to_family_events(
        {
            "type": "assistant_message",
            "trace": {"run_id": "r9"},
            "message": {"id": 7},
        }
    ) == [
        {
            "type": "flow_finished",
            "flow": "chat",
            "run_id": "r9",
            "result": {"message_id": 7},
        }
    ]
    assert to_family_events({"type": "turn_error", "detail": "boom"}) == [
        {
            "type": "flow_failed",
            "flow": "chat",
            "code": "turn_error",
            "message": "boom",
            "retryable": False,
        }
    ]


def test_unmapped_events_produce_nothing() -> None:
    assert to_family_events({"type": "stream_interrupted", "detail": "x"}) == []
    assert to_family_events({"type": "mystery"}) == []
    assert to_family_events({"type": "phase"}) == []


@contextmanager
def chat_harness(tmp_path: Path) -> Iterator[tuple[TestClient, int]]:
    from app.core.config import Settings

    app = create_app(
        Settings(
            data_dir=tmp_path,
            config_dir=tmp_path / "config",
            spa_dist=tmp_path / "no-spa",
            log_level="WARNING",
            chat_engine=ChatEngine.GRAPH,
        ),
        gateway=ScriptedGateway(["The answer, with care."]),
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        session_id = int(client.post("/api/v1/chat/sessions", json={}).json()["id"])
        yield client, session_id


def test_chat_turn_publishes_family_events_alongside_legacy(tmp_path: Path) -> None:
    with chat_harness(tmp_path) as (client, session_id), client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "subscribe", "topic": f"chat:{session_id}"})
        ws.receive_json()
        client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"content": "hello"},
        )
        legacy: list[str] = []
        family: list[str] = []
        start = time.monotonic()
        while time.monotonic() - start < 30:
            ws.send_json({"type": "ping"})
            done = False
            while True:
                message = ws.receive_json()
                if message.get("type") == "pong":
                    break
                payload = message["payload"]
                if payload["type"] == "flow_finished":
                    done = True
                if payload["type"] in FAMILY_TYPES:
                    family.append(payload["type"])
                else:
                    legacy.append(payload["type"])
            if done:
                break
        else:
            raise AssertionError("flow_finished never arrived")

    assert "flow_started" in family
    assert "node_started" in family
    assert "flow_finished" in family
    assert legacy[-1] == "assistant_message"
    assert family[-1] == "flow_finished"
