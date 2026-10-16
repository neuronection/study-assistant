"""Host adapter for the bundled external-sources connector (plan 73-E).

The connector lives in the extension subsystem
(:mod:`app.extensions.builtin.external_sources` — D24); this module is the
HOST side of the boundary: it injects the suggestion funnel
(:func:`app.services.content.discovery.record_scan_suggestion`) into the
connector's scan legs and re-exports the cadence policy the scheduler
consumes. Sync orchestration (the scheduler, overlap guard, due times)
stays here — D24 rule 4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.extensions.builtin.external_sources import (
    DEFAULT_SCAN_INTERVAL_SEC,
    MIN_SCAN_INTERVAL_SEC,
)
from app.extensions.builtin.external_sources import (
    effective_interval as _connector_effective_interval,
)
from app.extensions.builtin.external_sources import (
    next_due_at as _connector_next_due_at,
)
from app.extensions.builtin.external_sources import (
    run_scan as _connector_run_scan,
)
from app.extensions.errors import ExtensionError

from .discovery import record_scan_suggestion

__all__ = [
    "DEFAULT_SCAN_INTERVAL_SEC",
    "MIN_SCAN_INTERVAL_SEC",
    "ExtensionError",
    "effective_interval",
    "next_due_at",
    "run_scan",
    "validate_source",
]


def validate_source(
    kind: str, url: str, options: dict[str, Any] | None
) -> tuple[str, str, dict[str, Any]]:
    from app.extensions.builtin.external_sources import validate_source as _validate

    return _validate(kind, url, options)


def effective_interval(source: Any) -> int:
    return _connector_effective_interval(source)


def next_due_at(source: Any) -> datetime:
    return _connector_next_due_at(source)


def run_scan(session: Session, source: Any) -> dict[str, int]:
    return _connector_run_scan(session, source, record_scan_suggestion)
