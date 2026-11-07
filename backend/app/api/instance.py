"""Public instance facts (S8) — read-only, no secrets, no session.

The SPA needs these before login (the "Demo — synthetic data" badge must
render on the login gate), so the route is session-exempt
(`SessionAuthMiddleware` / `PROFILE_BIND_EXEMPT_PREFIXES` in main.py) and
stays product-owned: it reads the family-normative `instance_settings`
through the auth kit's live instance state (identity-auth §4/§13,
fail-closed) plus the kit's registration flag — nothing else.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from nx_auth.instance import effective_auth_mode
from pydantic import BaseModel

from .. import __version__
from ..services.platform import version_check

router = APIRouter(prefix="/instance", tags=["instance"])


class InstanceConfigOut(BaseModel):
    demo_mode: bool
    auth_mode: str
    registration_enabled: bool
    identity_mode: str


@router.get("/config", response_model=InstanceConfigOut)
def get_instance_config(request: Request) -> dict[str, object]:
    kit = request.app.state.auth
    state = kit.state
    return {
        "demo_mode": state.demo_mode,
        "auth_mode": effective_auth_mode(state).value,
        "registration_enabled": kit.config.registration_enabled,
        # The entrypoint mode (§4) is public fact, not secret: the SPA's
        # §4.5 control needs it to mark server instances as permanently
        # authenticated ("Remove login" is never offered there).
        "identity_mode": kit.config.identity_mode,
    }


RELEASE_PAGE_URL = "https://github.com/neuronection/study-assistant/releases/latest"
UPDATE_CACHE_SEC = 6 * 60 * 60
_UPDATE_CACHE: dict[str, object] | None = None
_UPDATE_CACHE_AT: datetime | None = None


class UpdateCheckOut(BaseModel):
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str = RELEASE_PAGE_URL
    checked_at: str | None = None
    error: str | None = None


def update_check() -> dict[str, object]:
    global _UPDATE_CACHE, _UPDATE_CACHE_AT

    now = datetime.now(UTC)
    if (
        _UPDATE_CACHE is not None
        and _UPDATE_CACHE_AT is not None
        and (now - _UPDATE_CACHE_AT).total_seconds() < UPDATE_CACHE_SEC
    ):
        return _UPDATE_CACHE
    payload = version_check.check_update(
        "study-assistant",
        __version__,
        releases_page_url=RELEASE_PAGE_URL,
    )
    _UPDATE_CACHE = payload
    _UPDATE_CACHE_AT = now
    return payload


@router.get("/update-check", response_model=UpdateCheckOut)
def get_update_check() -> dict[str, object]:
    return update_check()
