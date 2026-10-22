"""Shared OAuth token access for the provider adapters (plan 86 B/C, ADR-215)."""

from __future__ import annotations

from typing import Any

import httpx

from .....core import oauth as oauth_core
from ....errors import ExtensionError


def oauth_config(source: Any) -> oauth_core.OAuthConfig:
    try:
        return oauth_core.oauth_config_from_catalog(source.provider)
    except oauth_core.OAuthError as error:
        raise ExtensionError(error.code, error.detail) from error


def access_token(
    source: Any,
    transport: httpx.BaseTransport | None = None,
) -> tuple[oauth_core.OAuthConfig, str]:
    config = oauth_config(source)
    slot = oauth_core.token_slot(source.id)
    tokens = oauth_core.load_tokens(slot)
    if tokens is None:
        raise ExtensionError("needs-secret", "connect this account first")
    if tokens.expired():
        if not tokens.refresh_token:
            raise ExtensionError("auth", "the OAuth token expired; reconnect the account")
        try:
            tokens = oauth_core.refresh_tokens(config, tokens, transport=transport)
        except oauth_core.OAuthError as error:
            raise ExtensionError(error.code, error.detail) from error
        oauth_core.seal_tokens(slot, tokens)
    return config, tokens.access_token


def bearer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def probe(source: Any, transport: httpx.BaseTransport | None = None) -> str:
    config = oauth_config(source)
    tokens = oauth_core.load_tokens(oauth_core.token_slot(source.id))
    if tokens is None:
        return "needs-config"
    if not tokens.expired():
        return "ok"
    if not tokens.refresh_token:
        return "expired"
    try:
        fresh = oauth_core.refresh_tokens(config, tokens, transport=transport)
    except oauth_core.OAuthError:
        return "expired"
    oauth_core.seal_tokens(oauth_core.token_slot(source.id), fresh)
    return "ok"
