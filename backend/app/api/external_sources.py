from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions.builtin.external_sources import MIN_SCAN_INTERVAL_SEC
from app.extensions.builtin.external_sources.providers import get_provider
from app.extensions.errors import ExtensionError

from ..core.vocab import AuthKind
from ..domain.models import Course, ExternalSource, MaterialSuggestion
from ..services.content import discovery as suggestions
from ..services.content import external_sources as external
from ..services.platform.backup import BackupError, build_backup
from ..services.platform.profiles import ensure_default_profile
from .backup import apply_restore
from .deps import get_session

router = APIRouter(prefix="/external-sources", tags=["external-sources"])

STALENESS_WINDOW = timedelta(hours=24)


class SecretSlotOut(BaseModel):
    name: str
    label: str
    required: bool


class SourceProviderOAuthOut(BaseModel):
    scopes: list[str]
    client_id_env: str


class SourceProviderOut(BaseModel):
    id: str
    label: str
    kinds: list[str]
    default_kind: str
    auth_kind: str
    url_required: bool
    fields: list[str]
    supports_backup: bool
    secret_slots: list[SecretSlotOut]
    oauth: SourceProviderOAuthOut | None = None


class SourceProviderCatalogOut(BaseModel):
    providers: list[SourceProviderOut]
    secret_disclosure: str


class ExternalSourceIn(BaseModel):
    course_id: str
    provider: str | None = Field(default=None, max_length=64)
    kind: str = Field(default="", max_length=30)
    url: str = Field(default="", max_length=2048)
    label: str | None = Field(default=None, max_length=200)
    options: dict[str, Any] | None = None
    enabled: bool = True
    scan_interval_sec: int | None = Field(default=None, ge=MIN_SCAN_INTERVAL_SEC)


class ExternalSourcePatch(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    options: dict[str, Any] | None = None
    scan_interval_sec: int | None = Field(default=None, ge=MIN_SCAN_INTERVAL_SEC)


class ExternalSourceOut(BaseModel):
    id: str
    course_id: str
    provider: str
    kind: str
    auth_kind: str
    account_ref: str | None
    url: str
    label: str | None
    options: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    scan_interval_sec: int | None
    last_scan_error: str | None
    last_scanned_at: str | None
    status: str
    last_success_at: str | None
    consecutive_failures: int
    conditions: list[str] = Field(default_factory=list)
    secrets_configured: dict[str, bool] = Field(default_factory=dict)


class SecretIn(BaseModel):
    slot: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=10_000)


class SecretStatusOut(BaseModel):
    secrets_configured: dict[str, bool]


class OAuthStartOut(BaseModel):
    authorize_url: str
    redirect_uri: str
    state: str


class OAuthCompleteIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)
    state: str = Field(min_length=1, max_length=400)


class OAuthStatusOut(BaseModel):
    status: str


class AcceptIn(BaseModel):
    suggestion_id: str


class AcceptOut(BaseModel):
    material_id: str
    deduped: bool
    job_kind: str


class RemoteBackupOut(BaseModel):
    name: str
    size: int | None
    created_at: str | None
    remote_id: str


class RemoteBackupListOut(BaseModel):
    backups: list[RemoteBackupOut]


class BackupUploadOut(BaseModel):
    name: str
    size: int
    location: str


class RestoreOut(BaseModel):
    status: str
    materials: int
    blobs: int


def _status(source: ExternalSource) -> tuple[str, list[str], int]:
    conditions: list[str] = []
    from ..extensions.builtin.external_sources.providers import provider_for_kind

    provider = get_provider(source.provider or provider_for_kind(source.kind))
    if provider.auth_kind == AuthKind.OAUTH2.value:
        try:
            probe = external.oauth_status(source)
        except Exception:
            probe = "needs-config"
        if probe != "ok":
            conditions.append("needs-config" if probe == "needs-config" else "expired")
    failures = int(source.consecutive_failures or 0)
    if source.last_scan_error:
        return ("failing" if failures >= 2 else "degraded", conditions, max(1, failures))
    scanned = source.last_scanned_at
    if scanned is None:
        return ("ok", conditions, 0)
    if scanned.tzinfo is None:
        scanned = scanned.replace(tzinfo=UTC)
    if datetime.now(UTC) - scanned > STALENESS_WINDOW:
        return ("stale", conditions, 0)
    return ("ok", conditions, 0)


def _out(source: ExternalSource) -> ExternalSourceOut:
    status, conditions, failures = _status(source)
    return ExternalSourceOut(
        id=source.id,
        course_id=source.course_id,
        provider=source.provider,
        kind=source.kind,
        auth_kind=source.auth_kind,
        account_ref=source.account_ref,
        url=source.url,
        label=source.label,
        options=source.options or {},
        enabled=source.enabled,
        scan_interval_sec=source.scan_interval_sec,
        last_scan_error=source.last_scan_error,
        last_scanned_at=(source.last_scanned_at.isoformat() if source.last_scanned_at else None),
        status=status,
        last_success_at=(
            source.last_scanned_at.isoformat()
            if source.last_scanned_at and not source.last_scan_error
            else None
        ),
        consecutive_failures=failures,
        conditions=conditions,
        secrets_configured=external.secrets_configured(source),
    )


def _owned_source(session: Session, profile_id: str, source_id: str) -> ExternalSource:
    source = session.get(ExternalSource, source_id)
    if source is None or source.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="source not found")
    return source


def _typed_error(error: ExtensionError) -> HTTPException:
    status_code = (
        422 if error.code in {"invalid", "needs-secret", "not-ready", "unsupported"} else 502
    )
    return HTTPException(status_code=status_code, detail=f"{error.code}: {error.detail}")


@router.get("/providers", response_model=SourceProviderCatalogOut)
def provider_catalog() -> SourceProviderCatalogOut:
    payload = external.provider_catalog()
    return SourceProviderCatalogOut.model_validate(payload)


@router.get("", response_model=list[ExternalSourceOut])
def list_sources(
    course_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[ExternalSourceOut]:
    profile = ensure_default_profile(session)
    stmt = select(ExternalSource).where(ExternalSource.profile_id == profile.id)
    if course_id is not None:
        stmt = stmt.where(ExternalSource.course_id == course_id)
    sources = list(session.scalars(stmt.order_by(ExternalSource.created_at, ExternalSource.id)))
    return [_out(source) for source in sources]


@router.post("", response_model=ExternalSourceOut, status_code=201)
def create_source(
    body: ExternalSourceIn,
    session: Session = Depends(get_session),
) -> ExternalSourceOut:
    profile = ensure_default_profile(session)
    course = session.get(Course, body.course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=422, detail="course not found")
    try:
        provider_id = body.provider or ""
        if not provider_id:
            from ..extensions.builtin.external_sources.providers import provider_for_kind

            provider_id = provider_for_kind(body.kind)
        provider = get_provider(provider_id)
        kind, url, options = external.validate_source(
            body.kind or provider.default_kind, body.url, body.options, provider_id
        )
    except ExtensionError as error:
        raise _typed_error(error) from error
    source = ExternalSource(
        profile_id=profile.id,
        course_id=body.course_id,
        provider=provider.id,
        kind=kind,
        auth_kind=provider.auth_kind,
        url=url,
        label=(body.label or "").strip()[:200] or None,
        options=options,
        enabled=body.enabled,
        scan_interval_sec=body.scan_interval_sec,
    )
    session.add(source)
    session.flush()
    if provider.auth_kind in {AuthKind.TOKEN.value, AuthKind.OAUTH2.value}:
        source.account_ref = f"source:{source.id}"
    session.commit()
    return _out(source)


@router.patch("/{source_id}", response_model=ExternalSourceOut)
def patch_source(
    source_id: str,
    body: ExternalSourcePatch,
    session: Session = Depends(get_session),
) -> ExternalSourceOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    if body.label is not None:
        source.label = body.label.strip()[:200] or None
    if body.enabled is not None:
        source.enabled = body.enabled
    if body.scan_interval_sec is not None:
        source.scan_interval_sec = body.scan_interval_sec
    if body.options is not None:
        try:
            _, _, options = external.validate_source(
                source.kind, source.url, body.options, source.provider
            )
        except ExtensionError as error:
            raise _typed_error(error) from error
        source.options = options
    session.commit()
    return _out(source)


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: str,
    session: Session = Depends(get_session),
) -> None:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    external.disconnect_oauth(source)
    if source.provider:
        provider = get_provider(source.provider)
        for slot in provider.secret_slots:
            try:
                external.delete_source_secret(source, slot.name)
            except ExtensionError:
                continue
    session.delete(source)
    session.commit()


@router.put("/{source_id}/secret", response_model=SecretStatusOut)
def set_secret(
    source_id: str,
    body: SecretIn,
    session: Session = Depends(get_session),
) -> SecretStatusOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        external.set_source_secret(source, body.slot, body.value)
    except ExtensionError as error:
        raise _typed_error(error) from error
    session.commit()
    return SecretStatusOut(secrets_configured=external.secrets_configured(source))


@router.delete("/{source_id}/secret/{slot}", response_model=SecretStatusOut)
def delete_secret(
    source_id: str,
    slot: str,
    session: Session = Depends(get_session),
) -> SecretStatusOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        external.delete_source_secret(source, slot)
    except ExtensionError as error:
        raise _typed_error(error) from error
    session.commit()
    return SecretStatusOut(secrets_configured=external.secrets_configured(source))


@router.post("/{source_id}/oauth/start", response_model=OAuthStartOut)
def oauth_start(
    source_id: str,
    session: Session = Depends(get_session),
) -> OAuthStartOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        payload = external.oauth_start(source)
    except ExtensionError as error:
        raise _typed_error(error) from error
    return OAuthStartOut(**payload)


@router.post("/{source_id}/oauth/complete", response_model=OAuthStatusOut)
def oauth_complete(
    source_id: str,
    body: OAuthCompleteIn,
    session: Session = Depends(get_session),
) -> OAuthStatusOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        external.complete_oauth(source, body.code, body.state)
    except ExtensionError as error:
        raise _typed_error(error) from error
    return OAuthStatusOut(status=external.oauth_status(source))


@router.post("/{source_id}/oauth/connect", response_model=OAuthStatusOut)
def oauth_connect(
    source_id: str,
    session: Session = Depends(get_session),
) -> OAuthStatusOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        external.connect_oauth(source)
    except ExtensionError as error:
        raise _typed_error(error) from error
    return OAuthStatusOut(status=external.oauth_status(source))


@router.post("/{source_id}/oauth/disconnect", response_model=OAuthStatusOut)
def oauth_disconnect(
    source_id: str,
    session: Session = Depends(get_session),
) -> OAuthStatusOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    external.disconnect_oauth(source)
    return OAuthStatusOut(status=external.oauth_status(source))


@router.post("/{source_id}/scan", response_model=dict[str, int])
def scan_source(
    source_id: str,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        stats = external.run_scan(session, source)
        session.commit()
    except ExtensionError as error:
        session.rollback()
        if error.code == "invalid":
            raise _typed_error(error) from error
        dead = session.get(ExternalSource, source_id)
        if dead is not None:
            dead.last_scan_error = f"{error.code}: {error.detail}"[:500]
            dead.consecutive_failures = int(dead.consecutive_failures or 0) + 1
            session.commit()
        raise _typed_error(error) from error
    except Exception as error:
        session.rollback()
        dead = session.get(ExternalSource, source_id)
        if dead is not None:
            dead.last_scan_error = str(error)[:500]
            dead.consecutive_failures = int(dead.consecutive_failures or 0) + 1
            session.commit()
        raise HTTPException(status_code=502, detail=f"scan failed: {str(error)[:300]}") from error
    return stats


@router.post("/{source_id}/accept", response_model=AcceptOut)
def accept_suggestion(
    source_id: str,
    body: AcceptIn,
    request: Request,
    session: Session = Depends(get_session),
) -> AcceptOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    suggestion = session.get(MaterialSuggestion, body.suggestion_id)
    if suggestion is None or suggestion.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="suggestion not found")
    meta = suggestion.meta if isinstance(suggestion.meta, dict) else {}
    if meta.get("source_id") != source.id:
        raise HTTPException(status_code=422, detail="suggestion belongs to another source")
    try:
        result = external.accept_suggestion(
            session, source, suggestion, request.app.state.blobs, request.app.state.jobs
        )
    except ExtensionError as error:
        session.rollback()
        raise _typed_error(error) from error
    suggestions.update_suggestion(
        session, profile.id, suggestion.id, material_id=result.material.id
    )
    session.commit()
    return AcceptOut(
        material_id=result.material.id,
        deduped=result.deduped,
        job_kind=result.job_kind,
    )


@router.post("/{source_id}/backup", response_model=BackupUploadOut)
def upload_backup(
    source_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> BackupUploadOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    settings = request.app.state.settings
    try:
        data = build_backup(settings.db_path, settings.blobs_dir, database_url=settings.db_url)
    except BackupError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = f"manual-{stamp}.zip"
    try:
        result = external.upload_backup(source, name, data)
    except ExtensionError as error:
        raise _typed_error(error) from error
    return BackupUploadOut(**result)


@router.get("/{source_id}/backups", response_model=RemoteBackupListOut)
def list_remote_backups(
    source_id: str,
    session: Session = Depends(get_session),
) -> RemoteBackupListOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        rows = external.list_remote_backups(source)
    except ExtensionError as error:
        raise _typed_error(error) from error
    return RemoteBackupListOut(backups=[RemoteBackupOut(**row) for row in rows])


@router.get("/{source_id}/backups/{name}")
def download_remote_backup(
    source_id: str,
    name: str,
    session: Session = Depends(get_session),
) -> Response:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        data = external.remote_backup_data(source, name)
    except ExtensionError as error:
        raise _typed_error(error) from error
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/{source_id}/backups/{name}/restore", response_model=RestoreOut)
def restore_remote_backup(
    source_id: str,
    name: str,
    request: Request,
    session: Session = Depends(get_session),
) -> RestoreOut:
    profile = ensure_default_profile(session)
    source = _owned_source(session, profile.id, source_id)
    try:
        data = external.remote_backup_data(source, name)
    except ExtensionError as error:
        raise _typed_error(error) from error
    try:
        result = apply_restore(request, data)
    except HTTPException:
        raise
    return RestoreOut(**result)
