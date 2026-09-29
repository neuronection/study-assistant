"""Registered external MCP servers (plan 73-G, ADR-170): machine-local
config in profile preferences (`mcp.servers`), disabled by default, explicit
refresh, per-tool allowlist — refresh never auto-enables. Server entries hold
no secrets: bearer tokens and stdio env maps live in the OS keyring
(`app/core/secrets.py`) under `mcp:<id>:token` / `mcp:<id>:env`.
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from ...ai.mcp_client import (
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_TOOL_TIMEOUT_SEC,
    MAX_CONCURRENT_CAP,
    MAX_SERVERS,
    McpServerConfig,
    env_secret_ref,
    new_server_config,
    now_iso,
    parse_env_json,
    token_secret_ref,
)
from ...core.secrets import delete_secret, get_secret, set_secret
from ...core.vocab import McpTransport

TOOL_CONTRACTS = ("none", "discovery", "parse")
TRANSPORTS = tuple(t.value for t in McpTransport)


class McpServersError(ValueError):
    pass


def _validate_transport_fields(
    transport: str,
    command: str,
    url: str,
) -> tuple[str, str]:
    if transport not in TRANSPORTS:
        allowed = ", ".join(TRANSPORTS)
        raise McpServersError(f"unknown transport '{transport}' (allowed: {allowed})")
    if transport == McpTransport.STDIO:
        return command, ""
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        raise McpServersError("a http(s) URL is required for remote servers")
    return "", clean_url[:500]


def load_servers(session: Session, profile_id: str) -> list[dict[str, Any]]:
    from ...domain.models import Profile

    profile = session.get(Profile, profile_id)
    prefs = profile.preferences if profile is not None else None
    if not isinstance(prefs, dict):
        return []
    raw = prefs.get("mcp")
    if not isinstance(raw, dict):
        return []
    servers = raw.get("servers")
    if not isinstance(servers, list):
        return []
    return [entry for entry in servers if isinstance(entry, dict)]


def save_servers(session: Session, profile_id: str, servers: list[dict[str, Any]]) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    from ...domain.models import Profile

    profile = session.get(Profile, profile_id)
    if profile is None:
        raise McpServersError("profile not found")
    prefs = dict(profile.preferences or {})
    prefs["mcp"] = {"servers": servers}
    profile.preferences = prefs
    # In-place edits to a loaded entry make the new value compare equal to
    # the old one — flag_modified forces the JSON column to be written.
    flag_modified(profile, "preferences")
    session.flush()


def get_server(session: Session, profile_id: str, server_id: str) -> dict[str, Any] | None:
    for entry in load_servers(session, profile_id):
        if entry.get("id") == server_id:
            return entry
    return None


def _replace_server(
    session: Session, profile_id: str, updated: dict[str, Any]
) -> None:
    servers = load_servers(session, profile_id)
    save_servers(
        session,
        profile_id,
        [updated if entry.get("id") == updated.get("id") else entry for entry in servers],
    )


def create_server(
    session: Session,
    profile_id: str,
    *,
    name: str,
    command: str = "",
    args: list[str] | None = None,
    timeout_sec: int = DEFAULT_TOOL_TIMEOUT_SEC,
    transport: str = McpTransport.STDIO,
    url: str = "",
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    token: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    clean_name = (name or "").strip()
    clean_command, clean_url = _validate_transport_fields(
        transport, (command or "").strip(), url or ""
    )
    if not clean_name:
        raise McpServersError("name is required")
    if transport == McpTransport.STDIO and not clean_command:
        raise McpServersError("command is required for stdio servers")
    if not 5 <= int(timeout_sec) <= 120:
        raise McpServersError("timeout_sec must be 5-120")
    if not 1 <= int(max_concurrent) <= MAX_CONCURRENT_CAP:
        raise McpServersError(
            f"max_concurrent must be 1-{MAX_CONCURRENT_CAP}"
        )
    servers = load_servers(session, profile_id)
    if len(servers) >= MAX_SERVERS:
        raise McpServersError(f"at most {MAX_SERVERS} servers can be registered")
    entry: dict[str, Any] = new_server_config(
        clean_name[:80],
        clean_command[:500],
        [str(arg)[:500] for arg in (args or [])][:20],
        int(timeout_sec),
        transport=transport,
        url=clean_url,
        max_concurrent=int(max_concurrent),
    )
    if token:
        set_secret(token_secret_ref(str(entry["id"])), token)
    if env:
        set_secret(env_secret_ref(str(entry["id"])), json.dumps(env))
    servers.append(entry)
    save_servers(session, profile_id, servers)
    return entry


UNSET = object()


def patch_server(
    session: Session,
    profile_id: str,
    server_id: str,
    *,
    enabled: bool | None = None,
    timeout_sec: int | None = None,
    name: str | None = None,
    tool_updates: list[dict[str, Any]] | None = None,
    transport: Any = UNSET,
    url: Any = UNSET,
    max_concurrent: Any = UNSET,
    token: Any = UNSET,
    env: Any = UNSET,
) -> dict[str, Any]:
    server = get_server(session, profile_id, server_id)
    if server is None:
        raise McpServersError("server not found")
    if name is not None:
        clean = name.strip()
        if not clean:
            raise McpServersError("name must not be empty")
        server["name"] = clean[:80]
    if enabled is not None:
        server["enabled"] = bool(enabled)
    if timeout_sec is not None:
        if not 5 <= int(timeout_sec) <= 120:
            raise McpServersError("timeout_sec must be 5-120")
        server["timeout_sec"] = int(timeout_sec)
    next_transport = str(transport) if transport is not UNSET else None
    next_url = str(url or "") if url is not UNSET else None
    if next_transport is not None or next_url is not None:
        clean_command, clean_url = _validate_transport_fields(
            next_transport or str(server.get("transport") or McpTransport.STDIO),
            str(server.get("command") or "") if next_transport is None else "",
            next_url if next_url is not None else str(server.get("url") or ""),
        )
        if clean_command or next_transport == McpTransport.STDIO:
            server["command"] = clean_command[:500]
        if next_transport is not None:
            server["transport"] = next_transport
        server["url"] = clean_url
    if max_concurrent is not UNSET and max_concurrent is not None:
        if not 1 <= int(max_concurrent) <= MAX_CONCURRENT_CAP:
            raise McpServersError(
                f"max_concurrent must be 1-{MAX_CONCURRENT_CAP}"
            )
        server["max_concurrent"] = int(max_concurrent)
    if token is not UNSET:
        if token:
            set_secret(token_secret_ref(server_id), str(token))
        else:
            delete_secret(token_secret_ref(server_id))
    if env is not UNSET:
        if env:
            set_secret(env_secret_ref(server_id), json.dumps(env))
        else:
            delete_secret(env_secret_ref(server_id))
    for update in tool_updates or []:
        tool_name = str(update.get("name") or "")
        target = next(
            (tool for tool in server["tools"] if tool.get("name") == tool_name),
            None,
        )
        if target is None:
            raise McpServersError(f"unknown tool '{tool_name}' — refresh first")
        if "enabled" in update:
            target["enabled"] = bool(update["enabled"])
        if "contract" in update:
            contract = str(update["contract"])
            if contract not in TOOL_CONTRACTS:
                raise McpServersError(f"unknown contract '{contract}'")
            target["contract"] = contract
        if "url_pattern" in update:
            target["url_pattern"] = str(update["url_pattern"] or "").strip()[:300]
    _replace_server(session, profile_id, server)
    return server


def delete_server(session: Session, profile_id: str, server_id: str) -> bool:
    servers = load_servers(session, profile_id)
    remaining = [entry for entry in servers if entry.get("id") != server_id]
    if len(remaining) == len(servers):
        return False
    save_servers(session, profile_id, remaining)
    delete_secret(token_secret_ref(server_id))
    delete_secret(env_secret_ref(server_id))
    return True


def merge_refreshed_tools(
    server: dict[str, Any], discovered: list[dict[str, Any]]
) -> None:
    previous = {
        str(tool.get("name")): tool
        for tool in server.get("tools", [])
        if isinstance(tool, dict)
    }
    server["tools"] = [
        {
            "name": str(tool.get("name") or "")[:120],
            "description": str(tool.get("description") or "")[:300],
            "enabled": previous.get(str(tool.get("name")), {}).get(
                "enabled", False
            ),
            "contract": previous.get(str(tool.get("name")), {}).get(
                "contract", "none"
            ),
            "url_pattern": previous.get(str(tool.get("name")), {}).get(
                "url_pattern"
            ),
        }
        for tool in discovered
        if tool.get("name")
    ]
    server["refreshed_at"] = now_iso()


def enabled_tools(
    session: Session, profile_id: str, contract: str
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for server in load_servers(session, profile_id):
        if not server.get("enabled"):
            continue
        for tool in server.get("tools", []):
            if not isinstance(tool, dict):
                continue
            if tool.get("enabled") and tool.get("contract") == contract:
                pairs.append((server, tool))
    return pairs


def build_mcp_config(server: dict[str, Any]) -> McpServerConfig:
    server_id = str(server.get("id") or "")
    token = get_secret(token_secret_ref(server_id))
    env = parse_env_json(get_secret(env_secret_ref(server_id)))
    return McpServerConfig(
        id=server_id,
        name=str(server.get("name") or ""),
        command=str(server.get("command") or ""),
        args=[str(arg) for arg in server.get("args", [])],
        enabled=bool(server.get("enabled")),
        timeout_sec=int(server.get("timeout_sec") or DEFAULT_TOOL_TIMEOUT_SEC),
        tools=list(server.get("tools", [])),
        last_error=server.get("last_error"),
        refreshed_at=server.get("refreshed_at"),
        transport=str(
            server.get("transport") or McpTransport.STDIO
        ),
        url=str(server.get("url") or ""),
        max_concurrent=int(
            server.get("max_concurrent") or DEFAULT_MAX_CONCURRENT
        ),
        token=token or None,
        env=env,
    )
