"""OAuth2 authorization-code + PKCE with a loopback redirect (plan 86 B, ADR-215).

Only loopback redirects on ``127.0.0.1`` are supported: the browser opens,
one short-lived local listener receives the one callback, and tokens are
sealed into the OS keyring through :mod:`app.core.secrets` (``enc::`` at
rest, ADR-0027). No custom URI schemes, no embedded webviews, no token ever
touches the database or a config file. Refresh belongs to the adapter layer;
the state machine here is pure over an injectable ``httpx`` transport.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.core import secrets as secret_store

AUTH_TIMEOUT_SEC = 180.0


class OAuthError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail[:500]
        super().__init__(f"{code}: {self.detail}")


@dataclass(frozen=True)
class OAuthConfig:
    provider_id: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    redirect_port: int
    client_id: str
    client_secret: str | None = None
    extra_auth_params: dict[str, str] | None = None

    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.redirect_port}/oauth/callback"


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    token_type: str
    expires_at: str | None
    scope: str | None = None

    def expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        return current >= expires


def pkce_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def new_state() -> str:
    return secrets.token_urlsafe(24)


def build_authorize_url(config: OAuthConfig, state: str, verifier: str) -> str:
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri(),
        "scope": " ".join(config.scopes),
        "state": state,
        "code_challenge": pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    for key, value in (config.extra_auth_params or {}).items():
        params[key] = value
    separator = "&" if urlparse(config.authorize_url).query else "?"
    return f"{config.authorize_url}{separator}{urlencode(params)}"


def _token_payload(config: OAuthConfig, payload: dict[str, str]) -> dict[str, str]:
    body = dict(payload)
    body["client_id"] = config.client_id
    if config.client_secret:
        body["client_secret"] = config.client_secret
    return body


def _post_token(
    config: OAuthConfig,
    payload: dict[str, str],
    transport: httpx.BaseTransport | None,
) -> dict[str, Any]:
    try:
        with httpx.Client(transport=transport, timeout=30.0) as client:
            response = client.post(
                config.token_url,
                data=_token_payload(config, payload),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:
        raise OAuthError("unreachable", f"token endpoint unreachable: {error}") from error
    if response.status_code >= 400:
        detail = response.text[:300]
        with contextlib.suppress(ValueError):
            detail = str(response.json().get("error_description") or detail)
        raise OAuthError("auth", f"token endpoint rejected the request: {detail}")
    try:
        data = response.json()
    except ValueError as error:
        raise OAuthError("protocol", "token endpoint returned non-JSON") from error
    if not isinstance(data, dict) or not data.get("access_token"):
        raise OAuthError("protocol", "token response has no access_token")
    return data


def _tokens_from_response(data: dict[str, Any], *, now: datetime | None = None) -> OAuthTokens:
    expires_at: str | None = None
    expires_in = data.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        current = now or datetime.now(UTC)
        expires_at = (current + timedelta(seconds=int(expires_in))).isoformat()
    else:
        raw_expiry = data.get("expires_at")
        if isinstance(raw_expiry, str) and raw_expiry:
            expires_at = raw_expiry
    return OAuthTokens(
        access_token=str(data["access_token"]),
        refresh_token=(
            str(data["refresh_token"]) if data.get("refresh_token") is not None else None
        ),
        token_type=str(data.get("token_type") or "Bearer"),
        expires_at=expires_at,
        scope=str(data["scope"]) if data.get("scope") is not None else None,
    )


def exchange_code(
    config: OAuthConfig,
    code: str,
    verifier: str,
    *,
    transport: httpx.BaseTransport | None = None,
    now: datetime | None = None,
) -> OAuthTokens:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": config.redirect_uri(),
    }
    return _tokens_from_response(_post_token(config, payload, transport), now=now)


def refresh_tokens(
    config: OAuthConfig,
    tokens: OAuthTokens,
    *,
    transport: httpx.BaseTransport | None = None,
    now: datetime | None = None,
) -> OAuthTokens:
    if not tokens.refresh_token:
        raise OAuthError("auth", "stored credentials have no refresh token")
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": tokens.refresh_token,
    }
    fresh = _tokens_from_response(_post_token(config, payload, transport), now=now)
    if fresh.refresh_token is None:
        fresh = OAuthTokens(
            access_token=fresh.access_token,
            refresh_token=tokens.refresh_token,
            token_type=fresh.token_type,
            expires_at=fresh.expires_at,
            scope=fresh.scope,
        )
    return fresh


def seal_tokens(slot: str, tokens: OAuthTokens) -> None:
    secret_store.set_secret(slot, json.dumps(asdict(tokens)))


def load_tokens(slot: str) -> OAuthTokens | None:
    raw = secret_store.get_secret(slot)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not data.get("access_token"):
        return None
    return OAuthTokens(
        access_token=str(data["access_token"]),
        refresh_token=str(data["refresh_token"]) if data.get("refresh_token") else None,
        token_type=str(data.get("token_type") or "Bearer"),
        expires_at=str(data["expires_at"]) if data.get("expires_at") else None,
        scope=str(data["scope"]) if data.get("scope") else None,
    )


def wipe_tokens(slot: str) -> None:
    secret_store.delete_secret(slot)


def token_status(tokens: OAuthTokens | None, *, now: datetime | None = None) -> str:
    if tokens is None:
        return "needs-config"
    return "expired" if tokens.expired(now=now) else "ok"


def token_slot(source_id: str) -> str:
    return f"source:{source_id}:oauth"


def resolve_client(config: OAuthConfig) -> OAuthConfig:
    if config.client_id:
        return config
    raise OAuthError("needs-config", "OAuth client is not configured for this provider")


def oauth_config_from_catalog(
    provider_id: str,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> OAuthConfig:
    from app.extensions.builtin.external_sources.providers import get_provider

    provider = get_provider(provider_id)
    if provider.oauth is None:
        raise OAuthError("invalid", f"provider '{provider_id}' does not use OAuth")
    resolved_id = client_id or os.environ.get(provider.oauth.client_id_env, "")
    if not resolved_id:
        raise OAuthError(
            "needs-config",
            f"set {provider.oauth.client_id_env} to the OAuth client id registered for this app",
        )
    resolved_secret = client_secret or os.environ.get(provider.oauth.client_secret_env)
    return OAuthConfig(
        provider_id=provider_id,
        authorize_url=provider.oauth.authorize_url,
        token_url=provider.oauth.token_url,
        scopes=provider.oauth.scopes,
        redirect_port=provider.oauth.redirect_port,
        client_id=resolved_id,
        client_secret=resolved_secret,
        extra_auth_params=provider.oauth.extra_auth_params,
    )


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _LoopbackServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/oauth/callback":
            self.send_response(404)
            self.end_headers()
            return
        query = parse_qs(parsed.query)
        self.server.result = {key: values[0] for key, values in query.items() if values}
        self.send_response(200)
        body = b"Authorization received. You can close this window."
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format: str, *args: Any) -> None:
        return


class _LoopbackServer(HTTPServer):
    result: dict[str, str] | None = None


class LoopbackReceiver:
    def __init__(self, port: int) -> None:
        self._server = _LoopbackServer(("127.0.0.1", port), _CallbackHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> LoopbackReceiver:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        with contextlib.suppress(Exception):
            self._server.shutdown()
        with contextlib.suppress(Exception):
            self._server.server_close()
        self._thread.join(timeout=2)

    def wait(self, timeout: float = AUTH_TIMEOUT_SEC) -> dict[str, str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.result is not None:
                return self._server.result
            time.sleep(0.05)
        raise OAuthError("not-ready", "the browser callback did not arrive in time")


def connect_loopback(
    config: OAuthConfig,
    slot: str,
    *,
    transport: httpx.BaseTransport | None = None,
    open_browser: bool = True,
    timeout: float = AUTH_TIMEOUT_SEC,
    verifier: str | None = None,
) -> OAuthTokens:
    resolved = resolve_client(config)
    state = new_state()
    code_verifier = verifier or pkce_verifier()
    authorize_url = build_authorize_url(resolved, state, code_verifier)
    with LoopbackReceiver(resolved.redirect_port) as receiver:
        if open_browser:
            webbrowser.open(authorize_url)
        payload = receiver.wait(timeout)
    if payload.get("error"):
        raise OAuthError("auth", str(payload.get("error_description") or payload["error"]))
    if payload.get("state") != state:
        raise OAuthError("auth", "state mismatch on the OAuth callback")
    code = payload.get("code")
    if not code:
        raise OAuthError("auth", "OAuth callback carried no authorization code")
    tokens = exchange_code(resolved, code, code_verifier, transport=transport)
    seal_tokens(slot, tokens)
    return tokens
