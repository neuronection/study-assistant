"""MCP client bridge (plan 73-G, ADR-170): deterministic service invocation
of user-registered external MCP servers over stdio, Streamable HTTP or SSE.

Servers are launched lazily per invocation and reaped when the call ends —
no permanent subprocess fleet. Remote transports send the stored bearer
token as an Authorization header; stdio servers receive the user env map on
top of a minimal default environment. Secrets never enter the stored server
entry — `build_mcp_config` (services layer) reads them from the keyring per
config build and they live only in the short-lived config object. External
tool output is untrusted input (family-ai trust boundary): every consumer
validates shapes app-side. The `mcp` SDK import lives ONLY here (+ tests),
matching this repo's existing `mcp`-SDK server precedent
(`app/mcp_resources.py`).
"""

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from ..core.vocab import McpTransport
from ..domain.models import AiInteraction

logger = structlog.get_logger(__name__)

DEFAULT_TOOL_TIMEOUT_SEC = 30
SERVER_ID_LEN = 12
MAX_SERVERS = 10
DEFAULT_MAX_CONCURRENT = 4
MAX_CONCURRENT_CAP = 8

CONCURRENCY_ACQUIRE_TIMEOUT_SEC = 5.0


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
    transport: str = McpTransport.STDIO
    url: str = ""
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    token: str | None = None
    env: dict[str, str] = field(default_factory=dict)


def new_server_id() -> str:
    return uuid.uuid4().hex[:SERVER_ID_LEN]


def new_server_config(
    name: str,
    command: str,
    args: list[str],
    timeout_sec: int = DEFAULT_TOOL_TIMEOUT_SEC,
    transport: str = McpTransport.STDIO,
    url: str = "",
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
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
        "transport": transport,
        "url": url,
        "max_concurrent": max_concurrent,
    }


def token_secret_ref(server_id: str) -> str:
    return f"mcp:{server_id}:token"


def env_secret_ref(server_id: str) -> str:
    return f"mcp:{server_id}:env"


def parse_env_json(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items()}


_concurrency: dict[str, threading.BoundedSemaphore] = {}
_concurrency_lock = threading.Lock()


def _semaphore_for(server_id: str, max_concurrent: int) -> threading.BoundedSemaphore:
    with _concurrency_lock:
        semaphore = _concurrency.get(server_id)
        if semaphore is None:
            semaphore = threading.BoundedSemaphore(max(1, int(max_concurrent)))
            _concurrency[server_id] = semaphore
        return semaphore


def _auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


async def _open_session(config: McpServerConfig) -> tuple[Any, Any]:
    """Opens the transport and session; closing the returned stack reaps
    both."""
    import contextlib

    from mcp import ClientSession

    stack = contextlib.AsyncExitStack()
    read: Any
    write: Any

    if config.transport == McpTransport.STDIO:
        from mcp.client.stdio import (
            StdioServerParameters,
            get_default_environment,
            stdio_client,
        )

        env = get_default_environment()
        env.update({str(k): str(v) for k, v in (config.env or {}).items()})
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=env,
        )
        read, write = await stack.enter_async_context(stdio_client(server_params))
    elif config.transport == McpTransport.HTTP:
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client

        http_client = create_mcp_http_client(headers=_auth_headers(config.token))
        await stack.enter_async_context(http_client)
        read, write = await stack.enter_async_context(
            streamable_http_client(config.url, http_client=http_client)
        )
    elif config.transport == McpTransport.SSE:
        from mcp.client.sse import sse_client

        read, write = await stack.enter_async_context(
            sse_client(config.url, headers=_auth_headers(config.token))
        )
    else:
        raise McpToolError(f"unknown transport '{config.transport}'")

    session = await stack.enter_async_context(ClientSession(read, write))
    return stack, session


async def _run_tool_call(
    config: McpServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_sec: float,
) -> str:
    import anyio

    stack, session = await _open_session(config)
    with stack:
        with anyio.fail_after(timeout_sec):
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


async def _run_list_tools(config: McpServerConfig) -> list[dict[str, Any]]:
    import anyio

    stack, session = await _open_session(config)
    with stack:
        with anyio.fail_after(float(config.timeout_sec)):
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

    return asyncio.run(_run_list_tools(config))


def call_tool_sync(
    config: McpServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_sec: int | None = None,
) -> str:
    import asyncio

    effective = float(timeout_sec or config.timeout_sec or DEFAULT_TOOL_TIMEOUT_SEC)
    semaphore = _semaphore_for(config.id, config.max_concurrent)
    if not semaphore.acquire(timeout=CONCURRENCY_ACQUIRE_TIMEOUT_SEC):
        raise McpToolError(
            f"MCP server '{config.name}' is busy — max {config.max_concurrent} concurrent call(s)"
        )
    try:
        return asyncio.run(_run_tool_call(config, tool_name, arguments, effective))
    except TimeoutError as error:
        raise McpToolError(f"MCP tool '{tool_name}' timed out after {effective:.0f}s") from error
    finally:
        semaphore.release()


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
