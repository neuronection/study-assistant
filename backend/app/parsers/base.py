"""URL parser registry: deterministic fetch+convert, never user code (ADR-165)."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..services.content.materials import (
    AV_SUFFIXES,
    CONVERTIBLE_SUFFIXES,
    KIND_BY_SUFFIX,
)


class ParserError(ValueError):
    pass


@dataclass
class ParsedDocument:
    title: str = ""
    markdown: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    kind_hint: str | None = None
    blob: bytes | None = None
    mime: str | None = None


class URLParser(Protocol):
    def matches(self, url: str) -> bool: ...

    def fetch(self, url: str) -> ParsedDocument: ...


DOWNLOADABLE_SUFFIXES: dict[str, str] = {
    **KIND_BY_SUFFIX,
    **CONVERTIBLE_SUFFIXES,
    **AV_SUFFIXES,
}


def build_registry(
    transport: Any = None,
    language: str | None = None,
    session: Any = None,
    profile_id: int | None = None,
) -> list[URLParser]:
    from .direct_file import DirectFileParser
    from .html import HtmlParser
    from .youtube import YouTubeParser

    registry: list[URLParser] = []
    if session is not None and profile_id is not None:
        from .mcp_parse import build_mcp_parsers

        registry.extend(build_mcp_parsers(session, profile_id))
    registry.extend(
        [
            YouTubeParser(language=language),
            DirectFileParser(transport=transport),
            HtmlParser(transport=transport),
        ]
    )
    return registry


def resolve_parser(registry: list[URLParser], url: str) -> URLParser | None:
    for parser in registry:
        if parser.matches(url):
            return parser
    return None
