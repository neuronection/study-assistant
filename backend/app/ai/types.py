from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    data: bytes
    mime: str


Part = TextPart | ImagePart


@dataclass(frozen=True)
class StreamChunk:
    kind: str
    text: str


@dataclass(frozen=True)
class Message:
    role: str
    content: str | list[Part]
    tool_calls: tuple[dict[str, Any], ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ResolvedModel:
    provider_id: int
    provider_type: str
    base_url: str
    external_id: str
    label: str
    caps: list[str]
    api_key: str | None
    cost_in: float | None = None
    cost_out: float | None = None
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class Usage:
    tokens_in: int
    tokens_out: int
    cache_read: int = 0


class UsageHolder:
    def __init__(self) -> None:
        self.usage: Usage | None = None
