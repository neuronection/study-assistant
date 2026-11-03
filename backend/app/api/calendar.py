"""Cloud calendar API (ADR-0052 / plan 52).

The API surface is deliberately small: catalog, links, one secret write, the
OAuth pair and two verbs (sync/test). Everything provider-specific comes from
the family catalog; no token is ever returned — ``link_as_dict`` reports only
whether a credential is configured.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..services.platform.profiles import ensure_default_profile
from ..services.study import calendar_sync as service
from .deps import get_session

router = APIRouter(prefix="/calendar", tags=["calendar"])


class SetupFieldOut(BaseModel):
    """One bind-form field, derived from the catalog row (plan 52 §12).

    ``kind`` selects the input; ``calendar`` is the discovery-backed picker.
    ``label_key`` is an i18n suffix under ``settings.calendar.`` so the
    backend never ships user copy.
    """

    key: str
    kind: str
    required: bool
    label_key: str
    placeholder: str | None = None
    autocomplete: str | None = None
    auth_kind: str | None = None
    manual_key: str | None = None


class CalendarProviderOut(BaseModel):
    id: str
    label: str
    auth_kinds: list[str]
    base_url_required: bool
    protocol: str
    writable: bool
    supports_delta: bool
    scope_presets: dict[str, list[str]]
    consent_notice: str
    domains: list[str]
    setup_fields: list[SetupFieldOut]
    supports_discovery: bool


class CalendarCatalogOut(BaseModel):
    providers: list[CalendarProviderOut]
    secret_disclosure: str


class CalendarLinkIn(BaseModel):
    course_id: str
    provider: str
    label: str = Field(min_length=1, max_length=200)
    direction: str = Field(default="push", pattern="^(push|pull|two-way)$")
    auth_kind: str | None = Field(default=None, max_length=32)
    base_url: str | None = Field(default=None, max_length=2048)
    calendar_id: str | None = Field(default=None, max_length=512)
    calendar_url: str | None = Field(default=None, max_length=2048)
    username: str | None = Field(default=None, max_length=200)
    secret: str | None = Field(default=None, max_length=10_000)
    options: dict[str, Any] | None = None


class CalendarLinkPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    direction: str | None = Field(default=None, pattern="^(push|pull|two-way)$")
    calendar_id: str | None = Field(default=None, max_length=512)
    calendar_url: str | None = Field(default=None, max_length=2048)
    enabled: bool | None = None
    options: dict[str, Any] | None = None


class CalendarLinkOut(BaseModel):
    id: str
    course_id: str
    provider: str
    auth_kind: str
    label: str
    account_label: str | None
    calendar_id: str | None
    calendar_url: str | None
    direction: str
    enabled: bool
    status: str
    last_error: str | None
    last_synced_at: str | None
    consecutive_failures: int
    scopes: list[str]
    options: dict[str, Any]
    secret_configured: bool
    created_at: str | None
    updated_at: str | None


class CalendarSecretIn(BaseModel):
    value: str = Field(min_length=1, max_length=10_000)


class CalendarDiscoverIn(BaseModel):
    """Bind-form credentials for one discovery call — never persisted."""

    provider: str | None = Field(default=None, max_length=64)
    auth_kind: str | None = Field(default=None, max_length=32)
    base_url: str | None = Field(default=None, max_length=2048)
    calendar_url: str | None = Field(default=None, max_length=2048)
    username: str | None = Field(default=None, max_length=200)
    secret: str | None = Field(default=None, max_length=10_000)
    link_id: str | None = Field(default=None, max_length=64)


class CalendarDiscoveredOut(BaseModel):
    id: str
    name: str
    url: str | None = None
    primary: bool = False


class CalendarDiscoverOut(BaseModel):
    calendars: list[CalendarDiscoveredOut]


class OAuthStartOut(BaseModel):
    authorize_url: str
    redirect_uri: str
    state: str


class OAuthCompleteIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)
    state: str = Field(min_length=1, max_length=400)


class SyncReportOut(BaseModel):
    status: str
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
    error: str | None = None


def _http(error: service.CalendarSyncError) -> HTTPException:
    return HTTPException(status_code=error.status, detail=f"{error.code}: {error.detail}")


@router.get("/providers", response_model=CalendarCatalogOut)
def provider_catalog() -> CalendarCatalogOut:
    from ..extensions.cloud.cloud_providers import default_catalog

    rows = service.catalog_provider_rows()
    return CalendarCatalogOut(
        providers=[
            CalendarProviderOut(
                id=row["id"],
                label=row["label"],
                auth_kinds=row["authKinds"],
                base_url_required=row["baseUrlRequired"],
                protocol=row["protocol"],
                writable=row["writable"],
                supports_delta=row["supportsDelta"],
                scope_presets=row["scopePresets"],
                consent_notice=row["consentNotice"],
                domains=row["domains"],
                setup_fields=[
                    SetupFieldOut(
                        key=field["key"],
                        kind=field["kind"],
                        required=field["required"],
                        label_key=field["label_key"],
                        placeholder=field.get("placeholder"),
                        autocomplete=field.get("autocomplete"),
                        auth_kind=field.get("auth_kind"),
                        manual_key=field.get("manual_key"),
                    )
                    for field in row["setupFields"]
                ],
                supports_discovery=row["supportsDiscovery"],
            )
            for row in rows
        ],
        secret_disclosure=default_catalog().secret_disclosure,
    )


@router.post("/links/discover", response_model=CalendarDiscoverOut)
async def discover_calendars(
    body: CalendarDiscoverIn, session: Session = Depends(get_session)
) -> CalendarDiscoverOut:
    """List an account's calendars so the bind form offers a picker (M1)."""
    profile = ensure_default_profile(session)
    try:
        rows = await service.discover_calendars(
            session,
            profile_id=profile.id,
            link_id=body.link_id,
            provider_id=body.provider,
            auth_kind=body.auth_kind,
            base_url=body.base_url,
            calendar_url=body.calendar_url,
            username=body.username,
            secret=body.secret,
        )
    except service.CalendarSyncError as error:
        raise _http(error) from error
    return CalendarDiscoverOut(
        calendars=[CalendarDiscoveredOut(**row) for row in rows]
    )


@router.get("/links", response_model=list[CalendarLinkOut])
def list_links(
    course_id: str | None = None, session: Session = Depends(get_session)
) -> list[CalendarLinkOut]:
    profile = ensure_default_profile(session)
    links = service.list_links(session, profile.id)
    if course_id:
        links = [link for link in links if link.course_id == course_id]
    return [CalendarLinkOut(**service.link_as_dict(link)) for link in links]


@router.post("/links", response_model=CalendarLinkOut, status_code=201)
def create_link(body: CalendarLinkIn, session: Session = Depends(get_session)) -> CalendarLinkOut:
    profile = ensure_default_profile(session)
    try:
        link = service.create_link(
            session,
            profile_id=profile.id,
            course_id=body.course_id,
            provider_id=body.provider,
            label=body.label,
            direction=body.direction,
            base_url=body.base_url,
            calendar_id=body.calendar_id,
            calendar_url=body.calendar_url,
            username=body.username,
            secret=body.secret,
            auth_kind=body.auth_kind,
            options=body.options,
        )
    except service.CalendarSyncError as error:
        raise _http(error) from error
    return CalendarLinkOut(**service.link_as_dict(link))


@router.patch("/links/{link_id}", response_model=CalendarLinkOut)
def patch_link(
    link_id: str, body: CalendarLinkPatch, session: Session = Depends(get_session)
) -> CalendarLinkOut:
    profile = ensure_default_profile(session)
    try:
        link = service.get_link(session, profile.id, link_id)
        link = service.update_link(
            session,
            link,
            label=body.label,
            direction=body.direction,
            calendar_id=body.calendar_id,
            calendar_url=body.calendar_url,
            enabled=body.enabled,
            options=body.options,
        )
    except service.CalendarSyncError as error:
        raise _http(error) from error
    return CalendarLinkOut(**service.link_as_dict(link))


@router.delete("/links/{link_id}", status_code=204)
def remove_link(link_id: str, session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    try:
        link = service.get_link(session, profile.id, link_id)
    except service.CalendarSyncError as error:
        raise _http(error) from error
    service.delete_link(session, link)


@router.post("/links/{link_id}/secret", response_model=CalendarLinkOut)
def set_secret(
    link_id: str, body: CalendarSecretIn, session: Session = Depends(get_session)
) -> CalendarLinkOut:
    profile = ensure_default_profile(session)
    try:
        link = service.get_link(session, profile.id, link_id)
        link = service.set_secret(session, link, body.value)
    except service.CalendarSyncError as error:
        raise _http(error) from error
    return CalendarLinkOut(**service.link_as_dict(link))


@router.post("/links/{link_id}/oauth/start", response_model=OAuthStartOut)
def oauth_start(link_id: str, session: Session = Depends(get_session)) -> OAuthStartOut:
    profile = ensure_default_profile(session)
    try:
        link = service.get_link(session, profile.id, link_id)
        payload = service.oauth_start(link, profile_id=profile.id)
    except service.CalendarSyncError as error:
        raise _http(error) from error
    return OAuthStartOut(**payload)


@router.get("/oauth/callback")
def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_session),
):
    """Server-side OAuth callback (web deployments).

    Desktop/local never uses this: its loopback listener receives the
    redirect directly (RFC 8252). A web deployment sets ``SA_APP_URL`` and
    the provider redirects **here** — the user's browser runs on another
    machine, so a loopback redirect would land on their own localhost.

    Security: the flow's ``state`` is single-use, expiring and bound to the
    profile that started it, and this route consumes it with the session's
    profile. A foreign or replayed state is refused (ADR-0052 Rev 3 E12).
    """
    from fastapi.responses import RedirectResponse

    profile = ensure_default_profile(session)
    landing = _frontend_origin()

    if error or not code or not state:
        return RedirectResponse(
            f"{landing}/settings?tab=tools&section=connectors&calendar_status=error",
            status_code=302,
        )
    link_id = service.link_id_from_state(state or "")
    if not link_id:
        return RedirectResponse(
            f"{landing}/settings?tab=tools&section=connectors&calendar_status=error",
            status_code=302,
        )
    try:
        link = service.get_link(session, profile.id, link_id)
        service.oauth_complete(session, link, code=code, state=state, profile_id=profile.id)
    except service.CalendarSyncError:
        return RedirectResponse(
            f"{landing}/settings?tab=tools&section=connectors&calendar_status=error",
            status_code=302,
        )
    return RedirectResponse(
        f"{landing}/settings?tab=tools&section=connectors&calendar_status=connected",
        status_code=302,
    )


def _frontend_origin() -> str:
    from app.core.config import get_settings

    return (get_settings().app_url or "").rstrip("/") or ""


@router.post("/links/{link_id}/oauth/complete", response_model=CalendarLinkOut)
def oauth_complete(
    link_id: str, body: OAuthCompleteIn, session: Session = Depends(get_session)
) -> CalendarLinkOut:
    profile = ensure_default_profile(session)
    try:
        link = service.get_link(session, profile.id, link_id)
        link = service.oauth_complete(
            session, link, code=body.code, state=body.state, profile_id=profile.id
        )
    except service.CalendarSyncError as error:
        raise _http(error) from error
    return CalendarLinkOut(**service.link_as_dict(link))


@router.post("/links/{link_id}/test", response_model=SyncReportOut)
async def test_link(link_id: str, session: Session = Depends(get_session)) -> SyncReportOut:
    profile = ensure_default_profile(session)
    try:
        link = service.get_link(session, profile.id, link_id)
    except service.CalendarSyncError as error:
        raise _http(error) from error
    report = await service.test_link(session, link)
    return SyncReportOut(**report.as_dict())


@router.post("/links/{link_id}/sync", response_model=SyncReportOut)
async def sync_link(link_id: str, session: Session = Depends(get_session)) -> SyncReportOut:
    profile = ensure_default_profile(session)
    try:
        link = service.get_link(session, profile.id, link_id)
    except service.CalendarSyncError as error:
        raise _http(error) from error
    report = await service.sync_link(session, link)
    return SyncReportOut(**report.as_dict())
