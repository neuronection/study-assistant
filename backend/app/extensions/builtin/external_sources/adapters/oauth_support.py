"""Shared OAuth token access for the provider adapters.

Plan 52 §13 / ADR-0052 §12: this rides ``nx_auth.oauth`` (the family
provider-delegation OAuth) rather than a hand-rolled flow. Adapters call
:func:`access_token` concurrently during scans, so the kit's **single-flight
refresh** is the point here — a rotating refresh token can never be consumed
twice, which is exactly the failure a per-call refresh invites.
"""

from __future__ import annotations

import threading
from typing import Any

import httpx
import nx_auth.oauth as nx_oauth

from .....services.study import cloud_oauth
from ....errors import ExtensionError

#: One kit ``TokenClient`` per source — the single-flight lock lives on the
#: instance, so a fresh client per call would lock nothing.
_CLIENTS: dict[str, Any] = {}
_CLIENTS_LOCK = threading.Lock()


def oauth_client(source: Any) -> nx_oauth.OAuthClient:
    try:
        return cloud_oauth.source_client_for(source.provider)
    except nx_oauth.OAuthError as error:
        raise ExtensionError(error.code, error.detail) from error


def _token_client(source: Any) -> Any:
    with _CLIENTS_LOCK:
        cached = _CLIENTS.get(source.id)
        if cached is not None:
            return cached
        client = nx_oauth.TokenClient(
            oauth_client(source),
            vault=cloud_oauth.source_vault_for(source.id),
            transport=cloud_oauth.HttpxTokenTransport(_http()),
        )
        _CLIENTS[source.id] = client
        return client


def _http() -> httpx.Client:
    return httpx.Client(timeout=20.0, follow_redirects=False)


def access_token(
    source: Any,
    transport: httpx.BaseTransport | None = None,
) -> tuple[nx_oauth.OAuthClient, str]:
    """The client and a usable access token, refreshing if needed.

    The refresh is single-flight and rotation-safe (the kit persists the
    rotated grant before discarding the old one). ``transport`` is accepted
    for call-site compatibility; the memoised client owns its own.
    """
    client = oauth_client(source)
    try:
        token = _token_client(source).access(source.id)
    except nx_oauth.OAuthError as error:
        raise ExtensionError(error.code, error.detail) from error
    return client, token


def bearer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def probe(source: Any, transport: httpx.BaseTransport | None = None) -> str:
    """`needs-config` / `expired` / `ok` — never raises."""
    try:
        client = oauth_client(source)
    except ExtensionError:
        return "needs-config"
    vault = cloud_oauth.source_vault_for(source.id)
    tokens = vault.find(source.id)
    if tokens is None:
        return "needs-config"
    if not tokens.expired():
        return "ok"
    if not tokens.refresh_token:
        return "expired"
    try:
        fresh = nx_oauth.refresh_tokens(
            client,
            refresh_token=tokens.refresh_token,
            transport=cloud_oauth.HttpxTokenTransport(_http()),
        )
    except nx_oauth.OAuthError:
        return "expired"
    vault.rotate(source.id, fresh)
    return "ok"


def forget(source_id: str) -> None:
    """Drop the memoised client on disconnect (stale grants must not linger)."""
    with _CLIENTS_LOCK:
        _CLIENTS.pop(source_id, None)
