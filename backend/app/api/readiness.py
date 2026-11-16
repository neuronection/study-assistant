"""Readiness probe (`/ready`, plan 64 §1.4 / ADR-0062 v7 §9).

Liveness (`/api/v1/health`) answers "is the process up"; readiness answers
"may ingress send traffic": the database is reachable **and at this
release's migration head**, required object storage answers, and the boot
(lifespan startup) completed. Soft signals — optional (non-required) object
storage and Redis — never flip the status: study has no Redis (in-process
schedulers), so the soft column reports `none`.

Mounted at the root (outside `/api/v1`) in `app.main`, unauthenticated by
construction: both the kit's session enforcement and profile binding only
ever touch `/api/*` paths, so a probe needs no exempt-prefix carve-out.
503 until every hard check passes — negative tests live in
`tests/test_ready_endpoint.py`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import Engine

from .. import __version__
from ..local import head_revision
from ..storage.health import STATUS_OK

router = APIRouter(tags=["system"])


def db_revision(engine: Engine) -> str | None:
    """The stamped `alembic_version`, or None when unreachable/unstamped.

    Module-level so the negative tests can simulate a database outage (or a
    database behind the migration head) without a real server.
    """
    from ..local import _current_revision

    return _current_revision(engine)


def _db_check(app_state: Any) -> dict[str, Any]:
    engine: Engine = app_state.engine
    revision = db_revision(engine)
    at_head = False
    if revision is not None:
        try:
            at_head = revision == head_revision()
        except Exception:  # pragma: no cover - alembic files ship with the image
            at_head = False
    detail = None if at_head else "db not at migration head"
    return {"ok": at_head, "revision": revision, "detail": detail}


def _storage_check(app_state: Any) -> dict[str, Any]:
    health = app_state.storage_health.snapshot()
    required = bool(health.required)
    return {
        # Hard only when object storage is required (a cloud profile or
        # OBJECT_STORAGE_REQUIRED=true); otherwise a degraded provider is
        # a soft signal that never flips the status (plan 64 §1.4).
        "ok": health.status == STATUS_OK or not required,
        "required": required,
        "backend": health.backend,
        "status": health.status,
        "detail": health.detail,
    }


@router.get("/ready")
def ready(request: Request, response: Response) -> dict[str, Any]:
    app_state = request.app.state
    checks = {
        "db": _db_check(app_state),
        "storage": _storage_check(app_state),
        "boot": {"ok": bool(getattr(app_state, "boot_complete", False)), "detail": None},
    }
    # Soft signals never flip the status (plan 64 §1.4): study runs no
    # Redis (in-process schedulers), so the soft column is `none` today.
    ready_ = all(check["ok"] for check in checks.values())
    body: dict[str, Any] = {
        "status": "ready" if ready_ else "not-ready",
        "version": __version__,
        "checks": checks,
        "soft": {"redis": "none (in-process schedulers)"},
    }
    if not ready_:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return body
