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

import contextlib
import json
import threading
import time
import webbrowser
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import nx_auth.oauth as nx_oauth
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
    "LoopbackReceiver",
    "OAuthError",
    "TokenSet",
    "client_for",
    "connect_loopback",
    "sealed_ref",
    "source_client_for",
    "source_ref",
    "source_vault_for",
    "state_ref",
    "token_status",
    "vault_for",
]

#: Where a link's sealed token envelope lives (the pointer, never the token).
_OAUTH_SLOT_SUFFIX = "oauth"
#: Where a link's in-flight authorize state lives.
_PENDING_SLOT_SUFFIX = "pending"


def sealed_ref(link_id: str) -> str:
    return f"calendar:{link_id}:{_OAUTH_SLOT_SUFFIX}"


def source_ref(source_id: str) -> str:
    """Where an external-source's grant lives (``source:<id>:oauth``)."""
    return f"source:{source_id}:{_OAUTH_SLOT_SUFFIX}"


def source_vault_for(source_id: str) -> TokenVault:
    """The vault for an external source (Zotero/Drive/…)."""
    from ...core.secrets import cipher as atrest_cipher

    return TokenVault(KeyringSealedStore(source_ref(source_id)), cipher=atrest_cipher())


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




# ---------------------------------------------------------------------------
# Loopback bind (the one flow the kit deliberately leaves to the host)
# ---------------------------------------------------------------------------

AUTH_TIMEOUT_SEC = 180.0


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
    """One-shot listener on 127.0.0.1 only (RFC 8252)."""

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
    client: OAuthClient,
    vault: TokenVault,
    binding_id: str,
    *,
    transport: HttpxTokenTransport,
    open_browser: bool = True,
    timeout: float = AUTH_TIMEOUT_SEC,
) -> TokenSet:
    """Browser + one-shot loopback + exchange + seal, in one call.

    PKCE, the authorize URL, the code exchange and the custody all come from
    ``nx_auth.oauth`` — this adds only the browser and the listener, which the
    kit deliberately leaves to the host.
    """
    state = nx_oauth.new_state()
    verifier = nx_oauth.new_verifier()
    authorize_url = nx_oauth.build_authorize_url(
        client, state=state, code_challenge=nx_oauth.code_challenge(verifier)
    )
    with LoopbackReceiver(_port_of(client.redirect_uri)) as receiver:
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
    tokens = nx_oauth.exchange_code(
        client, code=code, code_verifier=verifier, transport=transport
    )
    vault.seal(binding_id, tokens)
    return tokens


def _port_of(redirect_uri: str) -> int:
    parsed = urlparse(redirect_uri)
    return parsed.port or (443 if parsed.scheme == "https" else 80)


def source_client_for(
    provider_id: str,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> OAuthClient:
    """The kit client for an external source, from its own provider catalog.

    Client ids are deployment config read via the provider's declared env
    name — never catalog data, never a secret in a native client.
    """
    import os

    from ...extensions.builtin.external_sources.providers import get_provider

    provider = get_provider(provider_id)
    oauth = getattr(provider, "oauth", None)
    if oauth is None:
        raise OAuthError("invalid", f"provider '{provider_id}' does not use OAuth")
    resolved_id = client_id or os.environ.get(oauth.client_id_env, "")
    if not resolved_id:
        raise OAuthError(
            "needs-config",
            f"set {oauth.client_id_env} to the OAuth client id registered for this app",
        )
    return OAuthClient(
        client_id=resolved_id,
        token_url=oauth.token_url,
        redirect_uri=f"http://127.0.0.1:{oauth.redirect_port}/oauth/callback",
        authorize_url=oauth.authorize_url,
        scopes=tuple(oauth.scopes),
        client_secret=client_secret or os.environ.get(oauth.client_secret_env),
        extra_auth_params=dict(getattr(oauth, "extra_auth_params", {}) or {}),
    )


def token_status(tokens: TokenSet | None, *, now: datetime | None = None) -> str:
    """`needs-config` / `expired` / `ok` — the host's status vocabulary."""
    if tokens is None:
        return "needs-config"
    return "expired" if tokens.expired(now=now) else "ok"


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
