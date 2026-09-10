from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from test_chat_api import (
    NoDescriber,
    NoEmbedder,
    ScriptedGateway,
    add_material,
    make_course,
    wait_for_assistant,
)
from test_chat_graph_turn import drain_until, send, sse_harness, subscribe

from app.ai.gateway import Message, StreamChunk
from app.core.config import Settings
from app.main import create_app


class ReasoningGateway(ScriptedGateway):
    def stream_events(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Iterator[StreamChunk]:
        text = self.generate(task, messages, model)
        yield StreamChunk("reasoning", "Let me think about the power rule.")
        for i in range(0, len(text), 8):
            yield StreamChunk("text", text[i : i + 8])


def test_trace_is_persisted_and_returned(
    tmp_path: Any, migrated_db_template: Any
) -> None:
    with sse_harness(
        tmp_path,
        [["CALC 2", "**10\n"], ["The answer ", "is 1024."]],
        migrated_db_template,
    ) as h, subscribe(h.client, h.session_id) as ws:
        send(h, "what is 2^10")
        messages = wait_for_assistant(h.client, h.session_id)
        events = drain_until(ws, {"assistant_message"})
    assistant = messages[-1]
    trace = assistant["trace"]
    assert trace["run_id"]
    assert trace["model"] == "mock-chat"
    assert trace["latency_ms"] >= 0
    assert trace["input_tokens"] > 0
    assert trace["output_tokens"] > 0
    assert trace["repair_rounds"] == 0
    assert len(trace["rounds"]) == 2
    assert trace["rounds"][0]["streamed"] is True
    assert trace["rounds"][1]["streamed"] is True
    assert all(round_["duration_ms"] >= 0 for round_ in trace["rounds"])
    call = assistant["tool_calls"][0]
    assert call["name"] == "CALC"
    assert call["status"] == "done"
    assert call["start_ms"] >= 0
    assert call["duration_ms"] >= 0

    stream_start = next(e for e in events if e.get("type") == "stream_start")
    assert stream_start["run_id"] == trace["run_id"]
    assert stream_start["elapsed_ms"] >= 0
    deltas = [e for e in events if e.get("type") == "stream_delta"]
    assert deltas and all(e["elapsed_ms"] >= 0 for e in deltas)
    phases = [e for e in events if e.get("type") == "phase"]
    assert any(e["phase"] == "thinking" for e in phases)
    tool_events = [e for e in events if e.get("type") == "tool_call"]
    assert tool_events and all(e["status"] == "done" for e in tool_events)
    assistant_event = next(e for e in events if e.get("type") == "assistant_message")
    assert assistant_event["trace"]["run_id"] == trace["run_id"]


def test_reasoning_is_captured_but_kept_out_of_the_answer(tmp_path: Path) -> None:
    gateway = ReasoningGateway(["The derivative is $2x$ [1]."])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        course_id = make_course(client)
        add_material(client, "deriv.txt", "Power rule for derivatives.", course_id)
        session = client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "derivative of x^2"},
        )
        messages = wait_for_assistant(client, session["id"])
        assistant = messages[-1]
        assert "Let me think" not in assistant["markdown"]
        assert "Let me think" in assistant["trace"]["thinking"]


def test_repair_round_is_recorded(tmp_path: Path) -> None:
    gateway = ScriptedGateway(
        ["no citation here", "Here is a cited answer [1]."]
    )
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        course_id = make_course(client)
        add_material(
            client, "m.txt", "The chain rule differentiates composite functions.", course_id
        )
        session = client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "what is the chain rule"},
        )
        messages = wait_for_assistant(client, session["id"])
        trace = messages[-1]["trace"]
        assert trace["repair_rounds"] == 1
        assert any(round_["phase"] == "repairing" for round_ in trace["rounds"])


def test_stream_deltas_are_coalesced(
    tmp_path: Any, migrated_db_template: Any
) -> None:
    long_text = "The answer is " + "word " * 120
    chunks = [long_text[i : i + 40] for i in range(0, len(long_text), 40)]
    with sse_harness(tmp_path, [chunks], migrated_db_template) as h, subscribe(
        h.client, h.session_id
    ) as ws:
        send(h, "give me a long answer")
        wait_for_assistant(h.client, h.session_id)
        events = drain_until(ws, {"assistant_message"})
    deltas = [e for e in events if e.get("type") == "stream_delta"]
    assert deltas
    joined = "".join(e["delta"] for e in deltas)
    assert joined == long_text
    assert len(deltas) < len(long_text) / 8


def test_tool_lines_are_not_streamed_as_text_and_final_answer_streams(
    tmp_path: Any, migrated_db_template: Any
) -> None:
    with sse_harness(
        tmp_path,
        [["Let me verify.\nCALC 2", "**10\n"], ["The answer is 1024."]],
        migrated_db_template,
    ) as h, subscribe(h.client, h.session_id) as ws:
        send(h, "what is 2^10")
        wait_for_assistant(h.client, h.session_id)
        events = drain_until(ws, {"assistant_message"})
    joined = "".join(
        e["delta"]
        for e in events
        if e.get("type") == "stream_delta" and e.get("kind") != "reasoning"
    )
    assert "CALC" not in joined
    assert "Let me verify." in joined
    assert "The answer is 1024" in joined
