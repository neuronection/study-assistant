"""Public instance facts (S8) — read-only, no secrets, no session.

The SPA needs these before login (the "Demo — synthetic data" badge must
render on the login gate), so the route is session-exempt
(`SessionAuthMiddleware` / `PROFILE_BIND_EXEMPT_PREFIXES` in main.py) and
stays product-owned: it reads the family-normative `instance_settings`
through the auth kit's live instance state (identity-auth §4/§13,
fail-closed) plus the kit's registration flag — nothing else.
"""

from fastapi import APIRouter, Request
from nx_auth.instance import effective_auth_mode
from pydantic import BaseModel

router = APIRouter(prefix="/instance", tags=["instance"])


class InstanceConfigOut(BaseModel):
    demo_mode: bool
    auth_mode: str
    registration_enabled: bool


@router.get("/config", response_model=InstanceConfigOut)
def get_instance_config(request: Request) -> dict[str, object]:
    kit = request.app.state.auth
    state = kit.state
    return {
        "demo_mode": state.demo_mode,
        "auth_mode": effective_auth_mode(state).value,
        "registration_enabled": kit.config.registration_enabled,
    }
