"""The family instance-status surface (ADR-0040 D7/D21 — the vocabulary is
family law, the persistence stays study-owned preferences).

Every surface that renders an MCP instance's state speaks ONE shape:

* ``status`` — ``ok | degraded | failing | stale``
* ``last_success_at`` — RFC3339 timestamp of the last successful refresh
* ``consecutive_failures`` — integer >= 0
* ``conditions`` — ``["needs-config"]`` when the stored config no longer
  satisfies the bundled connector's config requirements (never silently
  defaulted)

Derivation over the ``mcp.servers`` preference rows (host-profile policy,
computed without a migration — the rows carry ``enabled``, ``last_error``
and ``refreshed_at``): a failed refresh is one strike (``degraded``); the
rows don't count consecutive refresh failures, so ``failing`` needs a
second consecutive-failure signal study does not track yet. ``stale``
when the last successful refresh is older than the family window
(24h — generous; refresh is explicit, so most idle instances render
``stale``-adjacent ``ok`` only within the window).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

STALENESS_WINDOW = timedelta(hours=24)

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_FAILING = "failing"
STATUS_STALE = "stale"

_CONDITION_NEEDS_CONFIG = "needs-config"


def _needs_config(server: dict[str, Any]) -> bool:
    """The instance config must satisfy the bundled mcp connector's
    required shape: stdio needs a command, remote transports a URL."""
    from app.core.vocab import McpTransport

    transport = str(server.get("transport") or McpTransport.STDIO)
    if transport == McpTransport.STDIO:
        return not str(server.get("command") or "").strip()
    return not str(server.get("url") or "").strip()


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def instance_status_surface(
    server: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute the family status surface for one mcp.servers row."""

    now = now or datetime.now(UTC)
    conditions: list[str] = []
    if _needs_config(server):
        conditions.append(_CONDITION_NEEDS_CONFIG)

    last_error = str(server.get("last_error") or "").strip()
    last_success_at = _parse_ts(server.get("refreshed_at"))

    if last_error:
        consecutive_failures = 1
        status = STATUS_DEGRADED
    elif last_success_at is None:
        consecutive_failures = 0
        status = STATUS_OK
    else:
        consecutive_failures = 0
        status = (
            STATUS_STALE if (now - last_success_at) > STALENESS_WINDOW else STATUS_OK
        )

    surface: dict[str, Any] = {
        "status": status,
        "last_success_at": server.get("refreshed_at") if last_success_at else None,
        "consecutive_failures": consecutive_failures,
    }
    if conditions:
        surface["conditions"] = conditions
    return surface
