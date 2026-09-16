from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai import mcp_client
from ..services.platform.mcp_servers import (
    McpServersError,
    build_mcp_config,
    create_server,
    delete_server,
    load_servers,
    merge_refreshed_tools,
    patch_server,
    save_servers,
)
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/mcp/servers", tags=["mcp-servers"])


class McpServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    command: str = Field(min_length=1, max_length=500)
    args: list[str] = Field(default_factory=list, max_length=20)
    timeout_sec: int = Field(default=30, ge=5, le=120)


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


def _out(entry: dict[str, Any]) -> McpServerOut:
    return McpServerOut(
        id=str(entry.get("id") or ""),
        name=str(entry.get("name") or ""),
        command=str(entry.get("command") or ""),
        args=[str(arg) for arg in entry.get("args", [])],
        enabled=bool(entry.get("enabled")),
        timeout_sec=int(entry.get("timeout_sec") or 30),
        tools=[tool for tool in entry.get("tools", []) if isinstance(tool, dict)],
        last_error=entry.get("last_error"),
        refreshed_at=entry.get("refreshed_at"),
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
        )
        session.commit()
    except McpServersError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _out(entry)


@router.patch("/{server_id}", response_model=McpServerOut)
def update_server(
    server_id: str,
    body: McpServerPatch,
    session: Session = Depends(get_session),
) -> McpServerOut:
    profile = ensure_default_profile(session)
    try:
        entry = patch_server(
            session,
            profile.id,
            server_id,
            enabled=body.enabled,
            timeout_sec=body.timeout_sec,
            name=body.name,
            tool_updates=[tool.model_dump(exclude_none=True) for tool in body.tools],
        )
        session.commit()
    except McpServersError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
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
    entry = next(
        (item for item in servers if item.get("id") == server_id), None
    )
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
