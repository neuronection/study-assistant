"""Study's host adapter for cloud calendars (ADR-0052 / plan 52).

The shared engine lives in :mod:`app.extensions.cloud.cloud_calendar`; this
module is the *host*: account rows, keyring custody, OAuth, the plan-item
mapping and sync orchestration. Nothing provider-specific is hard-coded here
— providers, protocols, endpoints and scopes come from the family catalog in
:mod:`app.extensions.cloud.cloud_providers`.

Mapping law (ADR-0052 §6):

* only ``exam``, ``deadline`` and ``milestone`` plan items are projected by
  default; every study task on a calendar is noise;
* a projection is an all-day event whose canonical end is exclusive
  (``due_date + 1 day``), categories carry the plan kind;
* inbound events become plan items only when their categories (or an explicit
  ``accept_all`` link option) say they are study events — never the whole
  personal calendar;
* completed plan items are tombstones for the calendar: the remote event is
  removed, the plan item stays.

Credentials never enter the database: OAuth token sets and app passwords live
in the OS keyring under ``calendar:<link-id>:*``; ``calendar_links.secret_ref``
is a pointer.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol, cast
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import nx_auth.oauth as nx_oauth
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core import secrets as secret_store
from ...core.vocab import CalendarDirection, CalendarStatus, PlanItemKind, PlanItemOrigin
from ...domain import payloads
from ...domain.models import (
    CalendarEventLink,
    CalendarLink,
    Course,
    PlanItem,
    utcnow,
)
from ...extensions import polite_http
from ...extensions.cloud import cloud_calendar as calendar
from ...extensions.cloud.cloud_providers import (
    CatalogError,
    Provider,
    build_base_url,
    default_catalog,
    provider_rows,
)
from . import cloud_oauth

CALENDAR_SERVICE = "calendar"
DEFAULT_REDIRECT_PORT = 53690
SYNC_PAST_DAYS = 14
SYNC_FUTURE_DAYS = 400
MAX_PAGES = 10
MAX_TITLE = 300
MAX_DETAIL = 500
MAX_DISCOVERED = 50
PROJECTED_KINDS = ("exam", "deadline", "milestone")
ACCEPT_CATEGORIES = ("EXAM", "EXAMINATION", "DEADLINE", "MIDTERM", "FINAL")
#: Protocols whose account exposes a calendar list (CalDAV PROPFIND, Google
#: ``calendarList``, Graph ``me/calendars``) — the bind form's picker.
DISCOVERABLE_PROTOCOLS = ("caldav", "google-calendar", "graph-calendar")
EXAM_PATTERN = re.compile(
    r"\b(exam|final|midterm|test|quiz|prüfung|klausur|testat|εξέταση|διαγώνισμα)\b",
    re.IGNORECASE,
)

_locks: dict[str, asyncio.Lock] = {}


class CalendarSyncError(Exception):
    """Typed host error (API maps ``code`` to a status)."""

    def __init__(self, code: str, detail: str = "", *, status: int = 400) -> None:
        self.code = code
        self.detail = detail[:500]
        self.status = status
        super().__init__(f"{code}: {self.detail}" if self.detail else code)


@dataclass
class SyncReport:
    status: str = CalendarStatus.OK.value
    created_remote: int = 0
    updated_remote: int = 0
    deleted_remote: int = 0
    created_local: int = 0
    updated_local: int = 0
    deleted_local: int = 0
    unlinked: int = 0
    conflicts: int = 0
    skipped: int = 0
    suggested: int = 0
    linked_existing: int = 0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "created_remote": self.created_remote,
            "updated_remote": self.updated_remote,
            "deleted_remote": self.deleted_remote,
            "created_local": self.created_local,
            "updated_local": self.updated_local,
            "deleted_local": self.deleted_local,
            "unlinked": self.unlinked,
            "conflicts": self.conflicts,
            "skipped": self.skipped,
            "suggested": self.suggested,
            "linked_existing": self.linked_existing,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Catalog / lookups
# ---------------------------------------------------------------------------

#: One bind-form field, derived from the row's ``protocol`` + ``authKinds`` +
#: ``baseUrlRequired`` — never from a provider name (plan 52 §12). ``key`` is
#: the ``CalendarLinkIn`` payload key; ``label_key`` is an i18n suffix under
#: ``settings.calendar.``; ``kind`` is the input type with ``calendar`` being
#: the discovery-backed picker; ``auth_kind`` narrows a field to one chosen
#: auth kind (``None`` = render always).
def setup_fields(provider_row: Provider) -> list[dict[str, Any]]:
    spec = provider_row.service(CALENDAR_SERVICE)
    protocol = spec.protocol
    fields: list[dict[str, Any]] = []
    if protocol == "caldav":
        fields.append(
            {
                "key": "base_url",
                "kind": "url",
                "required": provider_row.base_url_required,
                "label_key": "baseUrl",
                "placeholder": "https://cloud.example.com",
                "autocomplete": None,
                "auth_kind": None,
            }
        )
    if protocol == "ics":
        fields.append(
            {
                "key": "calendar_url",
                "kind": "url",
                "required": True,
                "label_key": "feedUrl",
                "placeholder": "https://example.com/calendar.ics",
                "autocomplete": None,
                "auth_kind": None,
            }
        )
    if "app-password" in provider_row.auth_kinds:
        fields.append(
            {
                "key": "username",
                "kind": "text",
                "required": False,
                "label_key": "username",
                "placeholder": None,
                "autocomplete": "username",
                "auth_kind": "app-password",
            }
        )
        fields.append(
            {
                "key": "secret",
                "kind": "secret",
                "required": True,
                "label_key": "appPassword",
                "placeholder": None,
                "autocomplete": "new-password",
                "auth_kind": "app-password",
            }
        )
    if "token" in provider_row.auth_kinds:
        fields.append(
            {
                "key": "secret",
                "kind": "secret",
                "required": True,
                "label_key": "token",
                "placeholder": None,
                "autocomplete": "new-password",
                "auth_kind": "token",
            }
        )
    if protocol in DISCOVERABLE_PROTOCOLS:
        fields.append(
            {
                "key": "calendar",
                "kind": "calendar",
                "required": protocol == "caldav",
                "label_key": "calendar",
                "placeholder": None,
                "autocomplete": None,
                "auth_kind": None,
                # Payload key for the manual paste fallback (a CalDAV
                # collection URL); OAuth providers pick from the list only.
                "manual_key": "calendar_url" if protocol == "caldav" else None,
            }
        )
    return fields


def supports_discovery(provider_row: Provider) -> bool:
    return provider_row.service(CALENDAR_SERVICE).protocol in DISCOVERABLE_PROTOCOLS


def catalog_provider_rows() -> list[dict[str, Any]]:
    catalog = default_catalog()
    rows: list[dict[str, Any]] = []
    for row in provider_rows(catalog, CALENDAR_SERVICE):
        provider_row = catalog.get(row["id"])
        enriched = dict(row)
        enriched["setupFields"] = setup_fields(provider_row)
        enriched["supportsDiscovery"] = supports_discovery(provider_row)
        rows.append(enriched)
    return rows


def provider(provider_id: str) -> Provider:
    try:
        return default_catalog().get(provider_id)
    except CatalogError as exc:
        raise CalendarSyncError("invalid", str(exc), status=422) from exc


def list_links(session: Session, profile_id: str) -> list[CalendarLink]:
    return list(
        session.scalars(
            select(CalendarLink)
            .where(CalendarLink.profile_id == profile_id)
            .order_by(CalendarLink.created_at)
        )
    )


def get_link(session: Session, profile_id: str, link_id: str) -> CalendarLink:
    link = session.get(CalendarLink, link_id)
    if link is None or link.profile_id != profile_id:
        raise CalendarSyncError("not-found", "calendar link not found", status=404)
    return link


def _secret_slot(link_id: str, kind: str) -> str:
    return f"calendar:{link_id}:{kind}"


def _pending_slot(link_id: str) -> str:
    return _secret_slot(link_id, "pending")


def _oauth_slot(link_id: str) -> str:
    return _secret_slot(link_id, "oauth")


def _connection_slot(link_id: str, auth_kind: str) -> str:
    return _secret_slot(link_id, "password" if auth_kind == "app-password" else "token")


# ---------------------------------------------------------------------------
# Link lifecycle
# ---------------------------------------------------------------------------


def _resolve_calendar_url(
    provider_row: Provider,
    *,
    base_url: str | None,
    calendar_id: str | None,
    calendar_url: str | None,
    username: str | None,
) -> str | None:
    spec = provider_row.service(CALENDAR_SERVICE)
    if spec.protocol == "ics":
        return calendar_url or base_url
    if spec.protocol != "caldav":
        return None
    if calendar_url:
        return calendar_url.rstrip("/") + "/"
    root = build_base_url(provider_row, CALENDAR_SERVICE, base_url, username)
    if calendar_id:
        return f"{root}{calendar_id.strip('/')}/"
    return root


def create_link(
    session: Session,
    *,
    profile_id: str,
    course_id: str,
    provider_id: str,
    label: str,
    direction: str = "push",
    base_url: str | None = None,
    calendar_id: str | None = None,
    calendar_url: str | None = None,
    username: str | None = None,
    secret: str | None = None,
    auth_kind: str | None = None,
    options: dict[str, Any] | None = None,
) -> CalendarLink:
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile_id:
        raise CalendarSyncError("not-found", "course not found", status=404)
    provider_row = provider(provider_id)
    if not provider_row.supports(CALENDAR_SERVICE):
        raise CalendarSyncError("invalid", f"{provider_id} has no calendar service", status=422)
    try:
        mode = CalendarDirection(direction)
    except ValueError as exc:
        raise CalendarSyncError("invalid", f"unknown direction {direction!r}", status=422) from exc
    chosen_kind = auth_kind or provider_row.auth_kinds[0]
    if chosen_kind not in provider_row.auth_kinds:
        raise CalendarSyncError(
            "invalid", f"{chosen_kind} is not an auth kind of {provider_id}", status=422
        )
    protocol = provider_row.service(CALENDAR_SERVICE).protocol
    if protocol == "ics" and "token" in provider_row.auth_kinds:
        # A private ICS URL carries its token in the query string; it is a
        # bearer credential, so it goes to the keyring and the row keeps only
        # the sanitized display URL (ADR-0052 §2/§9).
        candidate = calendar_url or base_url
        parsed = urlparse(candidate or "")
        if secret or parsed.query:
            secret = secret or candidate
            if candidate:
                calendar_url = parsed._replace(query="", fragment="").geturl()
                base_url = None
            chosen_kind = "token"
    auth_kind = chosen_kind
    if provider_row.base_url_required and not base_url and not calendar_url:
        raise CalendarSyncError("invalid", f"{provider_row.label} needs a base URL", status=422)
    resolved_url = _resolve_calendar_url(
        provider_row,
        base_url=base_url,
        calendar_id=calendar_id,
        calendar_url=calendar_url,
        username=username,
    )
    if provider_row.service(CALENDAR_SERVICE).protocol == "caldav" and not resolved_url:
        raise CalendarSyncError("invalid", "a CalDAV calendar URL is required", status=422)

    link_id = str(uuid4())
    secret_ref: str | None = None
    if auth_kind in ("app-password", "token"):
        if not secret:
            raise CalendarSyncError(
                "needs-secret", f"{provider_row.label} needs an app password or token", status=422
            )
        secret_ref = _connection_slot(link_id, auth_kind)
        secret_store.set_secret(secret_ref, secret)
    elif auth_kind == "oauth2":
        secret_ref = _oauth_slot(link_id)

    merged_options: dict[str, Any] = {
        "kinds": list(PROJECTED_KINDS),
        # E8: inbound is attributable-only by default. A user who wants
        # category matching lists the categories themselves (explicit pick).
        "acceptCategories": [],
        "acceptAll": False,
        "conflictPolicy": "skip",
        "deletionPolicy": "keep-local",
    }
    if username:
        merged_options["username"] = username
    merged_options.update(options or {})

    preset = "read" if mode == CalendarDirection.PULL else "write"
    scopes = list(provider_row.oauth_scopes(CALENDAR_SERVICE, preset))
    link = CalendarLink(
        id=link_id,
        profile_id=profile_id,
        course_id=course_id,
        provider=provider_id,
        auth_kind=auth_kind,
        label=label,
        account_label=None,
        calendar_id=calendar_id,
        calendar_url=resolved_url,
        base_url=base_url,
        scopes=scopes or None,
        secret_ref=secret_ref,
        direction=mode.value,
        enabled=True,
        status=(
            CalendarStatus.NEEDS_AUTH.value
            if auth_kind == "oauth2"
            else CalendarStatus.OK.value
        ),
        options=merged_options,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(link)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if secret_ref:
            secret_store.delete_secret(secret_ref)
        raise CalendarSyncError(
            "invalid",
            "this calendar is already bound to the course",
            status=409,
        ) from exc
    session.refresh(link)
    return link


def update_link(
    session: Session,
    link: CalendarLink,
    *,
    label: str | None = None,
    direction: str | None = None,
    calendar_id: str | None = None,
    calendar_url: str | None = None,
    enabled: bool | None = None,
    options: dict[str, Any] | None = None,
) -> CalendarLink:
    if label is not None:
        link.label = label[:200]
    if direction is not None:
        try:
            link.direction = CalendarDirection(direction).value
        except ValueError as exc:
            raise CalendarSyncError(
                "invalid", f"unknown direction {direction!r}", status=422
            ) from exc
    if calendar_id is not None:
        link.calendar_id = calendar_id or None
    if calendar_url is not None:
        link.calendar_url = calendar_url or None
    if enabled is not None:
        link.enabled = enabled
    if options is not None:
        merged = dict(link.options or {})
        merged.update(options)
        link.options = cast(payloads.CalendarLinkOptions, merged)
    link.updated_at = utcnow()
    session.commit()
    session.refresh(link)
    return link


def delete_link(session: Session, link: CalendarLink) -> None:
    for kind in ("oauth", "password", "token", "pending"):
        secret_store.delete_secret(_secret_slot(link.id, kind))
    cloud_oauth.vault_for(link.id).clear(link.id)
    cloud_oauth.KeyringStateStore(cloud_oauth.state_ref(link.id)).discard("")
    _drop_token_client(link.id)
    session.delete(link)
    session.commit()


def set_secret(session: Session, link: CalendarLink, value: str) -> CalendarLink:
    if link.auth_kind == "oauth2":
        raise CalendarSyncError(
            "invalid", "OAuth links are bound through the OAuth flow", status=409
        )
    slot = _connection_slot(link.id, link.auth_kind)
    secret_store.set_secret(slot, value)
    link.secret_ref = slot
    link.status = CalendarStatus.OK.value
    link.last_error = None
    link.updated_at = utcnow()
    session.commit()
    session.refresh(link)
    return link


# ---------------------------------------------------------------------------
# OAuth
#


def oauth_client(provider_row: Provider, link: _CredentialContext | None = None) -> Any:
    """The kit's ``OAuthClient`` from the family catalog row.

    Endpoints and provider quirks are catalog data (ADR-0052 §11) — this
    never branches on a provider name.
    """
    if provider_row.oauth is None:
        raise CalendarSyncError("invalid", f"{provider_row.id} does not use OAuth", status=422)
    prefix = f"SA_{provider_row.id.upper().replace('-', '_')}"
    client_id = os.environ.get(f"{prefix}_CLIENT_ID", "")
    if not client_id:
        raise CalendarSyncError(
            "needs-config",
            f"set {prefix}_CLIENT_ID to the OAuth client registered for this app",
            status=409,
        )
    pull = link is not None and link.direction == CalendarDirection.PULL.value
    preset = "read" if pull else "write"
    return cloud_oauth.client_for(
        provider_row,
        client_id=client_id,
        redirect_uri=_redirect_uri(),
        scopes=provider_row.oauth_scopes(CALENDAR_SERVICE, preset),
        client_secret=os.environ.get(f"{prefix}_CLIENT_SECRET"),
    )


def _redirect_uri() -> str:
    """Where the provider sends the user back — deployment-aware.

    * **Desktop/local** (no ``SA_APP_URL``): a loopback redirect
      (RFC 8252). The browser and the app share a machine, so the
      one-shot listener on 127.0.0.1 receives the callback.
    * **Web/server** (``SA_APP_URL`` set): the server's own callback route.
      The user's browser runs elsewhere, so a loopback redirect would land
      on *their* localhost and the code would never reach us.
    """
    from app.core.config import get_settings

    app_url = (get_settings().app_url or os.environ.get("SA_APP_URL") or "").rstrip("/")
    if app_url:
        return f"{app_url}/api/v1/calendar/oauth/callback"
    port = int(os.environ.get("SA_CALENDAR_REDIRECT_PORT", str(DEFAULT_REDIRECT_PORT)))
    return f"http://127.0.0.1:{port}/oauth/callback"


def is_web_oauth() -> bool:
    """True when OAuth must complete through the server callback route."""
    from app.core.config import get_settings

    return bool((get_settings().app_url or os.environ.get("SA_APP_URL") or "").strip())


def oauth_start(link: CalendarLink, *, profile_id: str) -> dict[str, str]:
    """Begin one bind flow.

    ``state`` is single-use, expiring and bound to ``profile_id`` — the
    anti-bind-CSRF law (Rev 3 E12), enforced by the kit's state store.
    """
    provider_row = provider(link.provider)
    client = oauth_client(provider_row, link)
    store = cloud_oauth.KeyringStateStore(cloud_oauth.state_ref(link.id))
    try:
        offer = nx_oauth.authorize(
            client,
            store=store,
            principal_id=profile_id,
            extra={"scopes": list(client.scopes), "link_id": link.id},
        )
    except nx_oauth.OAuthError as exc:
        raise CalendarSyncError(exc.code, exc.detail, status=409) from exc
    # The state carries a non-secret link-id prefix so a server callback can
    # find the binding when the provider echoes only `code`+`state`. The
    # security comes from the nonce half (single-use, principal-bound), not
    # from hiding the link id.
    composite = f"{link.id}.{offer.record.state}"
    return {
        "authorize_url": offer.authorize_url,
        "redirect_uri": client.redirect_uri,
        "state": composite,
    }


def link_id_from_state(state: str) -> str | None:
    """The link id a composite state points at (``<link-id>.<nonce>``)."""
    link_id, sep, _nonce = (state or "").partition(".")
    return link_id if sep and link_id else None


def oauth_complete(
    session: Session,
    link: CalendarLink,
    *,
    code: str,
    state: str,
    profile_id: str,
    transport: httpx.BaseTransport | None = None,
) -> CalendarLink:
    """Consume the state, exchange the code once, seal the token set.

    Consumption is pop-first inside the store: success, expiry, mismatch and
    replay all burn the flow, so a bind can never complete twice (E12).
    """
    provider_row = provider(link.provider)
    client = oauth_client(provider_row, link)
    store = cloud_oauth.KeyringStateStore(cloud_oauth.state_ref(link.id))
    # The caller holds a composite `<link-id>.<nonce>`; the store keyed the
    # bare nonce. The prefix is a routing hint only — the nonce is the secret.
    nonce = state.partition(".")[2] or state
    try:
        record = store.consume(nonce, principal_id=profile_id)
    except nx_oauth.OAuthError as exc:
        raise CalendarSyncError(exc.code, exc.detail, status=409) from exc

    token_transport = cloud_oauth.HttpxTokenTransport(_token_http(transport))
    try:
        tokens = nx_oauth.exchange_code(
            client,
            code=code,
            code_verifier=record.code_verifier,
            transport=token_transport,
            redirect_uri=record.redirect_uri,
        )
    except nx_oauth.OAuthError as exc:
        raise CalendarSyncError(exc.code, exc.detail, status=409) from exc

    cloud_oauth.vault_for(link.id).seal(link.id, tokens)
    link.scopes = list(client.scopes)
    link.status = CalendarStatus.OK.value
    link.last_error = None
    link.consecutive_failures = 0
    link.updated_at = utcnow()
    session.commit()
    session.refresh(link)
    return link


def _token_http(transport: httpx.BaseTransport | None) -> httpx.Client:
    """A blocking client for the kit's synchronous token seam."""
    if transport is not None:
        return httpx.Client(transport=transport)
    return httpx.Client(timeout=20.0, follow_redirects=False)


# ---------------------------------------------------------------------------
# Transport wiring
# ---------------------------------------------------------------------------


class _CredentialContext(Protocol):
    """What the auth/guard helpers read off a link row (or a discovery target)."""

    @property
    def id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def auth_kind(self) -> str: ...

    @property
    def direction(self) -> str: ...

    @property
    def base_url(self) -> str | None: ...

    @property
    def calendar_url(self) -> str | None: ...

    @property
    def secret_ref(self) -> str | None: ...

    @property
    def options(self) -> Mapping[str, object] | None: ...


def _auth_header_provider(link: _CredentialContext, provider_row: Provider) -> Callable[[], str]:
    def header() -> str:
        if link.auth_kind == "oauth2":
            try:
                # Single-flight refresh (the reason this rides the kit): two
                # concurrent syncs await ONE refresh, so a rotating refresh
                # token can never be consumed twice.
                access = _token_client(provider_row, link).access(link.id)
            except nx_oauth.OAuthError as exc:
                raise CalendarSyncError(exc.code, exc.detail, status=409) from exc
            return f"Bearer {access}"
        slot = link.secret_ref or _connection_slot(link.id, link.auth_kind)
        secret = secret_store.get_secret(slot)
        if not secret:
            raise CalendarSyncError(
                "needs-secret", "this calendar has no stored credential", status=409
            )
        if link.auth_kind == "app-password":
            username = str((link.options or {}).get("username") or "")
            return calendar.basic_auth(username, secret)
        return calendar.bearer_auth(secret)

    return header



#: One :class:`nx_auth.oauth.TokenClient` per bound account. The kit's
#: single-flight refresh lives on the instance, so it must be SHARED across
#: concurrent syncs — a fresh client per call would lock nothing.
_token_clients: dict[str, Any] = {}
_token_clients_lock = __import__("threading").Lock()


def _token_client(provider_row: Provider, link: _CredentialContext) -> Any:
    with _token_clients_lock:
        cached = _token_clients.get(link.id)
        if cached is not None:
            return cached
        client = oauth_client(provider_row, link)
        token_client = nx_oauth.TokenClient(
            client,
            vault=cloud_oauth.vault_for(link.id),
            transport=cloud_oauth.HttpxTokenTransport(_token_http(None)),
        )
        _token_clients[link.id] = token_client
        return token_client


def _drop_token_client(link_id: str) -> None:
    """Forget the cached client on unbind/re-bind (stale grants must not linger)."""
    with _token_clients_lock:
        _token_clients.pop(link_id, None)


def _allowed_domains(link: _CredentialContext, provider_row: Provider) -> set[str]:
    """Token-bearing destinations for this binding.

    Catalog OAuth providers carry a closed domain list; self-hosted CalDAV /
    WebDAV / ICS bindings carry the host the user typed.
    """
    if provider_row.domains:
        return {domain.lower() for domain in provider_row.domains}
    for candidate in (link.base_url, link.calendar_url):
        host = urlparse(candidate or "").hostname
        if host:
            return {host.lower()}
    return set()


def _guarded_client(
    link: _CredentialContext, provider_row: Provider, *, timeout: float
) -> httpx.AsyncClient:
    """A client whose every request is SSRF-guarded and domain-scoped.

    Mirrors the family polite runtime's connect path (`check_url` +
    `pinned_request_parts`) without applying GET-only politeness (robots,
    conditional GET) to calendar writes. Private addresses are allowed only
    for self-hosted bindings whose host the user supplied — a Google/Graph
    request can never resolve to a LAN address.
    """
    domains = _allowed_domains(link, provider_row)
    self_hosted = link.provider in ("nextcloud", "caldav", "webdav", "ics") or bool(link.base_url)
    guard_config = polite_http.NetGuardConfig(allow_private=self_hosted)

    async def guard_request(request: httpx.Request) -> None:
        host = (request.url.host or "").lower()
        if domains and not any(polite_http.host_matches_domain(host, domain) for domain in domains):
            raise CalendarSyncError(
                "net-denied", f"host {host} is outside this calendar's declared domains"
            )
        try:
            resolved = await polite_http.assert_safe_url(str(request.url), config=guard_config)
        except polite_http.PoliteHttpError as error:
            raise CalendarSyncError(error.code, error.detail) from error
        if not resolved:
            return
        url, headers, extensions = polite_http.pinned_request_parts(str(request.url), resolved)
        request.url = httpx.URL(url)
        for name, value in headers.items():
            request.headers[name] = value
        request.extensions.update(extensions)

    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        event_hooks={"request": [guard_request]},
    )

def _transport(
    link: CalendarLink, provider_row: Provider, client: httpx.AsyncClient
) -> calendar.CalendarTransport:
    spec = provider_row.service(CALENDAR_SERVICE)
    auth = _auth_header_provider(link, provider_row)
    if spec.protocol == "caldav":
        calendar_url = link.calendar_url or _resolve_calendar_url(
            provider_row,
            base_url=link.base_url,
            calendar_id=link.calendar_id,
            calendar_url=link.calendar_url,
            username=str((link.options or {}).get("username") or "") or None,
        )
        if not calendar_url:
            raise CalendarSyncError("invalid", "the calendar has no CalDAV URL", status=409)
        return calendar.CalDavCalendarTransport(
            client, calendar_url, auth=auth, writable=spec.writable
        )
    if spec.protocol == "ics":
        feed = None
        if link.auth_kind in ("token", "app-password") and link.secret_ref:
            feed = secret_store.get_secret(link.secret_ref)
        feed = feed or link.calendar_url or link.base_url
        if not feed:
            raise CalendarSyncError("invalid", "the ICS feed has no URL", status=409)
        return calendar.IcsCalendarTransport(client, feed, auth=auth)
    if spec.protocol == "google-calendar":
        return calendar.GoogleCalendarTransport(
            client,
            link.calendar_id or "primary",
            api_base=spec.api_base or "https://www.googleapis.com/calendar/v3",
            auth=auth,
        )
    if spec.protocol == "graph-calendar":
        return calendar.GraphCalendarTransport(
            client,
            link.calendar_id or "",
            api_base=spec.api_base or "https://graph.microsoft.com/v1.0",
            auth=auth,
        )
    raise CalendarSyncError("unsupported", f"unknown protocol {spec.protocol!r}", status=422)


# ---------------------------------------------------------------------------
# Calendar discovery (plan 52 §9 M1 / §12 rule 4)
#
# Powers the bind form's picker: CalDAV PROPFIND via the engine's
# ``discover_calendars``, Google ``calendarList``, Graph ``me/calendars``.
# The credential never persists and never reaches the response — it exists
# only inside the transport for one bounded request.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DiscoveryTarget:
    """The subset of a link row the guarded client and auth provider read."""

    id: str = ""
    provider: str = ""
    auth_kind: str = "none"
    direction: str = "push"
    base_url: str | None = None
    calendar_url: str | None = None
    username: str | None = None
    secret: str | None = None
    secret_ref: str | None = None
    options: Mapping[str, object] | None = None


def _sanitize_feed_url(url: str | None) -> str | None:
    """Scheme + host + path only: a query string is a bearer credential (C4)."""
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return parsed._replace(query="", fragment="").geturl()


def _discovery_target(
    *,
    link: CalendarLink | None = None,
    provider_id: str | None = None,
    auth_kind: str | None = None,
    base_url: str | None = None,
    calendar_url: str | None = None,
    username: str | None = None,
    secret: str | None = None,
) -> tuple[Provider, _DiscoveryTarget]:
    if link is not None:
        provider_row = provider(link.provider)
        return provider_row, _DiscoveryTarget(
            id=link.id,
            provider=link.provider,
            auth_kind=link.auth_kind,
            direction=link.direction,
            base_url=link.base_url,
            calendar_url=link.calendar_url,
            username=str((link.options or {}).get("username") or "") or None,
            secret_ref=link.secret_ref,
            options=link.options,
        )
    if not provider_id:
        raise CalendarSyncError("invalid", "a provider or an existing link is required", status=422)
    provider_row = provider(provider_id)
    if not provider_row.supports(CALENDAR_SERVICE):
        raise CalendarSyncError("invalid", f"{provider_id} has no calendar service", status=422)
    kind = auth_kind or provider_row.auth_kinds[0]
    if kind not in provider_row.auth_kinds:
        raise CalendarSyncError(
            "invalid", f"{kind} is not an auth kind of {provider_id}", status=422
        )
    return provider_row, _DiscoveryTarget(
        provider=provider_row.id,
        auth_kind=kind,
        base_url=base_url,
        calendar_url=calendar_url,
        username=username,
        secret=secret,
        options={"username": username} if username else None,
    )


def _discovery_auth(
    target: _DiscoveryTarget, provider_row: Provider
) -> Callable[[], str] | None:
    if target.auth_kind == "oauth2":
        # OAuth discovery rides the stored token set of an existing link.
        return _auth_header_provider(target, provider_row)
    secret = target.secret
    if target.secret_ref:
        secret = secret or secret_store.get_secret(target.secret_ref)
    if not secret:
        if target.auth_kind == "none":
            return None
        raise CalendarSyncError(
            "needs-secret", "a credential is required to list calendars", status=409
        )
    if target.auth_kind == "app-password":
        return lambda: calendar.basic_auth(target.username or "", secret)
    return lambda: calendar.bearer_auth(secret)


async def _discover_rows(
    target: _DiscoveryTarget, provider_row: Provider, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    spec = provider_row.service(CALENDAR_SERVICE)
    protocol = spec.protocol
    if protocol == "caldav":
        root = target.calendar_url or _resolve_calendar_url(
            provider_row,
            base_url=target.base_url,
            calendar_id=None,
            calendar_url=None,
            username=target.username,
        )
        if not root:
            raise CalendarSyncError(
                "invalid", "a base URL is required to list calendars", status=422
            )
        transport = calendar.CalDavCalendarTransport(
            client, root, auth=_discovery_auth(target, provider_row), writable=False
        )
        rows = await transport.discover_calendars()
        return [
            {
                "id": str(row.get("id") or "")[:200],
                "name": str(row.get("name") or row.get("id") or "")[:200],
                "url": _sanitize_feed_url(row.get("href")),
                "primary": False,
            }
            for row in rows[:MAX_DISCOVERED]
        ]
    auth_provider = _discovery_auth(target, provider_row)
    auth_header = auth_provider() if auth_provider else None
    headers = {"Authorization": auth_header} if auth_header else {}
    if protocol == "google-calendar":
        base = spec.api_base or "https://www.googleapis.com/calendar/v3"
        response = await client.get(f"{base}/users/me/calendarList", headers=headers)
        if response.status_code >= 300:
            raise CalendarSyncError(
                "provider", f"calendarList -> {response.status_code}", status=409
            )
        items = response.json().get("items", [])[:MAX_DISCOVERED]
        return [
            {
                "id": str(item.get("id") or "")[:200],
                "name": str(item.get("summary") or item.get("id") or "")[:200],
                "url": None,
                "primary": bool(item.get("primary")),
            }
            for item in items
            if item.get("id")
        ]
    if protocol == "graph-calendar":
        base = spec.api_base or "https://graph.microsoft.com/v1.0"
        response = await client.get(f"{base}/me/calendars?$top={MAX_DISCOVERED}", headers=headers)
        if response.status_code >= 300:
            raise CalendarSyncError(
                "provider", f"me/calendars -> {response.status_code}", status=409
            )
        items = response.json().get("value", [])[:MAX_DISCOVERED]
        return [
            {
                "id": str(item.get("id") or "")[:200],
                "name": str(item.get("name") or item.get("id") or "")[:200],
                "url": None,
                "primary": bool(item.get("isDefaultCalendar")),
            }
            for item in items
            if item.get("id")
        ]
    raise CalendarSyncError("unsupported", f"{protocol} has no calendar list", status=422)


async def discover_calendars(
    session: Session,
    *,
    profile_id: str,
    link_id: str | None = None,
    provider_id: str | None = None,
    auth_kind: str | None = None,
    base_url: str | None = None,
    calendar_url: str | None = None,
    username: str | None = None,
    secret: str | None = None,
) -> list[dict[str, Any]]:
    """List an account's calendars for the bind form's picker.

    Runs with either an existing link's stored credential (``link_id``) or
    bind-form credentials held in memory for this one request. The response
    carries ids, names and sanitized URLs only — never a credential.
    """
    link: CalendarLink | None = None
    if link_id:
        link = get_link(session, profile_id, link_id)
    provider_row, target = _discovery_target(
        link=link,
        provider_id=provider_id,
        auth_kind=auth_kind,
        base_url=base_url,
        calendar_url=calendar_url,
        username=username,
        secret=secret,
    )
    if target.auth_kind == "oauth2" and link is None:
        raise CalendarSyncError(
            "invalid", "OAuth calendars are discovered through a connected link", status=422
        )
    client = _guarded_client(target, provider_row, timeout=15.0)
    try:
        return await _discover_rows(target, provider_row, client)
    except calendar.CalendarError as exc:
        raise CalendarSyncError(exc.code, exc.detail, status=409) from exc
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Domain mapping
# ---------------------------------------------------------------------------


def event_uid(item: PlanItem) -> str:
    return item.external_uid or f"planitem-{item.id}@studyassistant.local"


def course_exam_uid(course_id: str) -> str:
    return f"exam-{course_id}@studyassistant.local"


def course_exam_local_id(course_id: str) -> str:
    return f"course-exam:{course_id}"


def to_event(item: PlanItem, course: Course) -> calendar.CalendarEvent:
    description = course.title
    if item.detail:
        description = f"{description}\n{item.detail}"
    return calendar.CalendarEvent(
        uid=event_uid(item),
        start=item.due_date,
        end=item.due_date + timedelta(days=1),
        all_day=True,
        summary=item.title[:MAX_TITLE],
        description=description[:MAX_DETAIL],
        # E8 storage + attribution: the marker rides every projected event
        # (Google: private extendedProperties; CalDAV/Graph: real CATEGORIES)
        # so a round trip is attributable without any provider branch.
        categories=(calendar.SOURCE_CATEGORY, item.kind.upper()),
        updated_at=item.updated_at or item.created_at,
    )


def _accepted(event: calendar.CalendarEvent, link: CalendarLink) -> bool:
    """The inbound law (ADR-0052 §6 / E8): attributable-only.

    A remote event becomes a plan item ONLY when it is attributable (the
    ``NEURONECTION`` marker category or a uid we minted), when the link
    explicitly opted into ``acceptAll``, or when the user listed the
    categories themselves. A title that merely *looks* like an exam is a
    suggestion (:func:`_suggest_items`), never a record — a false positive
    here silently writes into the user's plan.
    """
    options = link.options or {}
    if calendar.is_attributable(event, namespaces=("study:",)):
        return True
    if options.get("acceptAll") is True:
        return True
    allowed = {str(value).upper() for value in options.get("acceptCategories") or ()}
    if not allowed:
        return False
    return bool({str(value).upper() for value in event.categories} & allowed)


def _suggest_items(
    session: Session, link: CalendarLink, remote: list[calendar.CalendarEvent]
) -> int:
    """Keyword lookalikes become ``origin='draft'`` suggestions, not records.

    The user keeps or discards each in the planner (the existing draft row
    pattern). Never auto-created, never auto-completed.
    """
    created = 0
    for event in remote:
        if _accepted(event, link):
            continue
        if not EXAM_PATTERN.search(event.summary or ""):
            continue
        exists = session.scalars(
            select(PlanItem).where(
                PlanItem.course_id == link.course_id,
                PlanItem.external_uid == event.uid,
            )
        ).first()
        if exists is not None:
            continue
        session.add(
            PlanItem(
                profile_id=link.profile_id,
                course_id=link.course_id,
                node_id=None,
                title=(event.summary or "Calendar event")[:MAX_TITLE],
                detail=(event.description or "")[:MAX_DETAIL] or None,
                kind=kind_for_event(event),
                due_date=event.start_day,
                origin=PlanItemOrigin.DRAFT.value,
                sort_key=0,
                external_uid=event.uid,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        created += 1
    if created:
        session.flush()
    return created


def kind_for_event(event: calendar.CalendarEvent) -> str:
    categories = {str(value).upper() for value in event.categories}
    if {"EXAM", "EXAMINATION", "MIDTERM", "FINAL"} & categories:
        return PlanItemKind.EXAM.value
    if {"DEADLINE", "DUE"} & categories:
        return PlanItemKind.DEADLINE.value
    if EXAM_PATTERN.search(event.summary or ""):
        return PlanItemKind.EXAM.value
    return PlanItemKind.DEADLINE.value


def _projected_kinds(link: CalendarLink) -> set[str]:
    return {str(value) for value in (link.options or {}).get("kinds") or PROJECTED_KINDS}


def _local_records(
    session: Session, link: CalendarLink, course: Course
) -> tuple[list[calendar.LocalEvent], dict[str, PlanItem]]:
    items = list(
        session.scalars(
            select(PlanItem).where(
                PlanItem.profile_id == link.profile_id,
                PlanItem.course_id == link.course_id,
            )
        )
    )
    linked_uids = {
        row.local_id: row.uid
        for row in session.scalars(
            select(CalendarEventLink).where(CalendarEventLink.link_id == link.id)
        )
    }
    kinds = _projected_kinds(link)
    records: list[calendar.LocalEvent] = []
    by_id: dict[str, PlanItem] = {}
    exam_local_id = course_exam_local_id(course.id)
    if course.exam_date is not None and PlanItemKind.EXAM.value in kinds:
        records.append(
            calendar.LocalEvent(
                local_id=exam_local_id,
                event=calendar.CalendarEvent(
                    uid=linked_uids.get(exam_local_id, course_exam_uid(course.id)),
                    start=course.exam_date,
                    end=course.exam_date + timedelta(days=1),
                    all_day=True,
                    summary=f"Exam: {course.title}"[:MAX_TITLE],
                    categories=("EXAM",),
                    updated_at=getattr(course, "updated_at", None) or utcnow(),
                ),
                updated_at=getattr(course, "updated_at", None) or utcnow(),
            )
        )
    for item in items:
        if item.kind not in kinds and item.id not in linked_uids:
            continue
        event = to_event(item, course)
        if item.id in linked_uids:
            event = dataclass_replace(event, uid=linked_uids[item.id])
        records.append(
            calendar.LocalEvent(
                local_id=item.id,
                event=event,
                updated_at=item.updated_at or item.created_at,
                deleted=item.done_at is not None,
            )
        )
        by_id[item.id] = item
    return records, by_id


def _links(session: Session, link: CalendarLink) -> list[calendar.EventLink]:
    return [
        calendar.EventLink(
            local_id=row.local_id,
            uid=row.uid,
            remote_id=row.remote_id,
            etag=row.etag,
            local_hash=row.local_hash,
            remote_hash=row.remote_hash,
            updated_at=row.updated_at,
        )
        for row in session.scalars(
            select(CalendarEventLink).where(CalendarEventLink.link_id == link.id)
        )
    ]


def _upsert_event_link(
    session: Session,
    link: CalendarLink,
    *,
    local_id: str,
    event: calendar.CalendarEvent,
    now: datetime,
    uid: str | None = None,
) -> None:
    """Persist the identity pin.

    ``uid`` is the LOCAL uid (``study:plan-item:<id>``) — the identity
    authority. The provider may mint its own (Graph's ``iCalUId`` is
    server-generated), so the remote's uid is only ever a write handle.
    """
    identity = uid or event.uid
    row = session.scalars(
        select(CalendarEventLink).where(
            CalendarEventLink.link_id == link.id,
            CalendarEventLink.local_id == local_id,
        )
    ).first()
    if row is None:
        row = CalendarEventLink(
            link_id=link.id,
            local_id=local_id,
            uid=identity,
            remote_id=event.remote_id,
            etag=event.etag,
            local_hash=calendar.event_hash(event),
            remote_hash=calendar.event_hash(event),
            updated_at=now,
        )
        session.add(row)
        return
    row.uid = identity
    row.remote_id = event.remote_id
    row.etag = event.etag
    row.local_hash = calendar.event_hash(event)
    row.remote_hash = calendar.event_hash(event)
    row.updated_at = now


def _pull_item(
    session: Session, link: CalendarLink, event: calendar.CalendarEvent
) -> tuple[PlanItem, bool]:
    existing = session.scalars(
        select(PlanItem).where(
            PlanItem.course_id == link.course_id,
            PlanItem.external_uid == event.uid,
        )
    ).first()
    kind = kind_for_event(event)
    detail = (event.description or "")[:MAX_DETAIL] or None
    if existing is not None:
        existing.title = (event.summary or existing.title)[:MAX_TITLE]
        existing.due_date = event.start_day
        existing.kind = kind
        existing.detail = detail
        existing.origin = PlanItemOrigin.CALENDAR.value
        existing.updated_at = utcnow()
        return existing, False
    item = PlanItem(
        profile_id=link.profile_id,
        course_id=link.course_id,
        node_id=None,
        title=(event.summary or "Calendar event")[:MAX_TITLE],
        detail=detail,
        kind=kind,
        due_date=event.start_day,
        origin=PlanItemOrigin.CALENDAR.value,
        sort_key=0,
        external_uid=event.uid,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(item)
    session.flush()
    return item, True


def _apply_local(
    session: Session, link: CalendarLink, course: Course, event: calendar.CalendarEvent
) -> tuple[str, bool]:
    """Upsert the local side of a pulled event; returns (local id, created)."""
    if event.uid == course_exam_uid(link.course_id):
        course.exam_date = event.start_day
        course.updated_at = utcnow()
        session.flush()
        return course_exam_local_id(link.course_id), False
    item, created = _pull_item(session, link, event)
    return item.id, created


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def _window(now: datetime | None = None) -> tuple[date, date]:
    today = (now or datetime.now(UTC)).date()
    return today - timedelta(days=SYNC_PAST_DAYS), today + timedelta(days=SYNC_FUTURE_DAYS)


async def _list_all(
    transport: calendar.CalendarTransport, start: date, end: date
) -> list[calendar.CalendarEvent]:
    events: list[calendar.CalendarEvent] = []
    page_token: str | None = None
    for _ in range(MAX_PAGES):
        page = await transport.list_events(start, end, page_token=page_token)
        events.extend(page.events)
        page_token = page.next_page_token
        if not page_token:
            break
    return events


def _mark_failure(session: Session, link: CalendarLink, error: Exception) -> SyncReport:
    code = getattr(error, "code", "provider")
    detail = getattr(error, "detail", None) or str(error)
    link.consecutive_failures = (link.consecutive_failures or 0) + 1
    link.last_error = str(detail)[:500]
    if code in ("auth", "needs-auth", "needs-secret"):
        link.status = CalendarStatus.NEEDS_AUTH.value
    elif link.consecutive_failures >= 3:
        link.status = CalendarStatus.FAILING.value
    else:
        link.status = CalendarStatus.DEGRADED.value
    link.updated_at = utcnow()
    session.commit()
    report = SyncReport(status=link.status, error=link.last_error)
    return report


async def sync_link(
    session: Session,
    link: CalendarLink,
    *,
    now: datetime | None = None,
) -> SyncReport:
    """One reconcile run. Never raises for provider failures; updates status."""
    if not link.enabled:
        return SyncReport(status=CalendarStatus.STALE.value, error="link is disabled")
    lock = _locks.setdefault(link.id, asyncio.Lock())
    if lock.locked():
        return SyncReport(status=CalendarStatus.DEGRADED.value, error="a sync is already running")
    async with lock:
        return await _sync_locked(session, link, now=now)


async def _sync_locked(
    session: Session, link: CalendarLink, *, now: datetime | None = None
) -> SyncReport:
    provider_row = provider(link.provider)
    course = session.get(Course, link.course_id)
    if course is None:
        return _mark_failure(session, link, CalendarSyncError("not-found", "course was deleted"))
    local_records, items = _local_records(session, link, course)
    link_rows = _links(session, link)
    start, end = _window(now)
    client = _guarded_client(link, provider_row, timeout=25.0)
    report = SyncReport()
    try:
        transport = _transport(link, provider_row, client)
        remote = await _list_all(transport, start, end)
        plan = calendar.reconcile(
            local_records,
            remote,
            link_rows,
            direction=link.direction,
            conflicts=str((link.options or {}).get("conflictPolicy") or "skip"),
            deletions=str((link.options or {}).get("deletionPolicy") or "keep-local"),
            accept=lambda event: _accepted(event, link),
            remote_writable=bool(transport.writable),
            now=now,
            # E5: the remote list is window-bounded — without the window an
            # out-of-window link reads as "remote deleted" and gets unlinked.
            window=(start, end),
        )
        report.skipped = plan.skipped
        at = now or datetime.now(UTC)

        # Links whose local plan item vanished: the next run cleans the remote
        # (only when the link explicitly propagates deletions).
        local_ids = {record.local_id for record in local_records}
        policy = str((link.options or {}).get("deletionPolicy") or "keep-local")
        for orphan in session.scalars(
            select(CalendarEventLink).where(CalendarEventLink.link_id == link.id)
        ):
            if orphan.local_id in local_ids:
                continue
            if (
                policy == "propagate"
                and link.direction != CalendarDirection.PULL.value
                and transport.writable
                and orphan.remote_id
            ):
                try:
                    await transport.delete_event(
                        calendar.CalendarEvent(
                            uid=orphan.uid,
                            start=date.today(),
                            end=date.today() + timedelta(days=1),
                            all_day=True,
                            remote_id=orphan.remote_id,
                            etag=orphan.etag,
                        )
                    )
                    report.deleted_remote += 1
                except calendar.CalendarError as exc:
                    report.error = f"delete remote: {exc.detail or exc.code}"
            session.delete(orphan)
            report.unlinked += 1

        for action in plan.actions:
            try:
                if action.kind == calendar.ActionKind.CREATE_REMOTE and action.event:
                    written = await transport.put_event(action.event)
                    item = items.get(action.local_id or "")
                    if item is not None:
                        item.external_uid = written.uid
                        item.updated_at = utcnow()
                    _upsert_event_link(
                        session,
                        link,
                        local_id=action.local_id or "",
                        event=written,
                        now=at,
                        uid=action.uid,
                    )
                    report.created_remote += 1
                elif action.kind == calendar.ActionKind.UPDATE_REMOTE and action.event:
                    written = await transport.put_event(action.event)
                    _upsert_event_link(
                        session,
                        link,
                        local_id=action.local_id or "",
                        event=written,
                        now=at,
                        uid=action.uid,
                    )
                    report.updated_remote += 1
                elif action.kind == calendar.ActionKind.DELETE_REMOTE and action.event:
                    await transport.delete_event(action.event)
                    linked = session.scalars(
                        select(CalendarEventLink).where(
                            CalendarEventLink.link_id == link.id,
                            CalendarEventLink.local_id == action.local_id,
                        )
                    ).first()
                    if linked is not None:
                        session.delete(linked)
                    report.deleted_remote += 1
                elif action.kind == calendar.ActionKind.CREATE_LOCAL and action.event:
                    local_id, created = _apply_local(session, link, course, action.event)
                    _upsert_event_link(
                        session, link, local_id=local_id, event=action.event, now=at
                    )
                    report.created_local += 1 if created else 0
                    report.updated_local += 0 if created else 1
                elif action.kind == calendar.ActionKind.UPDATE_LOCAL and action.event:
                    local_id, _ = _apply_local(session, link, course, action.event)
                    _upsert_event_link(
                        session, link, local_id=local_id, event=action.event, now=at
                    )
                    report.updated_local += 1
                elif action.kind == calendar.ActionKind.DELETE_LOCAL and action.local_id:
                    item = items.get(action.local_id)
                    if item is not None:
                        session.delete(item)
                    linked = session.scalars(
                        select(CalendarEventLink).where(
                            CalendarEventLink.link_id == link.id,
                            CalendarEventLink.local_id == action.local_id,
                        )
                    ).first()
                    if linked is not None:
                        session.delete(linked)
                    report.deleted_local += 1
                elif action.kind == calendar.ActionKind.UNLINK:
                    linked = session.scalars(
                        select(CalendarEventLink).where(
                            CalendarEventLink.link_id == link.id,
                            CalendarEventLink.local_id == action.local_id,
                        )
                    ).first()
                    if linked is not None:
                        session.delete(linked)
                    report.unlinked += 1
                elif action.kind == calendar.ActionKind.LINK_EXISTING and action.event:
                    # E9 orphan repair: the remote already exists — attach it
                    # to the local record instead of creating a duplicate.
                    _upsert_event_link(
                        session,
                        link,
                        local_id=action.local_id or "",
                        event=action.event,
                        now=at,
                        uid=action.uid,
                    )
                    report.unlinked += 0
                    report.updated_local += 0
                    report.linked_existing += 1
                elif action.kind == calendar.ActionKind.CONFLICT:
                    report.conflicts += 1
            except calendar.CalendarError as exc:
                report.error = f"{exc.code}: {exc.detail}"
                report.status = CalendarStatus.DEGRADED.value
        # E8: keyword lookalikes become draft suggestions, never records.
        report.suggested = _suggest_items(session, link, remote)
        link.last_synced_at = utcnow()
        link.consecutive_failures = 0
        link.last_error = report.error
        link.status = report.status if report.error else CalendarStatus.OK.value
        link.updated_at = utcnow()
        session.commit()
        return report
    except (calendar.CalendarError, CalendarSyncError) as exc:
        session.rollback()
        return _mark_failure(session, link, exc)
    except httpx.HTTPError as exc:
        session.rollback()
        return _mark_failure(
            session, link, CalendarSyncError("unreachable", str(exc), status=409)
        )
    finally:
        await client.aclose()


async def test_link(session: Session, link: CalendarLink) -> SyncReport:
    """One read, no writes — the bind surface's 'check connection'."""
    provider_row = provider(link.provider)
    start, end = _window()
    client = _guarded_client(link, provider_row, timeout=20.0)
    try:
        transport = _transport(link, provider_row, client)
        page = await transport.list_events(start, end)
        link.status = CalendarStatus.OK.value
        link.last_error = None
        link.consecutive_failures = 0
        link.updated_at = utcnow()
        session.commit()
        return SyncReport(status=CalendarStatus.OK.value, skipped=len(page.events))
    except (calendar.CalendarError, CalendarSyncError) as exc:
        session.rollback()
        return _mark_failure(session, link, exc)
    finally:
        await client.aclose()


def link_as_dict(link: CalendarLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "course_id": link.course_id,
        "provider": link.provider,
        "auth_kind": link.auth_kind,
        "label": link.label,
        "account_label": link.account_label,
        "calendar_id": link.calendar_id,
        "calendar_url": link.calendar_url,
        "direction": link.direction,
        "enabled": link.enabled,
        "status": link.status,
        "last_error": link.last_error,
        "last_synced_at": link.last_synced_at.isoformat() if link.last_synced_at else None,
        "consecutive_failures": link.consecutive_failures,
        "scopes": list(link.scopes or []),
        "options": dict(link.options or {}),
        "secret_configured": bool(
            link.secret_ref and secret_store.get_secret(link.secret_ref)
        ),
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "updated_at": link.updated_at.isoformat() if link.updated_at else None,
    }


__all__ = [
    "CalendarSyncError",
    "SyncReport",
    "catalog_provider_rows",
    "create_link",
    "delete_link",
    "discover_calendars",
    "get_link",
    "kind_for_event",
    "link_as_dict",
    "list_links",
    "oauth_complete",
    "oauth_start",
    "set_secret",
    "setup_fields",
    "supports_discovery",
    "sync_link",
    "test_link",
    "to_event",
    "update_link",
]
