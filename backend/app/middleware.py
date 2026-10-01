"""ASGI middleware and static serving (plan 20 Phase 4 split).

`ProfileBindingMiddleware` implements the X-Profile-Id ownership binding
(identity-auth §15); `SpaStaticFiles` serves the built SPA with an
index.html fallback. `create_app` registers both.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.profile_context import (
    reset_active_profile,
    reset_active_user,
    set_active_profile,
    set_active_user,
)
from .services.platform.profiles import (
    get_or_create_default,
    get_owned_profile,
    last_used_profile,
    touch_last_used,
)

PROFILE_BIND_EXEMPT_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/me",
    "/api/v1/profiles",
    "/api/v1/admin",
    "/api/v1/health",
    "/api/v1/instance",
    "/api/v1/desktop",
    "/api/v1/shell",
    # Browser *navigations* (PDF iframe documents, <img> subresources)
    # cannot carry the X-Profile-Id header at all — the blobs route is
    # exempt from the header requirement and owner-scopes the sha
    # itself (get_blob), so exemption never means open access.
    "/api/v1/blobs",
    "/api/docs",
)


async def _send_json_error(send: Any, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class ProfileBindingMiddleware:
    """X-Profile-Id ownership binding (identity-auth §15).

    Runs *inside* session enforcement (the verified `nx_principal` is in
    scope state) and binds user + profile into contextvars:

    - server: absent header ⇒ 400; malformed, unknown, or unowned
      ⇒ 403 — no silent default in web mode;
    - desktop: absent header ⇒ the last-used profile (Default
      fallback) — the silent boot UX;
    - exempt prefixes (auth, /me, /profiles, /admin, health, docs,
      beacon, desktop/shell plumbing) work without the header.
    """

    def __init__(self, app: Any, *, session_factory: Any, identity_mode: str) -> None:
        self.app = app
        self.session_factory = session_factory
        self.identity_mode = identity_mode

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        principal = scope.get("state", {}).get("nx_principal")
        user_id: str | None = principal.user_id if principal is not None else None
        raw = headers.get("x-profile-id")
        exempt = any(path.startswith(prefix) for prefix in PROFILE_BIND_EXEMPT_PREFIXES)
        profile_id: str | None = None
        with self.session_factory() as session:
            if raw:
                profile = get_owned_profile(session, user_id, raw) if user_id else None
                if profile is None:
                    if not exempt:
                        await _send_json_error(send, 403, "profile not allowed")
                        return
                else:
                    profile_id = profile.id
            elif not exempt:
                if user_id is None:
                    await _send_json_error(send, 401, "Not authenticated")
                    return
                if self.identity_mode != "desktop":
                    await _send_json_error(send, 400, "X-Profile-Id required")
                    return
                profile = last_used_profile(session, user_id) or get_or_create_default(
                    session, user_id
                )
                profile_id = profile.id
            if profile_id is not None and self.identity_mode == "desktop" and raw:
                touch_last_used(session, profile_id)
        user_token = set_active_user(user_id)
        profile_token = set_active_profile(profile_id)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_active_profile(profile_token)
            reset_active_user(user_token)


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Any) -> Any:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith(("api/", "ws/")):
                raise
            return await super().get_response("index.html", scope)
