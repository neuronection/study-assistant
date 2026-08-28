import json
import sys
from collections.abc import Iterator
from typing import Any

import httpx

from app.ai.chat_models import chat_native_schemas
from app.ai.gateway import LLMGateway, Message, ResolvedModel, StreamChunk


class NativeGateway(LLMGateway):
    def __init__(self, responses: list[Any], caps: list[str] | None = None) -> None:
        super().__init__(session_factory=None)
        self.responses = responses
        self.caps = caps or ["text", "tools"]
        self.calls: list[list[Message]] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="fake-native",
            label="fake-native",
            caps=self.caps,
            api_key=None,
        )

    def stream_events(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Iterator[StreamChunk]:
        from app.ai.gateway import StreamChunk

        response = self.responses.pop(0)
        self.calls.append(messages)
        if isinstance(response, list):
            for call in response:
                yield StreamChunk(
                    "tool_call",
                    json.dumps(
                        {
                            "id": call.get("id", "call_1"),
                            "name": call["name"],
                            "arguments": call.get("arguments", {}),
                        },
                        ensure_ascii=False,
                    ),
                )
            return
        text = response
        for i in range(0, len(text), 8):
            yield StreamChunk("text", text[i : i + 8])


def make_native_app(tmp_path: object, gateway: NativeGateway) -> Any:
    from fastapi.testclient import TestClient
    from test_chat_api import NoDescriber, NoEmbedder

    from app.core.config import Settings
    from app.main import create_app

    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),  # type: ignore[arg-type]
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def _course(client: Any) -> int:
    return int(client.post("/api/v1/courses", json={"title": "N"}).json()["id"])


def _session(client: Any) -> int:
    return int(client.post("/api/v1/chat/sessions", json={}).json()["id"])


def wait_for_assistant(client: Any, session_id: int, timeout: float = 5.0) -> list[dict[str, Any]]:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()
        if messages and messages[-1]["role"] == "assistant":
            return list(messages)
        time.sleep(0.05)
    raise AssertionError("no assistant message")


def test_native_calc_round_trip(tmp_path: object) -> None:
    gateway = NativeGateway(
        [
            [{"name": "CALC", "arguments": {"expression": "sin(pi/6)"}}],
            "The value is $0.5$. [1]",
        ]
    )
    with make_native_app(tmp_path, gateway) as client:
        _course(client)
        session = _session(client)
        client.post(
            f"/api/v1/chat/sessions/{session}/messages", json={"content": "hi"}
        )
        messages = wait_for_assistant(client, session)
        assistant = messages[-1]
        assert "0.5" in assistant["markdown"]
        assert "CALC" not in assistant["markdown"]
        assert len(assistant["tool_calls"]) == 1
        call = assistant["tool_calls"][0]
        assert call["name"] == "CALC"
        assert call["argument"] == "sin(pi/6)"
        assert call["phase"] == "math"
        assert call["result"] == "0.5"
        assert call["status"] == "done"
        assert len(gateway.calls) == 2
        second_messages = gateway.calls[1]
        roles = [m.role for m in second_messages]
        assert roles == ["system", "user", "assistant", "tool"]
        assert second_messages[2].tool_calls[0]["name"] == "CALC"
        assert second_messages[3].role == "tool"
        assert second_messages[3].content == "0.5"
        assert second_messages[3].tool_call_id == "call_1"
        assert len(assistant["trace"]["rounds"]) == 2


def test_native_sympy_round_trip(tmp_path: object) -> None:
    gateway = NativeGateway(
        [
            [{"name": "SYMPY", "arguments": {"action": "diff", "expression": "x**2"}}],
            "The derivative is $2x$. [1]",
        ]
    )
    with make_native_app(tmp_path, gateway) as client:
        _course(client)
        session = _session(client)
        client.post(
            f"/api/v1/chat/sessions/{session}/messages", json={"content": "hi"}
        )
        messages = wait_for_assistant(client, session)
        assistant = messages[-1]
        call = assistant["tool_calls"][0]
        assert call["name"] == "SYMPY"
        assert call["argument"] == "diff x**2"
        assert call["result"] == "2*x"
        assert "2x" in assistant["markdown"]


def test_native_resource_tool_round_trip(tmp_path: object) -> None:
    gateway = NativeGateway(
        [
            [{"name": "COURSES", "arguments": {}}],
            "Here are the courses. [1]",
        ]
    )
    with make_native_app(tmp_path, gateway) as client:
        course = _course(client)
        session = _session(client)
        client.post(
            f"/api/v1/chat/sessions/{session}/messages", json={"content": "hi"}
        )
        messages = wait_for_assistant(client, session)
        assistant = messages[-1]
        assert len(assistant["tool_calls"]) == 1
        call = assistant["tool_calls"][0]
        assert call["name"] == "COURSES"
        assert call["argument"] == ""
        assert call["phase"] == "read"
        assert course is not None


def test_native_cap_gate_uses_prompt_path_without_tools_cap(tmp_path: object) -> None:
    gateway = NativeGateway(
        [
            "Let me check.\nCALC 2^10\n",
            "It is $1024$. [1]",
        ],
        caps=["text"],
    )
    with make_native_app(tmp_path, gateway) as client:
        _course(client)
        session = _session(client)
        client.post(
            f"/api/v1/chat/sessions/{session}/messages", json={"content": "hi"}
        )
        messages = wait_for_assistant(client, session)
        assistant = messages[-1]
        assert len(assistant["tool_calls"]) == 1
        call = assistant["tool_calls"][0]
        assert call["name"] == "CALC"
        assert call["argument"] == "2^10"
        assert call["result"] == "1024"
        assert "CALC" not in assistant["markdown"]
        second_messages = gateway.calls[1]
        assert all(m.role != "tool" for m in second_messages)


def test_native_math_budget_bounds_rounds(tmp_path: object) -> None:
    gateway = NativeGateway(
        [
            [{"name": "CALC", "arguments": {"expression": "1+1"}}],
            [{"name": "CALC", "arguments": {"expression": "2+2"}}],
            [{"name": "CALC", "arguments": {"expression": "3+3"}}],
            "Done.",
        ]
    )
    with make_native_app(tmp_path, gateway) as client:
        _course(client)
        session = _session(client)
        client.post(
            f"/api/v1/chat/sessions/{session}/messages", json={"content": "hi"}
        )
        messages = wait_for_assistant(client, session)
        assistant = messages[-1]
        executed = [c for c in assistant["tool_calls"] if c["status"] == "done"]
        assert len(executed) == 2
        assert executed[0]["result"] == "2"
        assert executed[1]["result"] == "4"


def test_native_tool_call_ws_event_emitted(tmp_path: object) -> None:
    gateway = NativeGateway(
        [
            [{"name": "CALC", "arguments": {"expression": "sin(pi/2)"}}],
            "It is $1$. [1]",
        ]
    )
    sys.path.insert(0, "tests")
    from test_chat_api import NoDescriber, NoEmbedder

    from app.core.config import Settings
    from app.main import create_app

    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),  # type: ignore[arg-type]
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    events: list[dict[str, Any]] = []
    original = app.state.bus.publish_threadsafe

    def record(topic: str, payload: dict[str, Any]) -> None:
        if topic.startswith("chat:"):
            events.append(payload)
        original(topic, payload)

    app.state.bus.publish_threadsafe = record
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        _course(client)
        session = _session(client)
        client.post(
            f"/api/v1/chat/sessions/{session}/messages", json={"content": "hi"}
        )
        wait_for_assistant(client, session)
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "CALC"
    assert tool_calls[0]["argument"] == "sin(pi/2)"
    assert tool_calls[0]["result"] == "1"


def test_gateway_streams_native_tool_call_chunk() -> None:
    sse = (
        b'data: {"choices":[{"delta":{"role":"assistant","tool_calls":['
        b'{"index":0,"id":"call_9","function":{"name":"CALC","arguments":""}}]}}]}\n\n'
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        b'"function":{"arguments":"{\\"expression\\": \\"2+2\\"}"}}]}}]}\n\n'
        b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        b"data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=sse, headers={"content-type": "text/event-stream"}
        )

    gateway = LLMGateway(None, transport=httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="m",
        label="m",
        caps=["text", "tools"],
        api_key="k",
    )
    events = list(
        gateway.stream_events("chat", [Message(role="user", content="hi")], model=model)
    )
    calls = [json.loads(e.text) for e in events if e.kind == "tool_call"]
    assert calls == [
        {"id": "call_9", "name": "CALC", "arguments": {"expression": "2+2"}}
    ]


def test_chat_native_schemas_cover_all_tools() -> None:
    from app.ai.tools import CHAT_TOOL_CATALOG
    from app.mcp_resources import RESOURCE_TOOLS

    schemas = chat_native_schemas()
    names = {s["function"]["name"] for s in schemas}
    expected = {t["name"] for t in CHAT_TOOL_CATALOG} | {
        t["keyword"] for t in RESOURCE_TOOLS
    }
    assert names == expected
    for schema in schemas:
        parameters = schema["function"]["parameters"]
        assert parameters["type"] == "object"
        assert "additionalProperties" in parameters


class DegradingGateway(NativeGateway):
    def stream_events(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Iterator[StreamChunk]:
        native = not any(
            isinstance(m.content, str) and "Emit EXACTLY one tool line" in m.content
            for m in messages
            if m.role == "system"
        )
        if native:
            from app.ai.gateway import ProviderError

            raise ProviderError(
                self.resolve(task),
                "HTTP 400 Error code: 400 - Function tools with reasoning_effort "
                "are not supported for gpt-5.6-luna in /v1/chat/completions",
            )
        return super().stream_events(task, messages, model)


def test_native_tool_unsupported_degrades_to_prompt_grammar(tmp_path: object) -> None:
    from app.ai.chat_models import use_native_tools

    gateway = DegradingGateway(
        [
            "Let me check.\nCALC 2^10\n",
            "It is $1024$. [1]",
        ]
    )
    with make_native_app(tmp_path, gateway) as client:
        _course(client)
        session = _session(client)
        client.post(f"/api/v1/chat/sessions/{session}/messages", json={"content": "hi"})
        messages = wait_for_assistant(client, session)
        assistant = messages[-1]
        assert "1024" in assistant["markdown"]
        assert len(assistant["tool_calls"]) == 1
        call = assistant["tool_calls"][0]
        assert call["name"] == "CALC"
        assert call["argument"] == "2^10"
        assert call["result"] == "1024"
    assert not use_native_tools(gateway.resolve("chat"))


class FailingGateway(NativeGateway):
    def __init__(self) -> None:
        super().__init__([], caps=["text"])

    def stream_events(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Iterator[StreamChunk]:
        from app.ai.gateway import ProviderError

        raise ProviderError(self.resolve(task), "HTTP 500 service unavailable")


def test_pre_stream_failure_persists_no_empty_message_and_fires_turn_error(
    tmp_path: object,
) -> None:
    sys.path.insert(0, "tests")
    from test_chat_api import NoDescriber, NoEmbedder

    from app.core.config import Settings
    from app.main import create_app

    gateway = FailingGateway()
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),  # type: ignore[arg-type]
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    events: list[dict[str, Any]] = []
    original = app.state.bus.publish_threadsafe

    def record(topic: str, payload: dict[str, Any]) -> None:
        if topic.startswith("chat:"):
            events.append(payload)
        original(topic, payload)

    app.state.bus.publish_threadsafe = record
    import time

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        _course(client)
        session = _session(client)
        client.post(f"/api/v1/chat/sessions/{session}/messages", json={"content": "hi"})
        deadline = time.monotonic() + 5.0
        while not any(e["type"] == "turn_error" for e in events):
            assert time.monotonic() < deadline, "no turn_error event"
            time.sleep(0.05)
        messages = client.get(f"/api/v1/chat/sessions/{session}/messages").json()
    assert [m["role"] for m in messages] == ["user"]
    assert any(e["type"] == "turn_error" for e in events)
