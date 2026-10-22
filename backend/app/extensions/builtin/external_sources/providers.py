"""Source-provider catalog (plan 86 A, ADR-214).

The catalog is app data: providers are rows plus adapter classes, validated
at registration, never DB CHECK values. It is study-local because no second
family host runs source adapters yet; a promotion to a family contract is a
future two-app-rule decision, not a silent copy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ....core.vocab import AuthKind, ExternalSourceKind
from ...errors import ExtensionError


@dataclass(frozen=True)
class SecretSlot:
    name: str
    label: str
    required: bool


@dataclass(frozen=True)
class OAuthProvider:
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    redirect_port: int
    client_id_env: str
    client_secret_env: str
    extra_auth_params: dict[str, str]
    api_base: str
    content_base: str | None = None


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    kinds: tuple[str, ...]
    default_kind: str
    auth_kind: str
    url_required: bool
    fields: tuple[str, ...]
    supports_backup: bool
    adapter: str
    api_base: str | None = None
    secret_slots: tuple[SecretSlot, ...] = ()
    oauth: OAuthProvider | None = None


@dataclass(frozen=True)
class ProviderCatalog:
    providers: dict[str, Provider]
    order: tuple[str, ...]
    secret_disclosure: str


def _catalog_path() -> Path:
    return Path(__file__).with_name("providers.json")


@lru_cache(maxsize=1)
def catalog() -> ProviderCatalog:
    raw = json.loads(_catalog_path().read_text(encoding="utf-8"))
    providers: dict[str, Provider] = {}
    for provider_id, row in raw["providers"].items():
        oauth_raw = row.get("oauth")
        oauth = None
        if isinstance(oauth_raw, dict):
            oauth = OAuthProvider(
                authorize_url=str(oauth_raw["authorizeUrl"]),
                token_url=str(oauth_raw["tokenUrl"]),
                scopes=tuple(str(scope) for scope in oauth_raw.get("scopes", [])),
                redirect_port=int(oauth_raw["redirectPort"]),
                client_id_env=str(oauth_raw["clientIdEnv"]),
                client_secret_env=str(oauth_raw["clientSecretEnv"]),
                extra_auth_params={
                    str(key): str(value)
                    for key, value in oauth_raw.get("extraAuthParams", {}).items()
                },
                api_base=str(oauth_raw["apiBase"]),
                content_base=(
                    str(oauth_raw["contentBase"]) if oauth_raw.get("contentBase") else None
                ),
            )
        slots = tuple(
            SecretSlot(
                name=str(slot["name"]),
                label=str(slot["label"]),
                required=bool(slot.get("required", False)),
            )
            for slot in row.get("secretSlots", [])
        )
        providers[provider_id] = Provider(
            id=provider_id,
            label=str(row["label"]),
            kinds=tuple(str(kind) for kind in row["kinds"]),
            default_kind=str(row["defaultKind"]),
            auth_kind=str(row["authKind"]),
            url_required=bool(row.get("urlRequired", True)),
            fields=tuple(str(field) for field in row.get("fields", [])),
            supports_backup=bool(row.get("supportsBackup", False)),
            adapter=str(row["adapter"]),
            api_base=str(row["apiBase"]) if row.get("apiBase") else None,
            secret_slots=slots,
            oauth=oauth,
        )
    order = tuple(str(provider_id) for provider_id in raw["providerOrder"])
    return ProviderCatalog(
        providers=providers,
        order=order,
        secret_disclosure=str(raw["secretDisclosure"]),
    )


def provider_ids() -> tuple[str, ...]:
    return catalog().order


def get_provider(provider_id: str) -> Provider:
    provider = catalog().providers.get(provider_id)
    if provider is None:
        raise ExtensionError(
            "invalid",
            f"unknown source provider '{provider_id}' (allowed: {', '.join(provider_ids())})",
        )
    return provider


def provider_for_kind(kind: str) -> str:
    for provider in catalog().providers.values():
        if kind in provider.kinds:
            return provider.id
    raise ExtensionError("invalid", f"no source provider handles kind '{kind}'")


def validate_registration(
    provider_id: str,
    kind: str,
    auth_kind: str | None = None,
) -> Provider:
    provider = get_provider(provider_id)
    if kind not in provider.kinds:
        raise ExtensionError(
            "invalid",
            f"provider '{provider_id}' does not handle kind '{kind}'",
        )
    if auth_kind is not None and auth_kind != provider.auth_kind:
        raise ExtensionError(
            "invalid",
            f"provider '{provider_id}' requires auth_kind '{provider.auth_kind}'",
        )
    return provider


def kinds_for_provider(provider_id: str) -> tuple[str, ...]:
    return get_provider(provider_id).kinds


def serialized_catalog() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = []
    for provider_id in provider_ids():
        provider = catalog().providers[provider_id]
        row: dict[str, Any] = {
            "id": provider.id,
            "label": provider.label,
            "kinds": list(provider.kinds),
            "default_kind": provider.default_kind,
            "auth_kind": provider.auth_kind,
            "url_required": provider.url_required,
            "fields": list(provider.fields),
            "supports_backup": provider.supports_backup,
            "secret_slots": [
                {"name": slot.name, "label": slot.label, "required": slot.required}
                for slot in provider.secret_slots
            ],
        }
        if provider.oauth is not None:
            row["oauth"] = {
                "scopes": list(provider.oauth.scopes),
                "client_id_env": provider.oauth.client_id_env,
            }
        data.append(row)
    return data


def kind_defaults(kind: str) -> tuple[str, str]:
    provider_id = provider_for_kind(kind)
    provider = get_provider(provider_id)
    auth_kind = provider.auth_kind
    if auth_kind not in {member.value for member in AuthKind}:
        auth_kind = AuthKind.NONE.value
    return provider_id, auth_kind


def parse_kind(provider_id: str, kind: str | None) -> str:
    provider = get_provider(provider_id)
    if kind is None or kind == "":
        return provider.default_kind
    try:
        parsed = ExternalSourceKind.parse(kind)
    except ValueError as error:
        raise ExtensionError("invalid", str(error)) from error
    if parsed.value not in provider.kinds:
        raise ExtensionError("invalid", f"provider '{provider_id}' does not handle kind '{kind}'")
    return parsed.value
