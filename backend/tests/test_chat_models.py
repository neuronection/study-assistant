"""Wire-parameter routing of the chat-model factory (ADR-0038).

Modern OpenAI models reject ``max_tokens`` ("use max_completion_tokens
instead") while OpenAI-compatible endpoints reject the newer name. The
factory routes by endpoint — never by model id, which prefixes, chat
variants, and future families make unreliable.
"""

import httpx

from langchain_openai import ChatOpenAI

from app.ai.chat_models import (
    CompatibleCaChatOpenAI,
    CompatibleChatOpenAI,
    CaChatOpenAI,
    build_chat_model,
    is_openai_endpoint,
    is_openai_wire,
)
from app.ai.types import ResolvedModel
from app.ai.wire_params import resolve_chat_transport


def _resolved(
    provider_type: str = "openai_compatible",
    *,
    base_url: str = "http://localhost:8080/v1",
    max_tokens: int | None = None,
    chat_transport: str | None = None,
) -> ResolvedModel:
    return ResolvedModel(
        provider_id=1,
        provider_type=provider_type,
        base_url=base_url,
        external_id="gpt-5-chat-latest",
        label="test",
        caps=["text"],
        api_key=None,
        max_tokens=max_tokens,
        chat_transport=chat_transport,
    )


def _build(resolved: ResolvedModel):
    return build_chat_model(
        resolved, transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})), timeout=5.0
    )


def test_is_openai_endpoint() -> None:
    assert is_openai_endpoint("https://api.openai.com/v1")
    assert not is_openai_endpoint("http://localhost:11434/v1")
    assert not is_openai_endpoint("")
    assert not is_openai_endpoint(None)


def test_is_openai_wire() -> None:
    assert is_openai_wire("openai", None)
    assert is_openai_wire("openai_compatible", "https://api.openai.com/v1")
    assert not is_openai_wire("openai_compatible", "http://localhost:8080/v1")


def test_openai_endpoint_cap_uses_modern_parameter() -> None:
    model = _build(_resolved(base_url="https://api.openai.com/v1", max_tokens=512))
    assert isinstance(model, ChatOpenAI)
    assert not isinstance(model, CompatibleChatOpenAI)
    assert model._default_params["max_completion_tokens"] == 512
    assert "max_tokens" not in model._default_params


def test_compatible_endpoint_cap_keeps_classic_parameter() -> None:
    model = _build(_resolved(max_tokens=512))
    assert isinstance(model, CompatibleCaChatOpenAI)
    assert model._default_params["max_tokens"] == 512
    assert "max_completion_tokens" not in model._default_params


def test_compatible_class_keeps_reasoning_delta_support() -> None:
    """The compatible subclass must not drop CaChatOpenAI's delta handling."""
    model = _build(_resolved(max_tokens=512))
    assert type(model)._convert_chunk_to_generation_chunk is CaChatOpenAI._convert_chunk_to_generation_chunk


def test_compatible_without_cap_sends_neither_parameter() -> None:
    model = _build(_resolved())
    assert "max_tokens" not in model._default_params
    assert "max_completion_tokens" not in model._default_params


def test_responses_transport_on_the_openai_endpoint() -> None:
    """ADR-0039: a row opted into responses rides /responses store-less —
    reasoning_effort (passed through) + function tools keep working on
    gpt-6-family models."""
    model = _build(
        _resolved(base_url="https://api.openai.com/v1", max_tokens=512, chat_transport="responses")
    )
    assert isinstance(model, ChatOpenAI)
    assert model.use_responses_api is True
    assert model.store is False


def test_responses_transport_ignored_off_the_openai_endpoint() -> None:
    model = _build(_resolved(max_tokens=512, chat_transport="responses"))
    assert isinstance(model, CompatibleCaChatOpenAI)
    assert getattr(model, "use_responses_api", None) is not True


def test_chat_transport_resolution_matrix() -> None:
    assert resolve_chat_transport("openai", "https://api.openai.com/v1", "responses") == "responses"
    assert resolve_chat_transport("openai", None, "responses") == "responses"
    assert resolve_chat_transport("openai_compatible", "http://localhost:8080/v1", "responses") == "completions"
    assert resolve_chat_transport("openai", "https://api.openai.com/v1", None) == "completions"
    assert resolve_chat_transport("openai", "https://api.openai.com/v1", "completions") == "completions"
