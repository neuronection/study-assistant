import json
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar, cast

import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from app.ai.chat_models import build_chat_model
from app.ai.gateway import (
    ImagePart,
    LLMGateway,
    Message,
    ProviderError,
    ResolvedModel,
    TaskUnassigned,
    TextPart,
)

PNG = b"\x89PNG fakebytes"


def make_gateway(
    transport: httpx.BaseTransport, retry_attempts: int = 2, retry_wait: float = 0.01
) -> LLMGateway:
    return LLMGateway(
        session_factory=None,
        transport=transport,
        retry_attempts=retry_attempts,
        retry_wait=retry_wait,
    )


def openai_completion(content: str, usage: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "1",
        "object": "chat.completion",
        "model": "m",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content},
             "finish_reason": "stop"}
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return body


def test_google_adapter_request_shape_and_parse() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "  hello **math** $x^2$ "}]}}
                ]
            },
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="google",
        base_url="https://generativelanguage.googleapis.com",
        external_id="gemini-2.5-flash",
        label="gemini",
        caps=["text", "vision"],
        api_key="KEY",
    )
    text = gateway.generate(
        "ocr",
        [
            Message(role="system", content="be precise"),
            Message(
                role="user",
                content=[TextPart(text="go"), ImagePart(data=PNG, mime="image/png")],
            ),
        ],
        model=model,
    )
    assert text == "hello **math** $x^2$"
    assert captured["url"].startswith(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    )
    assert captured["headers"]["x-goog-api-key"] == "KEY"
    body = captured["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "be precise"
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"text": "go"}
    assert parts[1]["inlineData"]["mimeType"] == "image/png"
    assert parts[1]["inlineData"]["data"] == "iVBORyBmYWtlYnl0ZXM="


def test_openai_adapter_request_shape_and_parse() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "answer text"}}
                ]
            },
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=2,
        provider_type="openai_compatible",
        base_url="http://localhost:11434/v1",
        external_id="qwen2.5vl",
        label="qwen",
        caps=["text", "vision"],
        api_key=None,
    )
    text = gateway.generate(
        "chat", [Message(role="user", content="hi")], model=model
    )
    assert text == "answer text"
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["body"]["model"] == "qwen2.5vl"
    assert captured["auth"] == "Bearer EMPTY"


def test_anthropic_adapter_request_shape_and_parse() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={"content": [{"type": "text", "text": "claude says"}]})

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=3,
        provider_type="anthropic",
        base_url="https://api.anthropic.com",
        external_id="claude-sonnet-4",
        label="claude",
        caps=["text", "vision", "tools"],
        api_key="sk-ant",
    )
    text = gateway.generate(
        "chat", [Message(role="user", content="hi")], model=model
    )
    assert text == "claude says"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["key"] == "sk-ant"
    assert "system" not in captured["body"]


def _migrated_factory(tmp_path: object) -> Any:
    from alembic.config import Config

    from alembic import command

    root = Path(str(tmp_path)) / "gw37"
    root.mkdir(exist_ok=True)
    db_path = root / "gw.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, "head")

    from app.storage.db import make_engine, make_session_factory

    return make_session_factory(make_engine(db_path))


def test_resolve_follows_assignment_and_fallback(tmp_path: object) -> None:
    factory = _migrated_factory(tmp_path)
    from app.domain.models import AiModel, Provider, TaskAssignment

    with factory() as session:
        provider = Provider(
            name="p", type="openai_compatible", base_url="http://x/v1", keyring_ref="provider:1"
        )
        session.add(provider)
        session.flush()
        model = AiModel(
            provider_id=provider.id,
            external_id="m1",
            label="m1",
            caps=["text", "vision"],
            enabled=True,
        )
        session.add(model)
        session.flush()
        session.add(TaskAssignment(task="ocr", model_id=model.id))
        session.commit()
        model_id = model.id

    gateway = LLMGateway(factory)
    resolved = gateway.resolve("ocr")
    assert resolved.external_id == "m1"

    with factory() as session:
        assignment = session.get(TaskAssignment, "ocr")
        assert assignment is not None
        assignment.model_id = None
        assignment.fallback_model_id = model_id
        session.commit()

    resolved = gateway.resolve("ocr")
    assert resolved.external_id == "m1"

    with factory() as session:
        session.delete(session.get(TaskAssignment, "ocr"))
        session.commit()

    with pytest.raises(TaskUnassigned):
        gateway.resolve("ocr")


def test_resolve_falls_back_to_capability_default(tmp_path: object) -> None:
    factory = _migrated_factory(tmp_path)
    from app.domain.models import AiModel, DefaultTaskAssignment, Provider, TaskAssignment

    with factory() as session:
        provider = Provider(
            name="p", type="openai_compatible", base_url="http://x/v1", keyring_ref="provider:1"
        )
        session.add(provider)
        session.flush()
        default_model = AiModel(
            provider_id=provider.id,
            external_id="default-text",
            label="default-text",
            caps=["text"],
            enabled=True,
        )
        session.add(default_model)
        session.flush()
        session.add(
            DefaultTaskAssignment(
                requires="text",
                model_id=default_model.id,
                fallback_model_id=default_model.id,
            )
        )
        session.commit()

    gateway = LLMGateway(factory)
    assert gateway.resolve("chat").external_id == "default-text"

    with factory() as session:
        override = AiModel(
            provider_id=provider.id,
            external_id="override-text",
            label="override-text",
            caps=["text"],
            enabled=True,
        )
        session.add(override)
        session.flush()
        session.add(TaskAssignment(task="chat", model_id=override.id))
        session.commit()

    chain = gateway._resolve_chain("chat", None)
    assert [entry.external_id for entry in chain] == ["override-text", "default-text"]

    with factory() as session:
        session.delete(session.get(TaskAssignment, "chat"))
        session.commit()

    assert gateway.resolve("chat").external_id == "default-text"

    with factory() as session:
        session.delete(session.get(DefaultTaskAssignment, "text"))
        session.commit()

    with pytest.raises(TaskUnassigned):
        gateway.resolve("chat")


def test_provider_http_error_wrapped_with_friendly_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Incorrect API key provided"}},
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="https://api.openai.com/v1",
        external_id="gpt-test",
        label="gpt-test",
        caps=["text"],
        api_key="bad",
    )
    with pytest.raises(ProviderError) as exc_info:
        gateway.generate(
            "chat",
            [Message(role="user", content="hi")],
            model=model,
        )
    message = str(exc_info.value)
    assert "gpt-test" in message
    assert "HTTP 401" in message
    assert "check the API key in Settings" in message


def test_provider_transport_error_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="https://api.openai.com/v1",
        external_id="gpt-test",
        label="gpt-test",
        caps=["text"],
        api_key=None,
    )
    with pytest.raises(ProviderError) as exc_info:
        gateway.generate(
            "chat",
            [Message(role="user", content="hi")],
            model=model,
        )
    assert "ConnectError" in str(exc_info.value)
    assert "check the API key" not in str(exc_info.value)


def test_transient_5xx_is_retried_then_succeeds() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=openai_completion("ok"))

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="m",
        label="m",
        caps=["text"],
        api_key="k",
    )
    output = gateway.generate("chat", [Message(role="user", content="hi")], model=model)
    assert output == "ok"
    assert len(calls) == 2


def test_non_transient_401_is_not_retried() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="m",
        label="m",
        caps=["text"],
        api_key="k",
    )
    with pytest.raises(ProviderError):
        gateway.generate("chat", [Message(role="user", content="hi")], model=model)
    assert len(calls) == 1


def test_fallback_model_answers_and_is_billed(tmp_path: object) -> None:
    factory = _migrated_factory(tmp_path)
    from sqlalchemy import text as sql_text

    from app.domain.models import AiModel, Provider, TaskAssignment

    with factory() as session:
        provider = Provider(
            name="p", type="openai_compatible", base_url="http://x/v1", keyring_ref="provider:1"
        )
        session.add(provider)
        session.flush()
        primary = AiModel(
            provider_id=provider.id, external_id="primary", label="primary",
            caps=["text"], enabled=True,
        )
        fallback = AiModel(
            provider_id=provider.id, external_id="fallback", label="fallback",
            caps=["text"], enabled=True, cost_in=1.0, cost_out=2.0,
        )
        session.add_all([primary, fallback])
        session.flush()
        session.add(
            TaskAssignment(
                task="chat", model_id=primary.id, fallback_model_id=fallback.id
            )
        )
        session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["model"] == "primary":
            return httpx.Response(500, text="down")
        return httpx.Response(200, json=openai_completion("from fallback"))

    gateway = LLMGateway(factory, transport=httpx.MockTransport(handler), retry_wait=0.01)
    output = gateway.generate("chat", [Message(role="user", content="hi")])
    assert output == "from fallback"
    with factory() as session:
        rows = session.execute(
            sql_text(
                "SELECT model, input_tokens, output_tokens FROM ai_interactions "
                "WHERE context_type = 'gateway'"
            )
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "fallback"


def test_mid_stream_failure_keeps_prefix_without_replay() -> None:
    calls: list[httpx.Request] = []

    def content() -> Iterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        raise httpx.ReadError("connection reset mid-stream")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, content=content(), headers={"content-type": "text/event-stream"}
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="m",
        label="m",
        caps=["text"],
        api_key="k",
    )
    received: list[str] = []
    with pytest.raises(ProviderError):
        for chunk in gateway.stream("chat", [Message(role="user", content="hi")], model=model):
            received.append(chunk)
    assert received == ["Hel"]
    assert len(calls) == 1


def test_anthropic_chat_stream_sends_cache_control() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        body = (
            b'event: content_block_delta\n'
            b'data: {"type":"content_block_delta","index":0,'
            b'"delta":{"type":"text_delta","text":"ok"}}\n\n'
            b'event: message_stop\n'
            b'data: {"type":"message_stop"}\n\n'
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=3,
        provider_type="anthropic",
        base_url="https://api.anthropic.com",
        external_id="claude",
        label="claude",
        caps=["text"],
        api_key="k",
    )
    events = list(
        gateway.stream_events(
            "chat",
            [
                Message(role="system", content="invariant prefix"),
                Message(role="user", content="hi"),
            ],
            model=model,
        )
    )
    assert [e.text for e in events] == ["ok"]
    system = captured["body"]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_openai_reasoning_effort_sent_when_set() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=openai_completion("ok"))

    gateway = make_gateway(httpx.MockTransport(handler))
    model = ResolvedModel(
        provider_id=2,
        provider_type="openai_compatible",
        base_url="https://api.openai.com/v1",
        external_id="gpt-5.6-luna",
        label="gpt-5.6-luna",
        caps=["text", "tools"],
        api_key="k",
        reasoning_effort="none",
    )
    output = gateway.generate("chat", [Message(role="user", content="hi")], model=model)
    assert output == "ok"
    assert captured["body"]["reasoning_effort"] == "none"


def test_history_assistant_message_without_tool_calls_streams() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"choices":[{"delta":{"content":"follow-up answer"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    gateway = make_gateway(httpx.MockTransport(handler))
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
        gateway.stream_events(
            "chat",
            [
                Message(role="assistant", content="previous answer"),
                Message(role="user", content="follow up"),
            ],
            model=model,
        )
    )
    assert [e.text for e in events] == ["follow-up answer"]


def test_network_is_blocked_during_suite() -> None:
    with pytest.raises(AssertionError):
        socket.create_connection(("example.com", 443), timeout=0.1)


def test_no_telemetry_env_is_ever_set() -> None:
    import os

    before = dict(os.environ)
    build_chat_model(
        ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="m",
            label="m",
            caps=["text"],
            api_key="k",
        ),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=openai_completion("x"))
        ),
        timeout=30.0,
    )
    new_keys = set(os.environ) - set(before)
    assert not any(
        key.startswith("LANGSMITH_") or key == "LANGCHAIN_TRACING_V2" for key in new_keys
    )


def test_source_never_sets_telemetry_env() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    for path in root.rglob("*.py"):
        source = path.read_text()
        assert "LANGSMITH" not in source, path
        assert "LANGCHAIN_TRACING" not in source, path


def test_google_reasoning_effort_forwarded_when_in_google_set() -> None:
    from app.ai.chat_models import build_chat_model

    model = cast(Any, build_chat_model(
        ResolvedModel(
            provider_id=1,
            provider_type="google",
            base_url="https://generativelanguage.googleapis.com",
            external_id="gemini-2.5-pro",
            label="gemini",
            caps=["text"],
            api_key="k",
            reasoning_effort="high",
        ),
        transport=None,
        timeout=30.0,
    ))
    assert model.reasoning_effort == "high"


def test_google_reasoning_effort_out_of_set_is_dropped() -> None:
    from app.ai.chat_models import build_chat_model

    model = cast(Any, build_chat_model(
        ResolvedModel(
            provider_id=1,
            provider_type="google",
            base_url="https://generativelanguage.googleapis.com",
            external_id="gemini-2.5-pro",
            label="gemini",
            caps=["text"],
            api_key="k",
            reasoning_effort="max",
        ),
        transport=None,
        timeout=30.0,
    ))
    assert model.reasoning_effort is None


def test_anthropic_reasoning_effort_forwarded_when_in_anthropic_set() -> None:
    from app.ai.chat_models import build_chat_model

    model = cast(Any, build_chat_model(
        ResolvedModel(
            provider_id=1,
            provider_type="anthropic",
            base_url="https://api.anthropic.com",
            external_id="claude-sonnet-4-6",
            label="claude",
            caps=["text"],
            api_key="k",
            reasoning_effort="high",
        ),
        transport=None,
        timeout=30.0,
    ))
    assert model.reasoning_effort == "high"


def test_anthropic_reasoning_effort_out_of_set_is_dropped() -> None:
    from app.ai.chat_models import build_chat_model

    model = cast(Any, build_chat_model(
        ResolvedModel(
            provider_id=1,
            provider_type="anthropic",
            base_url="https://api.anthropic.com",
            external_id="claude-sonnet-4-6",
            label="claude",
            caps=["text"],
            api_key="k",
            reasoning_effort="none",
        ),
        transport=None,
        timeout=30.0,
    ))
    assert model.reasoning_effort is None


def test_structured_output_supported_profile_heuristic() -> None:
    from app.ai.chat_models import structured_output_supported

    class NoProfile:
        pass

    class EmptyProfile:
        profile: ClassVar[dict[str, Any]] = {}

    class SupportedProfile:
        profile: ClassVar[dict[str, Any]] = {"structured_output": True}

    class UnsupportedProfile:
        profile: ClassVar[dict[str, Any]] = {"structured_output": False}

    assert structured_output_supported(cast(BaseChatModel, NoProfile())) is True
    assert structured_output_supported(cast(BaseChatModel, EmptyProfile())) is True
    assert structured_output_supported(cast(BaseChatModel, SupportedProfile())) is True
    assert structured_output_supported(cast(BaseChatModel, UnsupportedProfile())) is False


def test_gateway_structured_skips_profile_unsupported_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai import gateway as gateway_module
    from app.ai.structured import QuizgenOut

    calls: list[str] = []

    class StubModel:
        profile: ClassVar[dict[str, Any]] = {"structured_output": False}

        def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
            calls.append("with_structured_output")
            raise AssertionError("pre-gate should have skipped the structured call")

    def fake_build(resolved: ResolvedModel, transport: Any, timeout: float) -> Any:
        calls.append("build")
        return StubModel()

    monkeypatch.setattr(gateway_module, "build_chat_model", fake_build)
    gateway = make_gateway(httpx.MockTransport(lambda request: httpx.Response(500)))
    monkeypatch.setattr(
        gateway,
        "_resolve_chain",
        lambda task, model, course_id=None: [
            ResolvedModel(
                provider_id=1,
                provider_type="openai_compatible",
                base_url="http://localhost/v1",
                external_id="m",
                label="m",
                caps=["text", "tools"],
                api_key="k",
            )
        ],
    )
    result = gateway.generate_structured("chat", [Message(role="user", content="hi")], QuizgenOut)
    assert result is None
    assert calls == ["build"]


def test_structured_generation_bills_real_usage(tmp_path: object) -> None:
    from sqlalchemy import text as sql_text

    from app.ai.structured import QuizgenOut
    from app.domain.models import AiModel, Provider, TaskAssignment

    quizgen_json = {
        "questions": [
            {
                "type": "single",
                "stem_md": "What is 2+2?",
                "options_md": ["3", "4"],
                "answer": {"index": 1},
                "explanation_md": "Basic addition.",
                "concepts": ["arithmetic"],
                "skill": "compute",
            }
        ]
    }
    factory = _migrated_factory(tmp_path)
    with factory() as session:
        provider = Provider(
            name="p", type="openai_compatible", base_url="http://x/v1", keyring_ref="provider:1"
        )
        session.add(provider)
        session.flush()
        model = AiModel(
            provider_id=provider.id, external_id="m", label="m",
            caps=["text", "tools"], enabled=True,
        )
        session.add(model)
        session.flush()
        session.add(TaskAssignment(task="quizgen", model_id=model.id))
        session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=openai_completion(
                json.dumps(quizgen_json),
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            ),
        )

    gateway = LLMGateway(factory, transport=httpx.MockTransport(handler))
    result = gateway.generate_structured(
        "quizgen", [Message(role="user", content="hi")], QuizgenOut
    )
    assert result is not None
    assert result["questions"][0]["stem_md"] == "What is 2+2?"
    with factory() as session:
        rows = session.execute(
            sql_text(
                "SELECT input_tokens, output_tokens, task FROM ai_interactions "
                "WHERE context_type = 'gateway'"
            )
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 10
    assert rows[0][1] == 5
    assert rows[0][2] == "quizgen"


def test_structured_generation_parsed_none_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai import gateway as gateway_module
    from app.ai.structured import QuizgenOut

    calls: list[tuple[str, bool]] = []

    class StubRunnable:
        def invoke(self, messages: Any, **kwargs: Any) -> dict[str, Any]:
            return {"raw": None, "parsed": None, "parsing_error": RuntimeError("nope")}

    class StubModel:
        profile: ClassVar[dict[str, Any]] = {"structured_output": True}

        def with_structured_output(self, schema: Any, **kwargs: Any) -> StubRunnable:
            calls.append(("with_structured_output", bool(kwargs.get("include_raw"))))
            return StubRunnable()

    def fake_build(resolved: ResolvedModel, transport: Any, timeout: float) -> Any:
        return StubModel()

    monkeypatch.setattr(gateway_module, "build_chat_model", fake_build)
    gateway = make_gateway(httpx.MockTransport(lambda request: httpx.Response(500)))
    monkeypatch.setattr(
        gateway,
        "_resolve_chain",
        lambda task, model, course_id=None: [
            ResolvedModel(
                provider_id=1,
                provider_type="openai_compatible",
                base_url="http://localhost/v1",
                external_id="m",
                label="m",
                caps=["text", "tools"],
                api_key="k",
            )
        ],
    )
    result = gateway.generate_structured("chat", [Message(role="user", content="hi")], QuizgenOut)
    assert result is None
    assert calls == [("with_structured_output", True)]


def test_embedder_records_embeddings_in_ledger(tmp_path: object) -> None:
    from sqlalchemy import select

    from app.ai.embeddings import GatewayEmbedder
    from app.domain.models import AiInteraction, AiModel, DefaultTaskAssignment, Provider

    factory = _migrated_factory(tmp_path)
    with factory() as session:
        provider = Provider(
            name="p", type="openai_compatible", base_url="http://x/v1", keyring_ref="provider:1"
        )
        session.add(provider)
        session.flush()
        model = AiModel(
            provider_id=provider.id,
            external_id="nomic",
            label="nomic",
            caps=["embeddings"],
            enabled=True,
        )
        session.add(model)
        session.flush()
        session.add(
            DefaultTaskAssignment(requires="embeddings", model_id=model.id, fallback_model_id=None)
        )
        session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/embeddings")
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    gateway = LLMGateway(factory, transport=httpx.MockTransport(handler))
    result = GatewayEmbedder(gateway).embed(["derivative chain rule"])
    assert result is not None
    assert result[0] == "nomic"
    assert result[1] == [[0.1, 0.2]]

    with factory() as session:
        row = session.scalars(
            select(AiInteraction).where(AiInteraction.task == "embeddings")
        ).one()
        assert row.model == "nomic"
        assert row.input_tokens > 0
        assert row.latency_ms >= 0
