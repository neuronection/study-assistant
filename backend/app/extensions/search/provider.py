"""App-side shell over the vendored family web-search core.

Lives in the extension subsystem home (D24, plan 32 Phase 7) — the
ADR-0035 web-search family is connector-kind. The wire contract
(adapters, normalization, error taxonomy, probe) lives in the vendored
contracts/search_providers.py copy (providers_contract.py — dev canonical,
never edited here). This module adds the app policy ADR-0031 keeps local:
persistence in Profile.preferences (`search_providers[]`), per-provider
keyring slots, the lazy migration from the pre-plan-28 single-provider
preference, and the ordered-fallback search used by chat tools, discovery,
genesis and external sources.

The web-search provider wire shapes (ADR-0035) are the vendored module's;
this file stays the product shell. FETCH is app-side policy too, but its
egress crosses the family polite perimeter
(:mod:`app.extensions.search.polite_fetch` — SSRF guard, resolve-then-
connect pinning, per-hop revalidation, size cap, conditional GET; plan 37
§8 / 4.8) instead of raw httpx.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from ...core.secrets import delete_secret, get_secret, set_secret
from ...domain.models import Profile
from ...pipelines.convert import html_to_markdown
from ..polite_http import HostRateLimiter, PoliteHttpError, Resolver
from .polite_fetch import FETCH_MAX_BYTES, Sleep, fetch_document
from .providers_contract import (
    PROVIDER_TYPES,
    SearchError,
    normalize_provider_config,
    perform_search,
    probe_provider,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PROVIDER_TYPES",
    "SearchError",
    "delete_search_provider",
    "list_search_providers",
    "move_search_provider",
    "perform_fetch",
    "perform_search",
    "probe_provider",
    "provider_key_ref",
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
        found = next(
            (i for i, entry in enumerate(providers) if entry["id"] == provider_id), None
        )
        if found is None:
            raise SearchError("bad_request", f"provider '{provider_id}' not found")
        replace_index = found

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
    providers: Sequence[Mapping[str, Any]],
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
# FETCH stays app-side (markdown conversion is product policy) — but the
# egress crosses the family polite perimeter (plan 37 §8 / 4.8).
# ---------------------------------------------------------------------------

# Charter typed code → ADR-0035 SearchError kind (the D4 projection's
# inverse at this boundary; the SearchError taxonomy stays untouched).
_FETCH_KIND_BY_CODE: dict[str, str] = {
    "auth": "auth",
    "rate-limited": "rate_limit",
    "unreachable": "unreachable",
    "net-denied": "bad_request",
}


def _fetch_search_error(error: PoliteHttpError, url: str) -> SearchError:
    """Project a charter error onto the ADR-0035 kind, sanitizing the one
    detail that can carry a raw transport exception string (F22)."""
    if error.code == "unreachable":
        try:
            host = urlparse(url).hostname or url
        except ValueError:  # a malformed URL must not re-raise here
            host = url
        message = f"fetch failed: could not reach {host}"
        logger.warning("fetch unreachable host=%s detail=%s", host, error.detail)
    else:
        message = f"fetch failed: {error.detail}"
    return SearchError(
        _FETCH_KIND_BY_CODE.get(error.code, "protocol"),
        message,
        http_status=error.status,
    )


def perform_fetch(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    max_chars: int = FETCH_MAX_CHARS,
    state: Mapping[str, object] | None = None,
    resolver: Resolver | None = None,
    rate: HostRateLimiter | None = None,
    sleep: Sleep | None = None,
    clock: Callable[[], float] | None = None,
    rng: Callable[[float], float] | None = None,
) -> str:
    """Fetch one URL through the guarded runtime and return markdown/text.

    ``transport`` / ``resolver`` / ``rate`` / ``sleep`` / ``clock`` /
    ``rng`` are the offline test seams (``httpx.MockTransport`` + a
    deterministic resolver/clock — no network in tests); production calls
    pass only the URL. ``state`` is the conditional-GET cursor
    (``{etag, last_modified}``); a ``304`` is reported as a typed
    ``protocol`` error because a fetch has no cached body to fall back on.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise SearchError("bad_request", "FETCH expects an http(s) URL")
    try:
        result = fetch_document(
            url,
            transport=transport,
            state=state,
            resolver=resolver,
            rate=rate,
            sleep=sleep,
            clock=clock,
            rng=rng,
        )
    except PoliteHttpError as error:
        raise _fetch_search_error(error, url) from error
    if result.not_modified:
        raise SearchError(
            "protocol", "fetch returned 304 (not modified)", http_status=304
        )
    if result.status != 200:
        raise SearchError(
            "protocol", f"fetch returned {result.status}", http_status=result.status
        )
    if result.truncated:
        raise SearchError(
            "protocol",
            f"fetch response exceeded the {FETCH_MAX_BYTES // (1024 * 1024)} MiB size cap",
            http_status=result.status,
        )
    text = html_to_markdown(result.text) if "html" in result.content_type else result.text
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    if not text:
        raise SearchError("protocol", "fetch returned no readable content")
    return text
