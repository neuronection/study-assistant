"""Host adapter for the bundled external-sources connector (plan 73-E/86).

The connector lives in the extension subsystem
(:mod:`app.extensions.builtin.external_sources` — D24); this module is the
HOST side of the boundary: it injects the suggestion funnel
(:func:`app.services.content.discovery.record_scan_suggestion`) into the
connector's scan legs and re-exports the cadence policy the scheduler
consumes. Sync orchestration (the scheduler, overlap guard, due times)
stays here — D24 rule 4. Plan 86 adds the provider-seam host verbs: secret
slots, OAuth start/complete/disconnect, acceptance and the backup
destination.
"""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions.builtin.external_sources import (
    DEFAULT_SCAN_INTERVAL_SEC,
    MIN_SCAN_INTERVAL_SEC,
)
from app.extensions.builtin.external_sources import (
    effective_interval as _connector_effective_interval,
)
from app.extensions.builtin.external_sources import (
    next_due_at as _connector_next_due_at,
)
from app.extensions.builtin.external_sources import (
    run_scan as _connector_run_scan,
)
from app.extensions.builtin.external_sources import (
    validate_source as _connector_validate_source,
)
from app.extensions.builtin.external_sources.adapters import build_adapter
from app.extensions.builtin.external_sources.engine import entry_from_suggestion, fetch_entry
from app.extensions.builtin.external_sources.providers import (
    catalog,
    get_provider,
    serialized_catalog,
)
from app.extensions.errors import ExtensionError

from ...jobs.payloads import IngestPayload, UrlImportPayload
from .discovery import record_scan_suggestion

__all__ = [
    "DEFAULT_SCAN_INTERVAL_SEC",
    "MIN_SCAN_INTERVAL_SEC",
    "ExtensionError",
    "accept_suggestion",
    "complete_oauth",
    "connect_oauth",
    "delete_source_secret",
    "disconnect_oauth",
    "effective_interval",
    "list_remote_backups",
    "next_due_at",
    "oauth_start",
    "oauth_status",
    "provider_catalog",
    "remote_backup_data",
    "run_scan",
    "secrets_configured",
    "set_source_secret",
    "upload_backup",
    "validate_source",
]



def validate_source(
    kind: str,
    url: str,
    options: dict[str, Any] | None,
    provider: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    return _connector_validate_source(kind, url, options, provider)


def effective_interval(source: Any) -> int:
    return _connector_effective_interval(source)


def next_due_at(source: Any) -> datetime:
    return _connector_next_due_at(source)


def run_scan(session: Session, source: Any) -> dict[str, int]:
    return _connector_run_scan(session, source, record_scan_suggestion)


def provider_catalog() -> dict[str, Any]:
    return {
        "providers": serialized_catalog(),
        "secret_disclosure": catalog().secret_disclosure,
    }


def _secret_ref(source_id: str, slot: str) -> str:
    return f"source:{source_id}:{slot}"


def _validate_slot(source: Any, slot: str) -> None:
    provider = get_provider(source.provider)
    names = {item.name for item in provider.secret_slots}
    if slot not in names:
        raise ExtensionError("invalid", f"provider '{provider.id}' has no secret slot '{slot}'")


def secrets_configured(source: Any) -> dict[str, bool]:
    from app.core.secrets import get_secret
    from app.extensions.builtin.external_sources.providers import provider_for_kind

    provider = get_provider(source.provider or provider_for_kind(source.kind))
    result: dict[str, bool] = {}
    for slot in provider.secret_slots:
        result[slot.name] = get_secret(_secret_ref(source.id, slot.name)) is not None
    if provider.auth_kind == "oauth2":
        from app.services.study import cloud_oauth

        result["oauth"] = (
            cloud_oauth.source_vault_for(source.id).find(source.id) is not None
        )
    return result


def set_source_secret(source: Any, slot: str, value: str) -> None:
    from app.core.secrets import set_secret

    _validate_slot(source, slot)
    cleaned = (value or "").strip()
    if not cleaned:
        raise ExtensionError("invalid", "secret value cannot be empty")
    set_secret(_secret_ref(source.id, slot), cleaned)


def delete_source_secret(source: Any, slot: str) -> None:
    from app.core.secrets import delete_secret

    _validate_slot(source, slot)
    delete_secret(_secret_ref(source.id, slot))


def _oauth_client(source: Any) -> Any:
    from app.services.study import cloud_oauth

    if source.auth_kind != "oauth2":
        raise ExtensionError("invalid", "this source does not use OAuth")
    try:
        return cloud_oauth.source_client_for(source.provider)
    except Exception as error:
        code = getattr(error, "code", "needs-config")
        detail = getattr(error, "detail", str(error))
        raise ExtensionError(code, detail) from error


def oauth_start(source: Any, *, principal_id: str) -> dict[str, str]:
    """Begin a bind. State is single-use, expiring and principal-bound (E12).

    The old in-memory `_PENDING_OAUTH` map was process-local and unbound —
    migrating onto the kit's state store closes that (a restart mid-flow now
    fails closed instead of silently losing the flow).
    """
    import nx_auth.oauth as nx_oauth

    from app.services.study import cloud_oauth

    client = _oauth_client(source)
    store = cloud_oauth.KeyringStateStore(cloud_oauth.source_ref(source.id))
    try:
        offer = nx_oauth.authorize(client, store=store, principal_id=principal_id)
    except nx_oauth.OAuthError as error:
        raise ExtensionError(error.code, error.detail) from error
    return {
        "authorize_url": offer.authorize_url,
        "redirect_uri": client.redirect_uri,
        "state": offer.record.state,
    }


def complete_oauth(
    source: Any,
    code: str,
    state: str,
    *,
    principal_id: str,
    transport: Any | None = None,
) -> None:
    import nx_auth.oauth as nx_oauth

    from app.services.study import cloud_oauth

    client = _oauth_client(source)
    store = cloud_oauth.KeyringStateStore(cloud_oauth.source_ref(source.id))
    try:
        record = store.consume(state, principal_id=principal_id)
    except nx_oauth.OAuthError as error:
        raise ExtensionError(error.code, error.detail) from error
    try:
        tokens = nx_oauth.exchange_code(
            client,
            code=code,
            code_verifier=record.code_verifier,
            transport=cloud_oauth.HttpxTokenTransport(_token_http(transport)),
            redirect_uri=record.redirect_uri,
        )
    except nx_oauth.OAuthError as error:
        raise ExtensionError(error.code, error.detail) from error
    cloud_oauth.source_vault_for(source.id).seal(source.id, tokens)


def connect_oauth(source: Any, *, transport: Any | None = None) -> None:
    from app.services.study import cloud_oauth

    client = _oauth_client(source)
    try:
        cloud_oauth.connect_loopback(
            client,
            cloud_oauth.source_vault_for(source.id),
            source.id,
            transport=cloud_oauth.HttpxTokenTransport(_token_http(transport)),
        )
    except cloud_oauth.OAuthError as error:
        raise ExtensionError(error.code, error.detail) from error


def disconnect_oauth(source: Any) -> None:
    from app.services.study import cloud_oauth

    cloud_oauth.source_vault_for(source.id).clear(source.id)


def oauth_status(source: Any) -> str:
    from app.services.study import cloud_oauth

    return cloud_oauth.token_status(cloud_oauth.source_vault_for(source.id).find(source.id))


def _token_http(transport: Any | None = None) -> Any:
    """A blocking client for the kit's synchronous token seam.

    ``transport`` is injectable so tests never touch the network — the same
    seam the kit's ``TokenTransport`` expects.
    """
    import httpx

    if transport is not None:
        return httpx.Client(transport=transport)
    return httpx.Client(timeout=20.0, follow_redirects=False)


@dataclass
class NativeMaterialResult:
    material: Any
    deduped: bool
    job_kind: str


def _citation_fields(meta: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if meta.get("citation_kind"):
        fields["citation_kind"] = str(meta["citation_kind"])
    if meta.get("authors"):
        fields["citation_authors"] = [
            {"name": str(name)} for name in meta["authors"] if str(name).strip()
        ]
    if isinstance(meta.get("year"), int):
        fields["citation_year"] = int(meta["year"])
    if meta.get("doi"):
        fields["citation_doi"] = str(meta["doi"])[:255]
    if meta.get("container"):
        fields["citation_container"] = str(meta["container"])[:300]
    return fields


def accept_suggestion(
    session: Session,
    source: Any,
    suggestion: Any,
    blobs: Any,
    runner: Any,
) -> NativeMaterialResult:
    from app.core.urls import normalize_url
    from app.core.vocab import MaterialKind, MaterialStatus
    from app.domain.models import Material
    from app.jobs.runner import JobRunner
    from app.services.content.materials import MaterialsService

    meta = suggestion.meta if isinstance(suggestion.meta, dict) else {}
    entry = entry_from_suggestion(suggestion)
    citation = _citation_fields(meta)

    if entry.meta.get("material_kind") == "link" and not entry.meta.get("attachment_url"):
        material, deduped = MaterialsService(session, blobs).create_link(
            profile_id=source.profile_id,
            course_id=source.course_id,
            url=entry.url,
            title=suggestion.title,
        )
        for field, value in citation.items():
            setattr(material, field, value)
        session.flush()
        return NativeMaterialResult(material=material, deduped=deduped, job_kind="link")

    enclosure = str(meta.get("enclosure_url") or "").strip()
    if enclosure:
        parsed = urlparse(enclosure)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ExtensionError("invalid", "enclosure URL is not http(s)")
        material_kind = str(meta.get("material_kind") or MaterialKind.AUDIO.value)
        media_kind = (
            MaterialKind.VIDEO.value
            if material_kind == MaterialKind.VIDEO.value
            else MaterialKind.AUDIO.value
        )
        name = str(meta.get("remote_name") or "") or parsed.path.rsplit("/", 1)[-1] or "media"
        material = Material(
            profile_id=source.profile_id,
            course_id=source.course_id,
            kind=media_kind,
            title=suggestion.title[:300],
            blob_sha=None,
            filename=name[:500],
            mime=str(meta.get("enclosure_type") or "") or None,
            status=MaterialStatus.PENDING.value,
            source_url=enclosure,
            source_url_norm=normalize_url(enclosure),
        )
        session.add(material)
        session.flush()
        JobRunner.enqueue(
            session,
            "url_import",
            UrlImportPayload(material_id=material.id, action="transcribe_audio"),
        )
        runner.wake()
        return NativeMaterialResult(material=material, deduped=False, job_kind="url_import")

    data = fetch_entry(source, entry)
    sha = hashlib.sha256(data).hexdigest()
    existing = session.scalars(
        select(Material).where(
            Material.profile_id == source.profile_id,
            Material.course_id == source.course_id,
            Material.content_hash == sha,
            Material.status != MaterialStatus.FAILED.value,
        )
    ).first()
    if existing is not None:
        for field, value in citation.items():
            setattr(existing, field, value)
        return NativeMaterialResult(material=existing, deduped=True, job_kind="none")
    mime = entry.mime or mimetypes.guess_type(entry.name)[0]
    stored = blobs.put(data, mime=mime, session=session)
    kind = str(meta.get("material_kind") or "pdf")
    material = Material(
        profile_id=source.profile_id,
        course_id=source.course_id,
        kind=kind,
        title=suggestion.title[:300],
        blob_sha=stored.sha256,
        filename=entry.name[:500],
        mime=mime,
        status=MaterialStatus.PENDING.value,
        content_hash=sha,
        source_url=entry.url,
    )
    for field, value in citation.items():
        setattr(material, field, value)
    session.add(material)
    session.flush()
    JobRunner.enqueue(
        session,
        "ingest",
        IngestPayload(material_id=material.id, blob_sha=material.blob_sha or stored.sha256),
    )
    runner.wake()
    return NativeMaterialResult(material=material, deduped=False, job_kind="ingest")


def upload_backup(source: Any, name: str, data: bytes) -> dict[str, Any]:
    provider = get_provider(source.provider)
    if not provider.supports_backup:
        raise ExtensionError("unsupported", f"{provider.label} is not a backup destination")
    adapter = build_adapter(source.provider)
    location = adapter.put(source, name, data)
    return {"name": name, "size": len(data), "location": location}


def list_remote_backups(source: Any) -> list[dict[str, Any]]:
    from app.services.platform.backup import STAMP_PATTERN

    adapter = build_adapter(source.provider)
    rows: list[dict[str, Any]] = []
    for entry in adapter.list(source):
        if STAMP_PATTERN.match(entry.name):
            rows.append(
                {
                    "name": entry.name,
                    "size": entry.size,
                    "created_at": entry.mtime,
                    "remote_id": entry.remote_id,
                }
            )
    rows.sort(key=lambda row: str(row["name"]), reverse=True)
    return rows


def remote_backup_data(source: Any, name: str) -> bytes:
    adapter = build_adapter(source.provider)
    for entry in adapter.list(source):
        if entry.name == name:
            data: bytes = adapter.fetch(source, entry)
            return data
    raise ExtensionError("not-found", f"remote backup not found: {name}")
