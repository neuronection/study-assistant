"""Registered external MCP servers (plan 73-G, ADR-170): machine-local
config in profile preferences (`mcp.servers`), disabled by default, explicit
refresh, per-tool allowlist — refresh never auto-enables. Nothing secret is
stored: servers read their own config (no env/secret mapping in v1).
"""

from typing import Any

from sqlalchemy.orm import Session

from ...ai.mcp_client import (
    DEFAULT_TOOL_TIMEOUT_SEC,
    MAX_SERVERS,
    McpServerConfig,
    new_server_config,
    now_iso,
)

TOOL_CONTRACTS = ("none", "discovery", "parse")


class McpServersError(ValueError):
    pass


def load_servers(session: Session, profile_id: int) -> list[dict[str, Any]]:
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


def save_servers(session: Session, profile_id: int, servers: list[dict[str, Any]]) -> None:
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


def get_server(session: Session, profile_id: int, server_id: str) -> dict[str, Any] | None:
    for entry in load_servers(session, profile_id):
        if entry.get("id") == server_id:
            return entry
    return None


def _replace_server(
    session: Session, profile_id: int, updated: dict[str, Any]
) -> None:
    servers = load_servers(session, profile_id)
    save_servers(
        session,
        profile_id,
        [updated if entry.get("id") == updated.get("id") else entry for entry in servers],
    )


def create_server(
    session: Session,
    profile_id: int,
    *,
    name: str,
    command: str,
    args: list[str] | None = None,
    timeout_sec: int = DEFAULT_TOOL_TIMEOUT_SEC,
) -> dict[str, Any]:
    clean_name = (name or "").strip()
    clean_command = (command or "").strip()
    if not clean_name or not clean_command:
        raise McpServersError("name and command are required")
    if not 5 <= int(timeout_sec) <= 120:
        raise McpServersError("timeout_sec must be 5-120")
    servers = load_servers(session, profile_id)
    if len(servers) >= MAX_SERVERS:
        raise McpServersError(f"at most {MAX_SERVERS} servers can be registered")
    entry: dict[str, Any] = new_server_config(
        clean_name[:80],
        clean_command[:500],
        [str(arg)[:500] for arg in (args or [])][:20],
        int(timeout_sec),
    )
    servers.append(entry)
    save_servers(session, profile_id, servers)
    return entry


def patch_server(
    session: Session,
    profile_id: int,
    server_id: str,
    *,
    enabled: bool | None = None,
    timeout_sec: int | None = None,
    name: str | None = None,
    tool_updates: list[dict[str, Any]] | None = None,
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


def delete_server(session: Session, profile_id: int, server_id: str) -> bool:
    servers = load_servers(session, profile_id)
    remaining = [entry for entry in servers if entry.get("id") != server_id]
    if len(remaining) == len(servers):
        return False
    save_servers(session, profile_id, remaining)
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
    session: Session, profile_id: int, contract: str
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
    return McpServerConfig(
        id=str(server.get("id") or ""),
        name=str(server.get("name") or ""),
        command=str(server.get("command") or ""),
        args=[str(arg) for arg in server.get("args", [])],
        enabled=bool(server.get("enabled")),
        timeout_sec=int(server.get("timeout_sec") or DEFAULT_TOOL_TIMEOUT_SEC),
        tools=list(server.get("tools", [])),
        last_error=server.get("last_error"),
        refreshed_at=server.get("refreshed_at"),
    )
