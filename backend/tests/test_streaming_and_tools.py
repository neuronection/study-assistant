import httpx
import pytest

from app.ai.gateway import LLMGateway, Message, ProviderError, ResolvedModel
from app.ai.tools import calculate, extract_tool_calls, run_tool_line, strip_tool_lines
from app.services.chat import _tool_result_summary


def make_stream_gateway(transport: httpx.BaseTransport) -> LLMGateway:
    return LLMGateway(session_factory=None, transport=transport)





def test_openai_streaming_yields_deltas() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = b"".join(
            [
                b'data: {"choices":[{"delta":{"content":"Hello "}}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"wor"}}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"ld"}}]}\n\n',
                b"data: [DONE]\n\n",
            ]
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    gateway = make_stream_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="m",
        label="m",
        caps=["text"],
        api_key=None,
    )
    deltas = list(gateway.stream("chat", [Message(role="user", content="hi")], model=model))
    assert deltas == ["Hello ", "wor", "ld"]


def test_anthropic_streaming_yields_deltas() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            b'event: content_block_delta\n'
            b'data: {"type":"content_block_delta","index":0,'
            b'"delta":{"type":"text_delta","text":"sin"}}\n\n'
            b'event: content_block_delta\n'
            b'data: {"type":"content_block_delta","index":0,'
            b'"delta":{"type":"text_delta","text":"(x)"}}\n\n'
            b'event: message_stop\n'
            b'data: {"type":"message_stop"}\n\n'
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    gateway = make_stream_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=2,
        provider_type="anthropic",
        base_url="https://api.anthropic.com",
        external_id="claude",
        label="claude",
        caps=["text"],
        api_key="k",
    )
    deltas = list(gateway.stream("chat", [Message(role="user", content="hi")], model=model))
    assert deltas == ["sin", "(x)"]


def test_google_streaming_yields_deltas() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = b"".join(
            [
                b'data: {"candidates":[{"content":{"parts":[{"text":"2x + "}]}}]}\n\n',
                b'data: {"candidates":[{"content":{"parts":[{"text":"C"}]}}]}\n\n',
            ]
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    gateway = make_stream_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=3,
        provider_type="google",
        base_url="https://generativelanguage.googleapis.com",
        external_id="gemini-2.5-flash",
        label="gemini",
        caps=["text"],
        api_key="k",
    )
    deltas = list(gateway.stream("chat", [Message(role="user", content="hi")], model=model))
    assert deltas == ["2x + ", "C"]


def test_stream_events_yields_reasoning_and_stream_drops_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = b"".join(
            [
                b'data: {"choices":[{"delta":{"reasoning_content":"hmm"}}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
                b"data: [DONE]\n\n",
            ]
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    gateway = make_stream_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="m",
        label="m",
        caps=["text"],
        api_key=None,
    )
    events = list(
        gateway.stream_events("chat", [Message(role="user", content="hi")], model=model)
    )
    assert [(event.kind, event.text) for event in events] == [
        ("reasoning", "hmm"),
        ("text", "answer"),
    ]
    deltas = list(gateway.stream("chat", [Message(role="user", content="hi")], model=model))
    assert deltas == ["answer"]


def test_anthropic_stream_events_yield_reasoning() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            b'event: content_block_delta\n'
            b'data: {"type":"content_block_delta","index":0,'
            b'"delta":{"type":"thinking_delta","thinking":"pondering"}}\n\n'
            b'event: content_block_delta\n'
            b'data: {"type":"content_block_delta","index":0,'
            b'"delta":{"type":"text_delta","text":"answer"}}\n\n'
            b'event: message_stop\n'
            b'data: {"type":"message_stop"}\n\n'
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    gateway = make_stream_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=2,
        provider_type="anthropic",
        base_url="https://api.anthropic.com",
        external_id="claude",
        label="claude",
        caps=["text"],
        api_key="k",
    )
    events = list(
        gateway.stream_events("chat", [Message(role="user", content="hi")], model=model)
    )
    assert [(event.kind, event.text) for event in events] == [
        ("reasoning", "pondering"),
        ("text", "answer"),
    ]


def test_google_stream_events_yield_reasoning() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"candidates":[{"content":{"parts":[{"text":"musing","thought":true}]}}]}\n\n'
            b'data: {"candidates":[{"content":{"parts":[{"text":"answer"}]}}]}\n\n'
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    gateway = make_stream_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=3,
        provider_type="google",
        base_url="https://generativelanguage.googleapis.com",
        external_id="gemini-2.5-flash",
        label="gemini",
        caps=["text"],
        api_key="k",
    )
    events = list(
        gateway.stream_events("chat", [Message(role="user", content="hi")], model=model)
    )
    assert [(event.kind, event.text) for event in events] == [
        ("reasoning", "musing"),
        ("text", "answer"),
    ]


def test_calculate_rejects_dangerous_input() -> None:
    assert calculate("2+2").rstrip("0").rstrip(".") in {"4", "4.0"}
    assert calculate("__import__('os')").startswith("error")
    assert calculate("open('/etc/passwd')").startswith("error")
    assert calculate("sin(pi/2)").startswith("1")
    assert calculate("1/0").startswith("error")


def test_sympy_actions() -> None:
    assert run_tool_line("SYMPY", "diff x**2") == "2*x"
    assert run_tool_line("SYMPY", "integrate 2*x") == "x**2"
    assert run_tool_line("SYMPY", "solve x**2 - 4") == "[-2, 2]"
    assert run_tool_line("SYMPY", "simplify sin(x)**2 + cos(x)**2") == "1"
    assert run_tool_line("SYMPY", "factor x**2 - 1") == "(x - 1)*(x + 1)"
    assert run_tool_line("SYMPY", "bogus x") .startswith("error")
    assert run_tool_line("SYMPY", "diff not an expression!") .startswith("error")


def test_extract_and_strip_tool_lines() -> None:
    text = "Let me verify.\nCALC 2^10\nSYMPY diff sin(x)\nDone."
    calls = extract_tool_calls(text)
    assert calls == [("CALC", "2^10"), ("SYMPY", "diff sin(x)")]
    stripped = strip_tool_lines(text)
    assert "CALC" not in stripped and "SYMPY" not in stripped
    assert stripped.startswith("Let me verify.") and stripped.endswith("Done.")
    assert extract_tool_calls("plain answer") == []


def test_extract_resource_tool_lines() -> None:
    text = "COURSES\nNODE_OVERVIEW T2\nNODE_NOTES here\nLet me see."
    calls = extract_tool_calls(text)
    assert calls == [
        ("COURSES", ""),
        ("NODE_OVERVIEW", "T2"),
        ("NODE_NOTES", "here"),
    ]
    stripped = strip_tool_lines(text)
    assert stripped == "Let me see."


def test_resource_tool_keywords_match_registry() -> None:
    from app.ai.tools import RESOURCE_TOOL_KEYWORDS
    from app.mcp_resources import RESOURCE_TOOLS

    assert set(RESOURCE_TOOL_KEYWORDS) == {tool["keyword"] for tool in RESOURCE_TOOLS}


def test_tool_result_summary_guards_content() -> None:
    assert _tool_result_summary("CALC", "0.5") == "0.5"
    assert _tool_result_summary("SYMPY", "2*x") == "2*x"
    assert _tool_result_summary("PLOT", '{"data": []}') == "chart data"
    assert _tool_result_summary("READ", "a" * 4000) == "read 4000 chars"
    assert _tool_result_summary("STATE", '{"checked": true}') is None


def test_chat_tool_round_flow(tmp_path: object) -> None:
    import sys

    sys.path.insert(0, "tests")

    from fastapi.testclient import TestClient
    from test_chat_api import (
        NoDescriber,
        NoEmbedder,
        ScriptedGateway,
        add_material,
        wait_for_assistant,
    )

    from app.core.config import Settings
    from app.main import create_app

    gateway = ScriptedGateway(
        [
            "Checking.\nSYMPY diff x**3\n",
            "The derivative is $3x^2$ per the rules [1].",
        ]
    )
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),  # type: ignore[arg-type]
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        course = client.post("/api/v1/courses", json={"title": "Tools"}).json()
        add_material(
            client,
            "deriv.txt",
            "Power rule for derivatives of polynomials.",
            course["id"],
        )
        session = client.post("/api/v1/chat/sessions", json={}).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages", json={"content": "derivative of x^3"}
        )
        messages = wait_for_assistant(client, session["id"])
        assistant = messages[-1]
        assert "3x^2" in assistant["markdown"]
        assert "SYMPY" not in assistant["markdown"]
        assert len(assistant["tool_calls"]) == 1
        call = assistant["tool_calls"][0]
        assert call["name"] == "SYMPY"
        assert call["argument"] == "diff x**3"
        assert call["phase"] == "math"
        assert call["result"] == "3*x**2"
        assert call["title"] is None
        assert call["status"] == "done"
        assert isinstance(call["start_ms"], int)
        assert isinstance(call["duration_ms"], int)
        trace = assistant["trace"]
        assert trace["run_id"]
        assert trace["model"] == "fake-chat"
        assert trace["latency_ms"] >= 0
        assert len(trace["rounds"]) == 2
        assert trace["rounds"][0]["streamed"] is True
        assert trace["rounds"][0]["phase"] == "thinking"
        assert trace["rounds"][1]["streamed"] is True
        assert len(gateway.calls) == 2
        second_prompt = " ".join(
            m.content if isinstance(m.content, str) else "" for m in gateway.calls[1]
        )
        assert "diff x**3 -> 3*x**2" in second_prompt


def test_stream_http_error_reports_status_not_response_not_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            headers={"content-type": "application/json"},
            content=iter([b'{"error":{"message":"Incorrect API key provided"}}']),
        )

    gateway = make_stream_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="m",
        label="gpt",
        caps=["text"],
        api_key="wrong",
    )
    with pytest.raises(ProviderError) as excinfo:
        list(gateway.stream("chat", [Message(role="user", content="hi")], model=model))
    message = str(excinfo.value)
    assert "HTTP 401" in message
    assert "Incorrect API key provided" in message
    assert "check the API key in Settings" in message
    assert "without having called" not in message


def test_stream_http_error_without_readable_body_still_reports_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            content=iter([b""]),
        )

    gateway = make_stream_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="m",
        label="gpt",
        caps=["text"],
        api_key=None,
    )
    with pytest.raises(ProviderError) as excinfo:
        list(gateway.stream("chat", [Message(role="user", content="hi")], model=model))
    assert "HTTP 503" in str(excinfo.value)
    assert "without having called" not in str(excinfo.value)
