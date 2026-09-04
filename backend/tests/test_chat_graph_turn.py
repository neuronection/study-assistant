import asyncio
import json
import shutil
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient
from langgraph.graph import START, StateGraph
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway
from typing_extensions import TypedDict

from app.ai.gateway import LLMGateway, StreamChunk
from app.ai.graphs.checkpointer import open_checkpointer, prune_checkpoints
from app.core.config import Settings
from app.core.vocab import ChatEngine
from app.domain.models import AiModel, Provider, TaskAssignment
from app.main import create_app
from app.storage.db import make_engine, make_session_factory


def make_settings(tmp_path: Path, engine: ChatEngine = ChatEngine.GRAPH) -> Settings:
    return Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        chat_engine=engine,
    )


class Harness:
    def __init__(
        self,
        client: TestClient,
        gateway: Any,
        session_id: int,
    ) -> None:
        self.client = client
        self.gateway = gateway
        self.session_id = session_id


@contextmanager
def turn_harness(
    tmp_path: Path, responses: list[str], engine: ChatEngine = ChatEngine.GRAPH
) -> Iterator[Harness]:
    gateway = ScriptedGateway(list(responses))
    app = create_app(
        make_settings(tmp_path, engine),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        session_id = int(client.post("/api/v1/chat/sessions", json={}).json()["id"])
        yield Harness(client, gateway, session_id)


@contextmanager
def sse_harness(
    tmp_path: Path,
    bodies: list[list[str]],
    migrated_db_template: Path,
    engine: ChatEngine = ChatEngine.GRAPH,
) -> Iterator[Harness]:
    """App wired to a real LangChain chat model behind a scripted SSE transport.

    The model streams the chunks of `bodies[i]` on the i-th request, so the
    graph and legacy engines run the identical production delta path.
    """
    settings = make_settings(tmp_path, engine)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(migrated_db_template, settings.db_path)
    sql_engine = make_engine(settings.db_path)
    factory = make_session_factory(sql_engine)
    with factory() as session:
        provider = Provider(
            name="mock",
            type="openai_compatible",
            base_url="http://localhost/v1",
            keyring_ref="mock-chat-key",
            enabled=True,
        )
        session.add(provider)
        session.flush()
        model = AiModel(
            provider_id=provider.id,
            external_id="mock-chat",
            label="mock-chat",
            caps=["text"],
            enabled=True,
        )
        session.add(model)
        session.flush()
        session.add(TaskAssignment(task="chat", model_id=model.id))
        session.commit()

    remaining = list(bodies)

    def handler(request: httpx.Request) -> httpx.Response:
        chunks = remaining.pop(0) if remaining else ["..."]
        lines = []
        for chunk in chunks:
            body = json.dumps({"choices": [{"delta": {"content": chunk}}]})
            lines.append(b"data: " + body.encode() + b"\n\n")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(lines) + b"data: [DONE]\n\n",
        )

    gateway = LLMGateway(factory, transport=httpx.MockTransport(handler))
    app = create_app(
        settings,
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    try:
        with TestClient(app) as client:
            session_id = int(
                client.post("/api/v1/chat/sessions", json={}).json()["id"]
            )
            yield Harness(client, gateway, session_id)
    finally:
        sql_engine.dispose()


@contextmanager
def subscribe(client: TestClient, session_id: int) -> Iterator[Any]:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "subscribe", "topic": f"chat:{session_id}"})
        assert ws.receive_json() == {
            "type": "subscribed",
            "topic": f"chat:{session_id}",
        }
        yield ws


def send(harness: Harness, content: str) -> None:
    response = harness.client.post(
        f"/api/v1/chat/sessions/{harness.session_id}/messages",
        json={"content": content},
    )
    assert response.status_code == 200


def wait_for_assistant(
    harness: Harness, timeout: float = 30.0
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    messages: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        messages = harness.client.get(
            f"/api/v1/chat/sessions/{harness.session_id}/messages"
        ).json()
        if messages and messages[-1]["role"] == "assistant":
            return messages
        time.sleep(0.05)
    raise AssertionError(
        f"assistant never replied within {timeout}s; last messages: {messages!r}"
    )


def drain_until(
    ws: Any, terminal: set[str], timeout: float = 30.0
) -> list[dict[str, Any]]:
    """Collect chat-topic events until one of `terminal` arrived (the pong
    only flushes what the bus already delivered — the turn's final event can
    land on the bus just after its DB row is visible, so keep pinging)."""
    events: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ws.send_json({"type": "ping"})
        message = ws.receive_json()
        while message.get("type") != "pong":
            events.append(message["payload"])
            message = ws.receive_json()
        if any(event.get("type") in terminal for event in events):
            return events
    raise AssertionError(
        f"terminal event {terminal} never arrived within {timeout}s; "
        f"events so far: {events!r}"
    )


def normalize(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stripped = [
        {
            key: value
            for key, value in event.items()
            if key not in ("elapsed_ms", "run_id", "start_ms", "duration_ms")
        }
        for event in events
    ]
    for event in stripped:
        if event.get("type") == "assistant_message":
            trace = event.get("trace") or {}
            event["trace"] = {
                key: value
                for key, value in trace.items()
                if key not in ("run_id", "latency_ms", "rounds", "thinking")
            }
            message = event.get("message") or {}
            event["message"] = {
                key: value for key, value in message.items() if key != "id"
            }
            event["message"]["tool_calls"] = [
                {
                    key: value
                    for key, value in tool_call.items()
                    if key not in ("start_ms", "duration_ms")
                }
                for tool_call in message.get("tool_calls") or []
            ]
    return stripped


def thread_ids(checkpoints_path: Path) -> list[str]:
    connection = sqlite3.connect(checkpoints_path)
    try:
        rows = connection.execute(
            "SELECT DISTINCT thread_id FROM checkpoints"
        ).fetchall()
    finally:
        connection.close()
    return sorted(str(row[0]) for row in rows)


def streamed_text(events: list[dict[str, Any]]) -> str:
    return "".join(
        event["delta"]
        for event in events
        if event.get("type") == "stream_delta" and "kind" not in event
    )


def test_chat_engine_flag_defaults_to_graph(tmp_path: Path) -> None:
    assert make_settings(tmp_path).chat_engine == ChatEngine.GRAPH
    assert Settings(data_dir=tmp_path).chat_engine == ChatEngine.GRAPH
    legacy_app = create_app(
        make_settings(tmp_path / "legacy-app", ChatEngine.LEGACY),
        gateway=ScriptedGateway(["unused"]),
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    assert getattr(legacy_app.state, "chat_turns", None) is None
    assert not (tmp_path / "legacy-app" / "checkpoints.db").exists()
    graph_app = create_app(
        make_settings(tmp_path / "graph-app"),
        gateway=ScriptedGateway(["unused"]),
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(graph_app):
        assert getattr(graph_app.state, "chat_turns", None) is not None
        assert (tmp_path / "graph-app" / "checkpoints.db").exists()


def test_graph_turn_persists_and_emits_contract_events(tmp_path: Path) -> None:
    with turn_harness(
        tmp_path, ["Follow the derivation **step by step**."]
    ) as h, subscribe(h.client, h.session_id) as ws:
        send(h, "Explain the chain rule")
        messages = wait_for_assistant(h)
        events = drain_until(ws, {"assistant_message"})

    assert messages[-1]["blocks"][0]["md"] == (
        "Follow the derivation **step by step**."
    )
    assert [event["type"] for event in events] == [
        "stream_start",
        "flow_started",
        "phase",
        "node_started",
        "assistant_message",
        "flow_finished",
    ]
    assert events[1]["flow"] == "chat"
    assert events[2]["phase"] == "thinking"
    assert events[3]["id"] == "thinking"
    assert messages[-1]["trace"]["repair_rounds"] == 0
    assert thread_ids(tmp_path / "checkpoints.db") == [str(h.session_id)]


def test_graph_matches_legacy_event_contract(
    tmp_path: Path, migrated_db_template: Path
) -> None:
    def run(
        root: Path, engine: ChatEngine, migrated: Path
    ) -> list[dict[str, Any]]:
        with sse_harness(
            root, [["Hello ", "from the ", "model."]], migrated, engine
        ) as h, subscribe(h.client, h.session_id) as ws:
            send(h, "question one")
            wait_for_assistant(h)
            return normalize(drain_until(ws, {"assistant_message"}))

    legacy = run(
        tmp_path / "legacy", ChatEngine.LEGACY, migrated_db_template
    )
    graph = run(tmp_path / "graph", ChatEngine.GRAPH, migrated_db_template)
    assert graph == legacy
    assert streamed_text(graph) == "Hello from the model."
    family_types = [event["type"] for event in graph if "flow" in event]
    assert "flow_started" in family_types
    assert family_types[-1] == "flow_finished"


def test_graph_tool_round_matches_legacy(
    tmp_path: Path, migrated_db_template: Path
) -> None:
    bodies = [["CALC 2", "*21\n"], ["The answer ", "is $42$."]]

    def run(root: Path, engine: ChatEngine, migrated: Path) -> list[dict[str, Any]]:
        with sse_harness(root, bodies, migrated, engine) as h, subscribe(
            h.client, h.session_id
        ) as ws:
            send(h, "compute 2*21 with the tool")
            wait_for_assistant(h)
            messages = h.client.get(
                f"/api/v1/chat/sessions/{h.session_id}/messages"
            ).json()
            drained = normalize(drain_until(ws, {"assistant_message"}))
        final = {"_final": messages[-1]["blocks"][0]["md"]}
        return [*drained, final]

    legacy = run(tmp_path / "legacy", ChatEngine.LEGACY, migrated_db_template)
    graph = run(tmp_path / "graph", ChatEngine.GRAPH, migrated_db_template)
    assert graph == legacy
    assert graph[-1]["_final"] == "The answer is $42$."
    tool_events = [event for event in graph if event.get("type") == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["name"] == "CALC"
    assert tool_events[0]["result"] == "42"
    assert streamed_text(graph) == "The answer is $42$."


def test_graph_repair_round_matches_legacy(
    tmp_path: Path, migrated_db_template: Path
) -> None:
    filler = " ".join(["filler"] * 450)
    bodies = [[filler[i : i + 40] for i in range(0, len(filler), 40)], ["short ", "answer"]]

    def run(root: Path, engine: ChatEngine, migrated: Path) -> list[dict[str, Any]]:
        with sse_harness(root, bodies, migrated, engine) as h, subscribe(
            h.client, h.session_id
        ) as ws:
            send(h, "say something short")
            wait_for_assistant(h)
            return normalize(drain_until(ws, {"assistant_message"}))

    legacy = run(tmp_path / "legacy", ChatEngine.LEGACY, migrated_db_template)
    graph = run(tmp_path / "graph", ChatEngine.GRAPH, migrated_db_template)
    assert graph == legacy
    phases = [event["phase"] for event in graph if event.get("type") == "phase"]
    assert phases == ["thinking", "repairing"]
    assert streamed_text(graph).endswith("short answer")


class StoppableSlowGateway(ScriptedGateway):
    """Streams tiny chunks until the registered stop event flips."""

    def __init__(self) -> None:
        super().__init__(["ignored"])
        self.stop = threading.Event()

    def stream_events(
        self,
        task: str,
        messages: list[Any],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        index = 0
        while not self.stop.is_set() and index < 400:
            yield StreamChunk("text", f"chunk {index} line\n")
            index += 1
            time.sleep(0.02)


def test_graph_stop_mid_stream_persists_prefix(tmp_path: Path) -> None:
    gateway = StoppableSlowGateway()
    app = create_app(
        make_settings(tmp_path),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        session_id = int(client.post("/api/v1/chat/sessions", json={}).json()["id"])
        with subscribe(client, session_id) as ws:
            response = client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                json={"content": "stop me"},
            )
            assert response.status_code == 200
            time.sleep(0.5)
            deadline = time.monotonic() + 30
            stopped = False
            while time.monotonic() < deadline:
                if client.post(
                    f"/api/v1/chat/sessions/{session_id}/stop"
                ).json()["stopped"]:
                    stopped = True
                    break
                time.sleep(0.05)
            assert stopped, "turn was not running when stop was requested"
            messages = wait_for_assistant(Harness(client, gateway, session_id))
            events = drain_until(ws, {"assistant_message"})

    stored = messages[-1]["blocks"][0]["md"]
    assert stored == "" or stored.startswith("chunk 0 ")
    assert "chunk 399" not in stored
    assert messages[-1]["trace"]["stream_interrupted"] is True
    assert [event["type"] for event in events][-3:] == [
        "stream_interrupted",
        "assistant_message",
        "flow_finished",
    ]
    assert events[0]["type"] in ("stream_start", "stream_interrupted")


def test_open_checkpointer_creates_schema(tmp_path: Path) -> None:
    async def main() -> None:
        async with open_checkpointer("sqlite", tmp_path / "checkpoints.db"):
            pass

    asyncio.run(main())
    connection = sqlite3.connect(tmp_path / "checkpoints.db")
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()
    assert {"checkpoints", "writes"} <= tables


def test_open_checkpointer_postgres_without_uri_raises(tmp_path: Path) -> None:
    async def main() -> None:
        async with open_checkpointer("postgresql", tmp_path / "checkpoints.db"):
            pass

    try:
        asyncio.run(main())
    except ValueError as error:
        assert "postgres checkpointing needs a database uri" in str(error)
    else:
        raise AssertionError("expected ValueError for missing postgres uri")


def test_prune_checkpoints_removes_stale_threads_only(tmp_path: Path) -> None:
    class Probe(TypedDict, total=False):
        x: int

    async def build() -> None:
        async with open_checkpointer("sqlite", tmp_path / "checkpoints.db") as saver:
            graph = (
                StateGraph(Probe)
                .add_node("n", lambda state: {"x": 1})
                .add_edge(START, "n")
                .compile(checkpointer=saver)
            )
            await graph.ainvoke({"x": 0}, {"configurable": {"thread_id": "fresh"}})
            await graph.ainvoke({"x": 0}, {"configurable": {"thread_id": "stale"}})

    asyncio.run(build())

    db_path = tmp_path / "checkpoints.db"
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT rowid, thread_id FROM checkpoints WHERE thread_id = 'stale'"
        ).fetchall()
        assert rows
        for rowid, _thread_id in rows:
            connection.execute(
                "UPDATE checkpoints SET checkpoint_id = ? WHERE rowid = ?",
                (f"{rowid:012d}", rowid),
            )
        connection.commit()
        stale_count = len(rows)
    finally:
        connection.close()

    deleted = prune_checkpoints(db_path, ttl_days=14, now_ms=int(time.time() * 1000))
    assert deleted == stale_count
    assert thread_ids(db_path) == ["fresh"]
    assert prune_checkpoints(db_path, ttl_days=14) == 0
    assert prune_checkpoints(tmp_path / "missing.db", ttl_days=14) == 0
