from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai import mcp_client
from ..ai.mcp_client import env_secret_ref, token_secret_ref
from ..core.secrets import get_secret
from ..core.vocab import McpTransport
from ..extensions.errors import ExtensionError
from ..extensions.instance_status import instance_status_surface
from ..extensions.mcp_servers import (
    UNSET,
    build_mcp_config,
    create_server,
    delete_server,
    load_servers,
    merge_refreshed_tools,
    patch_server,
    save_servers,
)
from ..extensions.registry import t3_perimeter_disclosure
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/mcp/servers", tags=["mcp-servers"])
charter_router = APIRouter(prefix="/mcp", tags=["mcp-servers"])


class McpServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    command: str = Field(default="", max_length=500)
    args: list[str] = Field(default_factory=list, max_length=20)
    timeout_sec: int = Field(default=30, ge=5, le=120)
    transport: str = Field(default=McpTransport.STDIO)
    url: str = Field(default="", max_length=500)
    max_concurrent: int = Field(default=4, ge=1, le=8)
    token: str | None = Field(default=None, max_length=2000)
    env: dict[str, str] | None = None


class McpToolPatch(BaseModel):
    name: str
    enabled: bool | None = None
    contract: str | None = None
    url_pattern: str | None = Field(default=None, max_length=300)


class McpServerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    enabled: bool | None = None
    timeout_sec: int | None = Field(default=None, ge=5, le=120)
    tools: list[McpToolPatch] = Field(default_factory=list, max_length=30)
    transport: str | None = None
    url: str | None = Field(default=None, max_length=500)
    max_concurrent: int | None = Field(default=None, ge=1, le=8)
    token: str | None = Field(default=None, max_length=2000)
    env: dict[str, str] | None = None


class McpServerOut(BaseModel):
    id: str
    name: str
    command: str
    args: list[str]
    enabled: bool
    timeout_sec: int
    tools: list[dict[str, Any]]
    last_error: str | None
    refreshed_at: str | None
    transport: str
    url: str
    max_concurrent: int
    has_token: bool
    has_env: bool
    status: str
    last_success_at: str | None
    consecutive_failures: int
    conditions: list[str] = Field(default_factory=list)
    declared_contracts: list[str] = Field(default_factory=list)


def _out(entry: dict[str, Any]) -> McpServerOut:
    server_id = str(entry.get("id") or "")
    status = instance_status_surface(entry)
    declared_contracts = sorted(
        {
            str(tool.get("contract"))
            for tool in entry.get("tools", [])
            if isinstance(tool, dict)
            and tool.get("enabled")
            and tool.get("contract") in ("discovery", "parse")
        }
    )
    return McpServerOut(
        id=server_id,
        name=str(entry.get("name") or ""),
        command=str(entry.get("command") or ""),
        args=[str(arg) for arg in entry.get("args", [])],
        enabled=bool(entry.get("enabled")),
        timeout_sec=int(entry.get("timeout_sec") or 30),
        tools=[tool for tool in entry.get("tools", []) if isinstance(tool, dict)],
        last_error=entry.get("last_error"),
        refreshed_at=entry.get("refreshed_at"),
        transport=str(entry.get("transport") or McpTransport.STDIO),
        url=str(entry.get("url") or ""),
        max_concurrent=int(entry.get("max_concurrent") or 4),
        has_token=get_secret(token_secret_ref(server_id)) is not None,
        has_env=get_secret(env_secret_ref(server_id)) is not None,
        status=str(status["status"]),
        last_success_at=status.get("last_success_at"),
        consecutive_failures=int(status["consecutive_failures"]),
        conditions=list(status.get("conditions") or []),
        declared_contracts=declared_contracts,
    )


class McpCharterOut(BaseModel):
    t3_perimeter_disclosure: str
    capabilities: list[str]


@charter_router.get("/charter", response_model=McpCharterOut)
def get_mcp_charter() -> McpCharterOut:
    """The D19/D22 instance-surface data: the T3 perimeter disclosure is
    the charter's verbatim copy (paraphrasing it away is a conformance
    failure) plus the bundled mcp connector's declared capabilities."""
    from ..extensions.registry import extension_registry

    return McpCharterOut(
        t3_perimeter_disclosure=t3_perimeter_disclosure(),
        capabilities=extension_registry.capabilities("mcp"),
    )


@router.get("", response_model=list[McpServerOut])
def list_servers(session: Session = Depends(get_session)) -> list[McpServerOut]:
    profile = ensure_default_profile(session)
    return [_out(entry) for entry in load_servers(session, profile.id)]


@router.post("", response_model=McpServerOut, status_code=201)
def add_server(
    body: McpServerIn,
    session: Session = Depends(get_session),
) -> McpServerOut:
    profile = ensure_default_profile(session)
    try:
        entry = create_server(
            session,
            profile.id,
            name=body.name,
            command=body.command,
            args=body.args,
            timeout_sec=body.timeout_sec,
            transport=body.transport,
            url=body.url,
            max_concurrent=body.max_concurrent,
            token=body.token,
            env=body.env,
        )
        session.commit()
    except ExtensionError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=error.detail) from error
    return _out(entry)


@router.patch("/{server_id}", response_model=McpServerOut)
def update_server(
    server_id: str,
    body: McpServerPatch,
    session: Session = Depends(get_session),
) -> McpServerOut:
    profile = ensure_default_profile(session)
    provided = body.model_fields_set
    try:
        entry = patch_server(
            session,
            profile.id,
            server_id,
            enabled=body.enabled,
            timeout_sec=body.timeout_sec,
            name=body.name,
            tool_updates=[tool.model_dump(exclude_none=True) for tool in body.tools],
            transport=body.transport if "transport" in provided else UNSET,
            url=body.url if "url" in provided else UNSET,
            max_concurrent=(body.max_concurrent if "max_concurrent" in provided else UNSET),
            token=body.token if "token" in provided else UNSET,
            env=body.env if "env" in provided else UNSET,
        )
        session.commit()
    except ExtensionError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=error.detail) from error
    return _out(entry)


@router.delete("/{server_id}", status_code=204)
def remove_server(
    server_id: str,
    session: Session = Depends(get_session),
) -> None:
    profile = ensure_default_profile(session)
    if not delete_server(session, profile.id, server_id):
        raise HTTPException(status_code=404, detail="server not found")
    session.commit()


@router.post("/{server_id}/refresh", response_model=McpServerOut)
def refresh_server(
    server_id: str,
    session: Session = Depends(get_session),
) -> McpServerOut:
    profile = ensure_default_profile(session)
    servers = load_servers(session, profile.id)
    entry = next((item for item in servers if item.get("id") == server_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="server not found")
    try:
        discovered = mcp_client.list_tools_sync(build_mcp_config(entry))
    except Exception as error:
        entry["last_error"] = str(error)[:500]
        save_servers(session, profile.id, servers)
        session.commit()
        raise HTTPException(
            status_code=502,
            detail=f"MCP server failed to refresh: {str(error)[:300]}",
        ) from error
    merge_refreshed_tools(entry, discovered)
    entry["last_error"] = None
    save_servers(session, profile.id, servers)
    session.commit()
    return _out(entry)
