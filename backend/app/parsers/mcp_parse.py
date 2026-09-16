"""MCP parse-contract connector (plan 73-G, ADR-170): a user-registered
external MCP tool takes `{url}` and returns `{title, markdown, metadata?}`.
Keyed by a user-declared URL pattern (e.g. `coursera.org/learn/*`); executed
by the url_import job like any built-in parser. Contract violations fail
honestly — external output is untrusted input (family-ai trust boundary).
"""

import json
import time
from fnmatch import fnmatch
from typing import Any
from urllib.parse import urlparse

from ..ai.mcp_client import (
    McpToolError,
    audit_mcp_invocation,
    call_tool_sync,
)
from .base import ParsedDocument, ParserError


class McpParseParser:
    def __init__(
        self,
        server: dict[str, Any],
        tool: dict[str, Any],
        audit: Any = None,
    ) -> None:
        from ..services.platform.mcp_servers import build_mcp_config

        tool_name = str(tool.get("name"))
        self.id = f"mcp.{server.get('name')}.{tool_name}"
        self._tool_name = tool_name
        self._pattern = str(tool.get("url_pattern") or "").strip()
        self._config = build_mcp_config(server)
        self._audit_session = audit

    def matches(self, url: str) -> bool:
        if not self._pattern:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False
        return fnmatch(f"{parsed.netloc.lower()}{parsed.path}", self._pattern)

    def fetch(self, url: str) -> ParsedDocument:
        started = time.monotonic()
        try:
            text = call_tool_sync(self._config, self._tool_name, {"url": url})
        except McpToolError as error:
            self._audit(ok=False, started=started, error=str(error))
            raise ParserError(str(error)) from None
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as error:
            self._audit(
                ok=False,
                started=started,
                error=f"non-JSON output from '{self._tool_name}'",
            )
            raise ParserError(
                f"MCP tool '{self._tool_name}' returned non-JSON output"
            ) from error
        if not isinstance(data, dict):
            self._audit(
                ok=False, started=started, error="parse contract violation"
            )
            raise ParserError(
                f"MCP tool '{self._tool_name}' must return an object with "
                "title and markdown"
            )
        markdown = data.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            self._audit(
                ok=False, started=started, error="parse returned no markdown"
            )
            raise ParserError(
                f"MCP tool '{self._tool_name}' returned no markdown"
            )
        self._audit(ok=True, started=started)
        title = str(data.get("title") or "").strip()
        metadata_raw = data.get("metadata")
        metadata: dict[str, Any] = {"mcp_tool": self.id}
        if isinstance(metadata_raw, dict):
            metadata.update(metadata_raw)
        return ParsedDocument(
            title=title[:300],
            markdown=markdown,
            metadata=metadata,
        )

    def _audit(
        self, *, ok: bool, started: float, error: str | None = None
    ) -> None:
        if self._audit_session is None:
            return
        audit_mcp_invocation(
            self._audit_session,
            tool_ref=self.id,
            latency_ms=int((time.monotonic() - started) * 1000),
            ok=ok,
            error=error,
        )


def build_mcp_parsers(session: Any, profile_id: int) -> list[McpParseParser]:
    """All enabled parse-contract tools across enabled servers, ordered."""
    from ..services.platform.mcp_servers import enabled_tools

    return [
        McpParseParser(server, tool, audit=session)
        for server, tool in enabled_tools(session, profile_id, "parse")
    ]
