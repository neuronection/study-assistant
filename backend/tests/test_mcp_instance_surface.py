"""The D19 MCP instance surface (plan 32 Phase 7): preference rows surface
as instances with the family status vocabulary (ok | degraded | failing |
stale + needs-config, computed without a migration), the tool contracts
surface as declared capability data, and the T3 perimeter disclosure
renders verbatim from the vendored charter.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.extensions.instance_status import instance_status_surface

NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC)


def _server(**overrides: Any) -> dict[str, Any]:
    server: dict[str, Any] = {
        "id": "srv123",
        "name": "coursehub",
        "command": "python",
        "args": [],
        "enabled": True,
        "timeout_sec": 30,
        "tools": [],
        "last_error": None,
        "refreshed_at": None,
        "transport": "stdio",
        "url": "",
        "max_concurrent": 4,
    }
    server.update(overrides)
    return server


def test_status_ok_before_first_refresh() -> None:
    surface = instance_status_surface(_server(), now=NOW)
    assert surface["status"] == "ok"
    assert surface["consecutive_failures"] == 0
    assert surface["last_success_at"] is None
    assert "conditions" not in surface


def test_status_stale_after_the_family_window() -> None:
    stale = (NOW - timedelta(hours=25)).isoformat()
    surface = instance_status_surface(_server(refreshed_at=stale), now=NOW)
    assert surface["status"] == "stale"
    assert surface["last_success_at"] == stale


def test_status_degraded_on_last_error() -> None:
    surface = instance_status_surface(
        _server(refreshed_at=NOW.isoformat(), last_error="spawn failed"),
        now=NOW,
    )
    assert surface["status"] == "degraded"
    assert surface["consecutive_failures"] == 1


def test_needs_config_conditions_per_transport() -> None:
    surface = instance_status_surface(_server(command=""), now=NOW)
    assert surface["conditions"] == ["needs-config"]
    remote = instance_status_surface(
        _server(transport="http", command="", url=""), now=NOW
    )
    assert remote["conditions"] == ["needs-config"]
    remote_ok = instance_status_surface(
        _server(transport="http", command="", url="http://host/mcp"), now=NOW
    )
    assert "conditions" not in remote_ok


def test_rows_surface_status_and_declared_contracts(client: TestClient) -> None:
    with client:
        created = client.post(
            "/api/v1/mcp/servers",
            json={"name": "coursehub", "command": "python", "args": ["-m", "srv"]},
        ).json()
        listed = client.get("/api/v1/mcp/servers").json()
    row = next(entry for entry in listed if entry["id"] == created["id"])
    assert row["status"] == "ok"
    assert row["consecutive_failures"] == 0
    assert row["declared_contracts"] == []


def test_charter_endpoint_renders_the_t3_disclosure_verbatim(client: TestClient) -> None:
    import json
    from pathlib import Path

    charter = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts" / "extension-charter.json").read_text(
            encoding="utf-8"
        )
    )
    with client:
        body = client.get("/api/v1/mcp/charter").json()
    assert body["t3_perimeter_disclosure"] == charter["consent"]["t3PerimeterDisclosure"]
    assert body["capabilities"] == ["secrets"]
