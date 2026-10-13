"""App-side shell over the vendored family web-search core.

The wire contract (adapters, normalization, error taxonomy, probe) lives in
the vendored contracts/search_providers.py copy (providers_contract.py —
dev canonical, ADR-0035 / plan 28, never edited here). This module adds the
app policy ADR-0031 keeps local: persistence in Profile.preferences
(`search_providers[]`), per-provider keyring slots, the lazy migration from
the pre-plan-28 single-provider preference, and the ordered-fallback search
used by chat tools, discovery, genesis and external sources.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping

import httpx
from sqlalchemy.orm import Session

from ..core.secrets import delete_secret, get_secret, set_secret
from ..domain.models import Profile
from ..pipelines.convert import html_to_markdown
from .providers_contract import (
    PROVIDER_TYPES,
    SearchError,
    normalize_provider_config,
    perform_search,
    probe_provider,
)

__all__ = [
    "PROVIDER_TYPES",
    "SearchError",
    "delete_search_provider",
    "list_search_providers",
    "move_search_provider",
    "perform_fetch",
    "perform_search",
    "provider_key_ref",
    "probe_provider",
    "search_provider_views",
    "search_with_fallback",
    "search_with_fallback_configs",
    "upsert_search_provider",
]

SEARCH_PROVIDERS_KEY = "search_providers"
LEGACY_SEARCH_PROVIDER_KEY = "search_provider"
LEGACY_SEARCH_KEYRING_REF = "search:api_key"  # pre-plan-28 single key slot

FETCH_MAX_CHARS = 4000


def provider_key_ref(provider_id: str) -> str:
    """Keyring slot for one provider's API key (desktop: search-provider:{id})."""
    return f"search:{provider_id}"


# ---------------------------------------------------------------------------
# Persistence (Profile.preferences.search_providers[]) + lazy migration
# ---------------------------------------------------------------------------

def _providers_raw(preferences: Mapping[str, Any] | None) -> list[Any]:
    raw = preferences.get(SEARCH_PROVIDERS_KEY) if isinstance(preferences, Mapping) else None
    return [entry for entry in raw if isinstance(entry, Mapping)] if isinstance(raw, list) else []


def list_search_providers(session: Session, profile_id: str) -> list[dict[str, Any]]:
    """Normalized provider configs, ordered; lazily migrates the legacy
    single-provider preference (base_url/flavor + one key slot) into the
    family providers[] shape on first read."""
    profile = session.get(Profile, profile_id)
    preferences = profile.preferences if profile is not None else None
    if not isinstance(preferences, dict):
        preferences = {}
    raw = _providers_raw(preferences)

    legacy = preferences.get(LEGACY_SEARCH_PROVIDER_KEY)
    if not raw and isinstance(legacy, Mapping):
        base_url = str(legacy.get("base_url", "") or "").strip().rstrip("/")
        flavor = str(legacy.get("flavor", "") or "").strip()
        if base_url and flavor in ("tavily", "searxng"):
            entry = {
                "id": "legacy",
                "name": "Tavily" if flavor == "tavily" else "SearXNG",
                "type": flavor,
                "enabled": True,
                "base_url": base_url,
            }
            legacy_key = get_secret(LEGACY_SEARCH_KEYRING_REF)
            if legacy_key:
                set_secret(provider_key_ref("legacy"), legacy_key)
                delete_secret(LEGACY_SEARCH_KEYRING_REF)
            migrated = dict(preferences)
            migrated[SEARCH_PROVIDERS_KEY] = [entry]
            migrated.pop(LEGACY_SEARCH_PROVIDER_KEY, None)
            if profile is not None:
                profile.preferences = migrated
                session.commit()
            raw = [entry]

    providers: list[dict[str, Any]] = []
    for item in raw:
        try:
            providers.append(normalize_provider_config(item))
        except SearchError:
            continue  # a corrupt entry never breaks the whole list
    return providers


def _write_providers(session: Session, profile_id: str, providers: list[dict[str, Any]]) -> None:
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise SearchError("bad_request", "profile not found")
    preferences = dict(profile.preferences or {})
    preferences[SEARCH_PROVIDERS_KEY] = providers
    preferences.pop(LEGACY_SEARCH_PROVIDER_KEY, None)
    profile.preferences = preferences


def search_provider_views(session: Session, profile_id: str) -> list[dict[str, Any]]:
    """Provider configs + key presence, for the settings UI."""
    views: list[dict[str, Any]] = []
    for provider in list_search_providers(session, profile_id):
        views.append(
            {
                **provider,
                "key_set": bool(get_secret(provider_key_ref(provider["id"]))),
            }
        )
    return views


def _mask_key_hint(api_key: str) -> str:
    tail = api_key[-4:]
    return f"••••{tail}" if len(api_key) > 4 else "••••"


def upsert_search_provider(
    session: Session,
    profile_id: str,
    body: Mapping[str, Any],
    *,
    provider_id: str | None = None,
) -> dict[str, Any]:
    """Create or update one provider. `api_key` semantics (desktop): absent
    keeps the stored key, empty string clears it, a value stores it."""
    providers = list_search_providers(session, profile_id)
    raw = dict(body)
    api_key = raw.pop("api_key", None)

    if provider_id is None:
        provider_id = uuid.uuid4().hex[:8]
        providers.append({})  # placeholder replaced by the normalized entry below
        replace_index = len(providers) - 1
    else:
        replace_index = next(
            (i for i, entry in enumerate(providers) if entry["id"] == provider_id), None
        )
        if replace_index is None:
            raise SearchError("bad_request", f"provider '{provider_id}' not found")

    existing = providers[replace_index] if providers[replace_index] else {}
    merged = {**existing, **{key: value for key, value in raw.items() if value is not None}}
    merged["id"] = provider_id
    normalized = normalize_provider_config(merged)
    # normalize may have dropped the explicit enabled default on create
    if "enabled" not in merged and "enabled" not in existing:
        normalized["enabled"] = True

    key_ref = provider_key_ref(provider_id)
    if api_key is not None:
        if str(api_key).strip():
            set_secret(key_ref, str(api_key).strip())
            normalized["key_hint"] = _mask_key_hint(str(api_key).strip())
        else:
            delete_secret(key_ref)
            normalized["key_hint"] = None

    providers[replace_index] = normalized
    _write_providers(session, profile_id, providers)
    session.commit()
    return {**normalized, "key_set": bool(get_secret(key_ref))}


def delete_search_provider(session: Session, profile_id: str, provider_id: str) -> bool:
    providers = list_search_providers(session, profile_id)
    remaining = [entry for entry in providers if entry["id"] != provider_id]
    if len(remaining) == len(providers):
        return False
    _write_providers(session, profile_id, remaining)
    delete_secret(provider_key_ref(provider_id))
    session.commit()
    return True


def move_search_provider(
    session: Session, profile_id: str, provider_id: str, direction: str
) -> list[dict[str, Any]]:
    """Reorder (family semantics: the first enabled provider that answers wins)."""
    if direction not in ("up", "down"):
        raise SearchError("bad_request", "direction must be 'up' or 'down'")
    providers = list_search_providers(session, profile_id)
    index = next((i for i, entry in enumerate(providers) if entry["id"] == provider_id), None)
    if index is None:
        raise SearchError("bad_request", f"provider '{provider_id}' not found")
    swap = index - 1 if direction == "up" else index + 1
    if 0 <= swap < len(providers):
        providers[index], providers[swap] = providers[swap], providers[index]
        _write_providers(session, profile_id, providers)
        session.commit()
    return search_provider_views(session, profile_id)


# ---------------------------------------------------------------------------
# Ordered fallback across enabled providers
# ---------------------------------------------------------------------------

def search_with_fallback_configs(
    providers: list[Mapping[str, Any]],
    keys: Mapping[str, str],
    query: str,
    *,
    transport: httpx.BaseTransport | None = None,
    limit: int | None = None,
) -> list[dict[str, str]] | None:
    """First enabled provider that answers wins; None = none enabled; all
    failing raises the last error (kind=unreachable keeps callers' existing
    skip semantics)."""
    enabled = [provider for provider in providers if provider.get("enabled", True)]
    if not enabled:
        return None
    last_error: SearchError | None = None
    for provider in enabled:
        try:
            return perform_search(
                provider,
                query,
                api_key=keys.get(str(provider["id"]), ""),
                transport=transport,
                limit=limit,
            )
        except SearchError as error:
            last_error = error
    raise SearchError(
        "unreachable",
        last_error.message if last_error else "all search providers failed",
    )


def search_with_fallback(
    session: Session,
    profile_id: str,
    query: str,
    *,
    transport: httpx.BaseTransport | None = None,
    limit: int | None = None,
) -> list[dict[str, str]] | None:
    providers = list_search_providers(session, profile_id)
    keys = {
        provider["id"]: get_secret(provider_key_ref(provider["id"])) or ""
        for provider in providers
    }
    return search_with_fallback_configs(providers, keys, query, transport=transport, limit=limit)


# ---------------------------------------------------------------------------
# FETCH stays app-side (markdown conversion is product policy)
# ---------------------------------------------------------------------------

def perform_fetch(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    max_chars: int = FETCH_MAX_CHARS,
) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise SearchError("bad_request", "FETCH expects an http(s) URL")
    try:
        with httpx.Client(
            timeout=httpx.Timeout(1.5, read=10.0, write=10.0, pool=1.5),
            transport=transport,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as error:
        raise SearchError("unreachable", f"fetch failed: {error}") from error
    if response.status_code != 200:
        raise SearchError(
            "protocol", f"fetch returned {response.status_code}", http_status=response.status_code
        )
    content_type = response.headers.get("content-type", "")
    text = html_to_markdown(response.text) if "html" in content_type else response.text
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    if not text:
        raise SearchError("protocol", "fetch returned no readable content")
    return text
