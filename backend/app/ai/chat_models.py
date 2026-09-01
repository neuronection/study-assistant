from __future__ import annotations

import base64
from collections.abc import Iterator
from typing import Any

import httpx
from anthropic import Anthropic as AnthropicClient
from google.genai import types as google_types
from google.genai.client import Client as GoogleClient
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .types import ImagePart, Message, ResolvedModel, TextPart, Usage

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com"
_KEYLESS_API_KEY = "EMPTY"
_ANTHROPIC_REASONING_EFFORT_LEVELS = frozenset({"max", "xhigh", "high", "medium", "low"})
_GOOGLE_REASONING_EFFORT_LEVELS = frozenset({"minimal", "low", "medium", "high"})
_NATIVE_TOOLS_DEGRADED: set[tuple[int, str]] = set()


def degrade_native_tools(resolved: ResolvedModel) -> None:
    _NATIVE_TOOLS_DEGRADED.add((resolved.provider_id, resolved.external_id))


def use_native_tools(resolved: ResolvedModel) -> bool:
    return "tools" in resolved.caps and (
        (resolved.provider_id, resolved.external_id) not in _NATIVE_TOOLS_DEGRADED
    )


def structured_output_supported(model: BaseChatModel) -> bool:
    profile = getattr(model, "profile", None)
    return not (isinstance(profile, dict) and profile.get("structured_output") is False)


def chat_native_schemas() -> list[dict[Any, Any]]:
    from ..mcp_resources import resource_native_schemas
    from .tools import CHAT_TOOL_CATALOG, native_tool_schemas

    return [*native_tool_schemas(CHAT_TOOL_CATALOG), *resource_native_schemas()]


class CaChatOpenAI(ChatOpenAI):
    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[Any, Any],
        default_chunk_class: type,
        base_generation_info: dict[Any, Any] | None,
    ) -> ChatGenerationChunk | None:
        generation = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation is None:
            return None
        choices = chunk.get("choices") or []
        delta = choices[0].get("delta") if choices else None
        reasoning = None
        if isinstance(delta, dict):
            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if reasoning and generation.message is not None:
            generation.message.additional_kwargs["reasoning_content"] = reasoning
        return generation


def _content_blocks(content: list[TextPart | ImagePart]) -> list[str | dict[Any, Any]]:
    blocks: list[str | dict[Any, Any]] = []
    for part in content:
        if isinstance(part, TextPart):
            blocks.append({"type": "text", "text": part.text})
        else:
            b64 = base64.b64encode(part.data).decode()
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{part.mime};base64,{b64}"},
                }
            )
    return blocks


def to_langchain_messages(
    messages: list[Message], cache_prefix: bool = False
) -> list[BaseMessage]:
    mapped: list[BaseMessage] = []
    for index, message in enumerate(messages):
        content: str | list[str | dict[Any, Any]] = (
            message.content
            if isinstance(message.content, str)
            else _content_blocks(message.content)
        )
        if message.role == "system":
            if cache_prefix and index == 0 and isinstance(content, str):
                content = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            mapped.append(SystemMessage(content=content))
        elif message.role == "assistant":
            kwargs: dict[str, Any] = {"content": content}
            if message.tool_calls:
                kwargs["tool_calls"] = list(message.tool_calls)
            if message.tool_call_id is not None:
                kwargs["id"] = message.tool_call_id
            mapped.append(AIMessage(**kwargs))
        elif message.role == "tool":
            mapped.append(
                ToolMessage(
                    content=message.content if isinstance(message.content, str) else "",
                    tool_call_id=message.tool_call_id or "",
                )
            )
        else:
            mapped.append(HumanMessage(content=content))
    return mapped


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            value = block.get("text")
            if isinstance(value, str):
                parts.append(value)
    return "".join(parts)


def reasoning_from_message(message: AIMessage) -> str:
    parts: list[str] = []
    reasoning = message.additional_kwargs.get("reasoning_content")
    if isinstance(reasoning, str):
        parts.append(reasoning)
    content = message.content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                value = block.get("thinking")
                if isinstance(value, str):
                    parts.append(value)
    return "".join(parts)


def usage_from_message(message: AIMessage) -> Usage | None:
    meta = message.usage_metadata
    if meta is None:
        return None
    details = meta.get("input_token_details") or {}
    return Usage(
        tokens_in=meta.get("input_tokens") or 0,
        tokens_out=meta.get("output_tokens") or 0,
        cache_read=details.get("cache_read") or 0,
    )


def _http_client(transport: httpx.BaseTransport, timeout: float) -> httpx.Client:
    return httpx.Client(transport=transport, timeout=timeout, follow_redirects=True)


def _openai_model(
    resolved: ResolvedModel, transport: httpx.BaseTransport | None, timeout: float
) -> CaChatOpenAI:
    kwargs: dict[str, Any] = {
        "model": resolved.external_id,
        "api_key": resolved.api_key or _KEYLESS_API_KEY,
        "temperature": None,
        "max_retries": 0,
        "timeout": timeout,
    }
    if resolved.reasoning_effort:
        kwargs["reasoning_effort"] = resolved.reasoning_effort
    if resolved.temperature is not None:
        kwargs["temperature"] = resolved.temperature
    if resolved.max_tokens is not None:
        kwargs["max_tokens"] = resolved.max_tokens
    if resolved.base_url:
        kwargs["base_url"] = resolved.base_url
    if transport is not None:
        kwargs["http_client"] = _http_client(transport, timeout)
    return CaChatOpenAI(**kwargs)


def _anthropic_model(
    resolved: ResolvedModel, transport: httpx.BaseTransport | None, timeout: float
) -> ChatAnthropic:
    api_key = resolved.api_key or _KEYLESS_API_KEY
    base_url = resolved.base_url or ANTHROPIC_BASE_URL
    kwargs: dict[str, Any] = {
        "model": resolved.external_id,
        "api_key": SecretStr(api_key),
        "anthropic_api_url": base_url,
        "max_tokens": 8192,
        "temperature": None,
        "max_retries": 0,
        "default_request_timeout": timeout,
    }
    if resolved.reasoning_effort in _ANTHROPIC_REASONING_EFFORT_LEVELS:
        kwargs["reasoning_effort"] = resolved.reasoning_effort
    if resolved.temperature is not None:
        kwargs["temperature"] = resolved.temperature
    if resolved.max_tokens is not None:
        kwargs["max_tokens"] = resolved.max_tokens
    model = ChatAnthropic(**kwargs)
    if transport is not None:
        model._client = AnthropicClient(
            api_key=api_key,
            base_url=base_url,
            max_retries=0,
            timeout=timeout,
            http_client=_http_client(transport, timeout),
        )
    return model


def _google_model(
    resolved: ResolvedModel, transport: httpx.BaseTransport | None, timeout: float
) -> ChatGoogleGenerativeAI:
    api_key = resolved.api_key or _KEYLESS_API_KEY
    base_url = resolved.base_url or GOOGLE_BASE_URL
    kwargs: dict[str, Any] = {
        "model": resolved.external_id,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": None,
    }
    if resolved.reasoning_effort in _GOOGLE_REASONING_EFFORT_LEVELS:
        kwargs["reasoning_effort"] = resolved.reasoning_effort
    if resolved.temperature is not None:
        kwargs["temperature"] = resolved.temperature
    if resolved.max_tokens is not None:
        kwargs["max_tokens"] = resolved.max_tokens
    model = ChatGoogleGenerativeAI(**kwargs)
    if transport is not None:
        model.client = GoogleClient(
            api_key=api_key,
            http_options=google_types.HttpOptions(
                base_url=base_url,
                timeout=int(timeout),
                retry_options=google_types.HttpRetryOptions(attempts=1),
                httpx_client=_http_client(transport, timeout),
            ),
        )
    return model


def build_chat_model(
    resolved: ResolvedModel,
    transport: httpx.BaseTransport | None,
    timeout: float,
) -> BaseChatModel:
    if resolved.provider_type == "openai_compatible":
        return _openai_model(resolved, transport, timeout)
    if resolved.provider_type == "anthropic":
        return _anthropic_model(resolved, transport, timeout)
    if resolved.provider_type == "google":
        return _google_model(resolved, transport, timeout)
    raise ValueError(f"unknown provider type '{resolved.provider_type}'")


def stream_message_chunks(
    model: Runnable[Any, AIMessage], messages: list[BaseMessage]
) -> Iterator[AIMessage]:
    for chunk in model.stream(messages):
        if isinstance(chunk, AIMessage):
            yield chunk
