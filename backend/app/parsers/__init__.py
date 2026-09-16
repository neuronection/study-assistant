"""URL parser registry: deterministic fetch+convert, never user code (ADR-165)."""

from .base import (
    DOWNLOADABLE_SUFFIXES,
    ParsedDocument,
    ParserError,
    URLParser,
    build_registry,
    resolve_parser,
)

__all__ = [
    "DOWNLOADABLE_SUFFIXES",
    "ParsedDocument",
    "ParserError",
    "URLParser",
    "build_registry",
    "resolve_parser",
]
