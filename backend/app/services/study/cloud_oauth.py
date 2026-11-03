"""Study's wiring of ``nx_auth.oauth`` — the family provider-delegation OAuth.

Plan 52 §13 / ADR-0052 §3, §12. ``nx_auth.oauth`` is the **one**
implementation of authorization-code + PKCE for the family (auth-kit
``v0.5.0``); this module is study's thin adapter over its own storage —
nothing here re-implements a flow.

What it adapts:

* :class:`HttpxTokenTransport` — study talks HTTP with ``httpx``; the kit
  speaks a ``TokenTransport.post_form`` seam so it stays dependency-free and
  testable without a network.
* :class:`KeyringSealedStore` — the kit's :class:`SealedStore` wants atomic
  single-write custody; study's ``app.core.secrets`` is the only door to the
  OS keyring, so the sealed envelope round-trips through it (sealed twice —
  the kit's per-binding ``context`` envelope, then the at-rest cipher).
* :class:`KeyringStateStore` — the anti-bind-CSRF law (ADR-0052 Rev 3 E12):
  state is **single-use, expiring and bound to a principal**. Consumption is
  pop-first, so a replay or a foreign principal burns the record.

``app/core/oauth.py`` is unchanged and still powers the external-source
flows (Zotero/Drive/…); retiring it is the next stage. No token is ever
logged, returned or written to a row.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from nx_auth.oauth import (
    OAuthClient,
    OAuthError,
    StateRecord,
    TokenResponse,
    TokenSet,
    TokenVault,
)

from ...core import secrets as secret_store

__all__ = [
    "HttpxTokenTransport",
    "KeyringSealedStore",
    "KeyringStateStore",
    "OAuthError",
    "TokenSet",
    "client_for",
    "sealed_ref",
    "state_ref",
    "vault_for",
]

#: Where a link's sealed token envelope lives (the pointer, never the token).
_OAUTH_SLOT_SUFFIX = "oauth"
#: Where a link's in-flight authorize state lives.
_PENDING_SLOT_SUFFIX = "pending"


def sealed_ref(link_id: str) -> str:
    return f"calendar:{link_id}:{_OAUTH_SLOT_SUFFIX}"


def state_ref(link_id: str) -> str:
    return f"calendar:{link_id}:{_PENDING_SLOT_SUFFIX}"


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


class HttpxTokenTransport:
    """``httpx`` behind the kit's ``TokenTransport`` seam."""

    def __init__(self, client: httpx.AsyncClient | httpx.Client) -> None:
        self._client = client

    def post_form(
        self,
        url: str,
        data: Mapping[str, str],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> TokenResponse:
        """Blocking ``application/x-www-form-urlencoded`` POST.

        The kit's seam is synchronous by design (its single-flight refresh is
        thread-based). An async host calls this from a worker; study's
        calendar sync does exactly that through ``asyncio.to_thread`` where
        it matters.
        """
        try:
            response = self._client.post(
                url,
                data=dict(data),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    **dict(headers or {}),
                },
            )
        except httpx.HTTPError as exc:
            # A transport failure must never carry the URL's query — the
            # kit maps this to a typed `unreachable`, but detail is ours to
            # keep clean (ADR-0052 §9).
            raise OAuthError("unreachable", f"{type(exc).__name__}: transport failure") from exc
        payload: dict[str, Any]
        try:
            parsed = response.json()
            payload = dict(parsed) if isinstance(parsed, Mapping) else {}
        except ValueError:
            payload = {}
        return TokenResponse(
            status_code=response.status_code,
            data=payload or None,
            retry_after=response.headers.get("Retry-After"),
        )


# ---------------------------------------------------------------------------
# Custody
# ---------------------------------------------------------------------------


class KeyringSealedStore:
    """The kit's ``SealedStore`` over study's keyring-only secret module.

    ``set`` is one call to ``secret_store.set_secret`` — atomic and durable,
    which is what the kit's rotation-crash safety depends on: the old
    envelope survives until the new one is fully written.
    """

    def __init__(self, ref: str) -> None:
        self._ref = ref

    def get(self, binding_id: str) -> dict[str, str] | None:
        raw = secret_store.get_secret(self._ref)
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        return dict(parsed) if isinstance(parsed, Mapping) else None

    def set(self, binding_id: str, sealed: dict[str, str]) -> None:
        secret_store.set_secret(self._ref, json.dumps(sealed, separators=(",", ":")))

    def delete(self, binding_id: str) -> None:
        secret_store.delete_secret(self._ref)


def vault_for(link_id: str) -> TokenVault:
    """A :class:`TokenVault` bound to this link's keyring slot.

    The cipher is study's at-rest cipher (``nx_auth.atrest``); the kit seals
    each envelope with ``context="oauth:<link-id>"`` so a copied envelope
    cannot be replayed into another binding.
    """
    from ...core.secrets import cipher as atrest_cipher

    return TokenVault(KeyringSealedStore(sealed_ref(link_id)), cipher=atrest_cipher())


# ---------------------------------------------------------------------------
# State (the anti-bind-CSRF law)
# ---------------------------------------------------------------------------


@dataclass
class _StoredState:
    state: str
    principal_id: str
    code_verifier: str
    expires_at: str
    redirect_uri: str = ""
    created_at: str = ""
    extra: dict[str, Any] | None = None


class KeyringStateStore:
    """Single-use, expiring, principal-bound authorize state in the keyring.

    Consumption is **pop-first**: reading the record removes it even when the
    subsequent check fails, so a replay, a foreign principal or a lapsed
    window all burn the flow (ADR-0052 Rev 3 E12). Failures map to the kit's
    three distinct codes: ``invalid`` (replay/foreign), ``not-ready``
    (expired), ``canceled`` (explicitly discarded).
    """

    def __init__(self, ref: str) -> None:
        self._ref = ref

    def issue(self, record: StateRecord) -> None:
        secret_store.set_secret(
            self._ref,
            json.dumps(
                {
                    "state": record.state,
                    "principal_id": record.principal_id,
                    "code_verifier": record.code_verifier,
                    "expires_at": record.expires_at.isoformat(),
                    "redirect_uri": record.redirect_uri,
                    "created_at": (record.created_at or datetime.now(UTC)).isoformat(),
                    "extra": dict(record.extra or {}),
                },
                separators=(",", ":"),
            ),
        )

    def _pop(self) -> _StoredState | None:
        """Read AND clear in one step — the single-use guarantee."""
        raw = secret_store.get_secret(self._ref)
        secret_store.delete_secret(self._ref)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(data, Mapping):
            return None
        return _StoredState(
            state=str(data.get("state") or ""),
            principal_id=str(data.get("principal_id") or ""),
            code_verifier=str(data.get("code_verifier") or ""),
            expires_at=str(data.get("expires_at") or ""),
            redirect_uri=str(data.get("redirect_uri") or ""),
            created_at=str(data.get("created_at") or ""),
            extra=dict(data.get("extra") or {}),
        )

    def consume(self, state: str, *, principal_id: str) -> StateRecord:
        stored = self._pop()
        if stored is None:
            raise OAuthError("invalid", "no OAuth flow is pending for this link")
        if not stored.state or stored.state != state:
            raise OAuthError("invalid", "OAuth state mismatch")
        if stored.principal_id != principal_id:
            # Bind-CSRF: the completing principal is not the one that started.
            raise OAuthError("invalid", "OAuth state was issued to a different user")
        try:
            expires = datetime.fromisoformat(stored.expires_at)
        except ValueError:
            expires = datetime.now(UTC) - timedelta(seconds=1)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if datetime.now(UTC) > expires:
            raise OAuthError("not-ready", "OAuth flow expired; start again")
        return StateRecord(
            state=stored.state,
            principal_id=stored.principal_id,
            code_verifier=stored.code_verifier,
            expires_at=expires,
            redirect_uri=stored.redirect_uri,
            created_at=datetime.fromisoformat(stored.created_at)
            if stored.created_at
            else None,
            extra=stored.extra or {},
        )

    def discard(self, state: str) -> None:
        secret_store.delete_secret(self._ref)


# ``_pop`` uses ``timedelta`` for the malformed-expiry fail-closed path.
from datetime import timedelta  # noqa: E402  (kept local: only the store needs it)

# ---------------------------------------------------------------------------
# Client construction (providers are data)
# ---------------------------------------------------------------------------


def client_for(
    provider_row: Any,
    *,
    client_id: str,
    redirect_uri: str,
    scopes: tuple[str, ...] | list[str],
    client_secret: str | None = None,
) -> OAuthClient:
    """Build the kit's :class:`OAuthClient` from the family catalog row.

    Endpoints and provider quirks are **catalog data** (ADR-0052 §11) — this
    never branches on a provider name.
    """
    spec = getattr(provider_row, "oauth", None)
    if spec is None:
        raise OAuthError("invalid", f"{getattr(provider_row, 'id', 'provider')} does not use OAuth")
    return OAuthClient(
        client_id=client_id,
        token_url=spec.token_url,
        redirect_uri=redirect_uri,
        authorize_url=spec.authorize_url,
        scopes=tuple(scopes),
        client_secret=client_secret or None,
        extra_auth_params=dict(getattr(spec, "extra_auth_params", {}) or {}),
    )
