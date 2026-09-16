"""MCP client bridge (plan 73-G, ADR-170): deterministic service invocation
of user-registered external MCP servers over stdio.

Servers are launched lazily per invocation and reaped when the call ends —
no permanent subprocess fleet. External tool output is untrusted input
(family-ai trust boundary): every consumer validates shapes app-side. The
`mcp` SDK import lives ONLY here (+ tests), matching this repo's existing
`mcp`-SDK server precedent (`app/mcp_resources.py`).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from ..domain.models import AiInteraction

logger = structlog.get_logger(__name__)

DEFAULT_TOOL_TIMEOUT_SEC = 30
SERVER_ID_LEN = 12
MAX_SERVERS = 10


class McpToolError(RuntimeError):
    pass


@dataclass
class McpServerConfig:
    id: str
    name: str
    command: str
    args: list[str]
    enabled: bool
    timeout_sec: int
    tools: list[dict[str, Any]]
    last_error: str | None
    refreshed_at: str | None


def new_server_id() -> str:
    return uuid.uuid4().hex[:SERVER_ID_LEN]


def new_server_config(
    name: str, command: str, args: list[str], timeout_sec: int = DEFAULT_TOOL_TIMEOUT_SEC
) -> dict[str, Any]:
    return {
        "id": new_server_id(),
        "name": name,
        "command": command,
        "args": args,
        "enabled": False,
        "timeout_sec": timeout_sec,
        "tools": [],
        "last_error": None,
        "refreshed_at": None,
    }


async def _run_tool_call(
    command: str,
    args: list[str],
    tool_name: str,
    arguments: dict[str, Any],
    timeout_sec: float,
) -> str:
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=get_default_environment(),
    )
    with anyio.fail_after(timeout_sec):
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
    texts = [
        str(block.text)
        for block in result.content
        if getattr(block, "type", None) == "text" and hasattr(block, "text")
    ]
    if not texts:
        raise McpToolError(f"tool '{tool_name}' returned no text content")
    return "\n".join(texts)


async def _run_list_tools(
    command: str, args: list[str], timeout_sec: float
) -> list[dict[str, Any]]:
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=get_default_environment(),
    )
    with anyio.fail_after(timeout_sec):
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
    return [
        {
            "name": tool.name,
            "description": str(tool.description or "")[:300],
        }
        for tool in listing.tools
    ]


def list_tools_sync(config: McpServerConfig) -> list[dict[str, Any]]:
    import asyncio

    return asyncio.run(
        _run_list_tools(config.command, config.args, float(config.timeout_sec))
    )


def call_tool_sync(
    config: McpServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_sec: int | None = None,
) -> str:
    import asyncio

    effective = float(timeout_sec or config.timeout_sec or DEFAULT_TOOL_TIMEOUT_SEC)
    try:
        return asyncio.run(
            _run_tool_call(
                config.command, config.args, tool_name, arguments, effective
            )
        )
    except TimeoutError as error:
        raise McpToolError(
            f"MCP tool '{tool_name}' timed out after {effective:.0f}s"
        ) from error


def audit_mcp_invocation(
    session: Any,
    *,
    tool_ref: str,
    latency_ms: int,
    ok: bool,
    error: str | None = None,
) -> None:
    """Ledger one deterministic MCP tool invocation (task `mcp_tool_call`)."""
    if error:
        logger.warning("mcp_tool_call_error", tool=tool_ref, error=error[:200])
    try:
        session.add(
            AiInteraction(
                context_type="mcp",
                task="mcp_tool_call",
                model=tool_ref,
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
            )
        )
        session.commit()
    except Exception as exc:
        logger.warning("mcp_invocation_ledger_failed", error=str(exc)[:200])
        session.rollback()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
