"""Family web-search provider core (contract, ADR-0035 / plan 28).

Canonical copy lives in the dev repo (contracts/search_providers.py) and is
vendored byte-identical into the product backends via
dev/scripts/sync-search-providers.sh — edit the canonical copy only, never a
vendored copy (ADR-0031 sync-and-gate).

The contract this module freezes (desktop-assistant's TS adapters in
src/main/services/search-providers.ts are the reference implementation):

- provider types: searxng | tavily | brave | exa | serper | google-pse
- config shape (snake_case form of the desktop SearchProviderConfig):
  id, name, type, enabled, base_url, google_cx, key_hint, timeout_ms,
  max_results
- normalized hit: {title, url, content} — title falls back to the url,
  content falls back to snippet/description/text, content caps at 800 chars
- error taxonomy (SearchError.kind): missing_key | missing_config |
  unknown_type | bad_request | auth | rate_limit | unreachable |
  json_disabled | protocol
- probe statuses: ok | unreachable | auth | rate_limit | json_disabled |
  error

Policy stays app-side (ADR-0031): persistence, secret storage, scope,
which providers a user enables, and how failures fall back. This module is
pure functions over plain dicts; httpx is the only dependency and the
transport is injectable for tests.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Mapping

import httpx

PROVIDER_TYPES = ("searxng", "tavily", "brave", "exa", "serper", "google-pse")

DEFAULT_TIMEOUT_MS = 8000
DEFAULT_MAX_RESULTS = 5
CONTENT_MAX_CHARS = 800

DEFAULT_BASE_URLS: dict[str, str] = {
    "tavily": "https://api.tavily.com",
    "brave": "https://api.search.brave.com/res/v1",
    "exa": "https://api.exa.ai",
    "serper": "https://google.serper.dev",
    "google-pse": "https://www.googleapis.com/customsearch/v1",
}

# Types whose catalog entry marks a base URL as required (searxng is
# self-hosted; everything else has a hosted default).
BASE_URL_REQUIRED = ("searxng",)


class SearchErrorKind(str, Enum):
    MISSING_KEY = "missing_key"
    MISSING_CONFIG = "missing_config"
    UNKNOWN_TYPE = "unknown_type"
    BAD_REQUEST = "bad_request"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    UNREACHABLE = "unreachable"
    JSON_DISABLED = "json_disabled"
    PROTOCOL = "protocol"


class SearchError(Exception):
    """One family error type; `kind` is the taxonomy, `message` is human."""

    def __init__(
        self,
        kind: str | SearchErrorKind,
        message: str,
        http_status: int | None = None,
    ) -> None:
        self.kind = SearchErrorKind(kind).value
        self.message = message
        self.http_status = http_status
        super().__init__(message)


# ---------------------------------------------------------------------------
# Config normalization
# ---------------------------------------------------------------------------

def normalize_provider_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate + clamp one provider config dict (raises SearchError)."""
    if not isinstance(raw, Mapping):
        raise SearchError(SearchErrorKind.BAD_REQUEST, "provider config must be an object")
    provider_id = str(raw.get("id", "")).strip()
    if not provider_id or len(provider_id) > 64:
        raise SearchError(SearchErrorKind.BAD_REQUEST, "provider id must be 1-64 chars")
    p_type = str(raw.get("type", "")).strip()
    if p_type not in PROVIDER_TYPES:
        raise SearchError(
            SearchErrorKind.UNKNOWN_TYPE,
            f"unknown search provider type '{p_type}'",
        )
    name = str(raw.get("name", "")).strip() or p_type
    enabled = bool(raw.get("enabled", True))
    base_url = str(raw.get("base_url", "") or "").strip().rstrip("/")
    if base_url and not base_url.startswith(("http://", "https://")):
        raise SearchError(SearchErrorKind.BAD_REQUEST, "base_url must be an http(s) URL")
    if not base_url and p_type in BASE_URL_REQUIRED:
        raise SearchError(
            SearchErrorKind.MISSING_CONFIG,
            "SearXNG needs a base URL (self-hosted instance).",
        )
    google_cx = str(raw.get("google_cx", "") or "").strip() or None
    key_hint = str(raw.get("key_hint", "") or "").strip() or None
    try:
        timeout_ms = int(raw.get("timeout_ms", DEFAULT_TIMEOUT_MS))
    except (TypeError, ValueError):
        timeout_ms = DEFAULT_TIMEOUT_MS
    timeout_ms = max(500, min(timeout_ms, 30_000))
    try:
        max_results = int(raw.get("max_results", DEFAULT_MAX_RESULTS))
    except (TypeError, ValueError):
        max_results = DEFAULT_MAX_RESULTS
    max_results = max(1, min(max_results, 10))
    return {
        "id": provider_id,
        "name": name,
        "type": p_type,
        "enabled": enabled,
        "base_url": base_url or None,
        "google_cx": google_cx,
        "key_hint": key_hint,
        "timeout_ms": timeout_ms,
        "max_results": max_results,
    }


# ---------------------------------------------------------------------------
# Normalization of provider payloads
# ---------------------------------------------------------------------------

def _item(row: Any) -> dict[str, str] | None:
    if not isinstance(row, Mapping):
        return None
    url = str(row.get("url", "") or row.get("link", "") or "").strip()
    if not url:
        return None
    title = str(row.get("title", "") or "").strip() or url
    content = (
        row.get("content")
        if row.get("content") is not None
        else row.get("snippet")
        if row.get("snippet") is not None
        else row.get("description")
        if row.get("description") is not None
        else row.get("text")
        if row.get("text") is not None
        else ""
    )
    content = str(content).strip()[:CONTENT_MAX_CHARS]
    return {"title": title, "url": url, "content": content}


def _items(payload: Any, list_key: str, limit: int) -> list[dict[str, str]]:
    rows = payload.get(list_key) if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise SearchError(
            SearchErrorKind.PROTOCOL,
            f"search provider response missing '{list_key}' list",
        )
    hits = [hit for hit in (_item(row) for row in rows) if hit is not None]
    return hits[:limit]


def _client(config: Mapping[str, Any], transport: httpx.BaseTransport | None) -> httpx.Client:
    timeout_seconds = max(0.5, config.get("timeout_ms", DEFAULT_TIMEOUT_MS) / 1000.0)
    return httpx.Client(
        timeout=httpx.Timeout(timeout_seconds),
        transport=transport,
        follow_redirects=True,
    )


def _effective_base(config: Mapping[str, Any]) -> str:
    base = config.get("base_url") or DEFAULT_BASE_URLS.get(str(config["type"]))
    if not base:
        raise SearchError(
            SearchErrorKind.MISSING_CONFIG,
            "this provider needs a base URL",
        )
    return str(base).rstrip("/")


def _request_json(
    config: Mapping[str, Any],
    transport: httpx.BaseTransport | None,
    request: httpx.Request,
) -> tuple[Any, int]:
    """Send one request; map transport/status errors onto the taxonomy."""
    try:
        with _client(config, transport) as client:
            response = client.send(request)
    except httpx.HTTPError as error:
        raise SearchError(
            SearchErrorKind.UNREACHABLE,
            f"search request failed: {error}",
        ) from error
    if response.status_code in (401, 403):
        # searxng signals "JSON format disabled" with a 403 HTML page —
        # keyless searxng has no real auth, so a non-JSON 403 body is the
        # json-disabled case, not an auth failure.
        text = response.text
        looks_json = (
            "json" in response.headers.get("content-type", "")
            or text.lstrip().startswith(("{", "["))
        )
        if config["type"] == "searxng" and not looks_json:
            raise SearchError(
                SearchErrorKind.JSON_DISABLED,
                "SearXNG returned HTML — enable the `json` format on the instance"
                " (settings.yml: search.formats: [json])",
                http_status=response.status_code,
            )
        raise SearchError(
            SearchErrorKind.AUTH,
            f"search provider rejected the request ({response.status_code})",
            http_status=response.status_code,
        )
    if response.status_code == 429:
        raise SearchError(
            SearchErrorKind.RATE_LIMIT,
            "search provider rate limit hit (429)",
            http_status=response.status_code,
        )
    if response.status_code != 200:
        raise SearchError(
            SearchErrorKind.PROTOCOL,
            f"search provider returned {response.status_code}",
            http_status=response.status_code,
        )
    content_type = response.headers.get("content-type", "")
    text = response.text
    if "json" not in content_type and not text.lstrip().startswith(("{", "[")):
        # searxng returns HTML when the JSON format is disabled on the
        # instance — give the actionable message instead of a JSON error.
        raise SearchError(
            SearchErrorKind.JSON_DISABLED,
            "provider returned non-JSON output"
            + (" (enable the `json` format on the SearXNG instance)" if config["type"] == "searxng" else ""),
            http_status=response.status_code,
        )
    try:
        return json.loads(text), response.status_code
    except ValueError as error:
        raise SearchError(
            SearchErrorKind.PROTOCOL,
            "search provider returned non-JSON output",
        ) from error


def _require_key(config: Mapping[str, Any], api_key: str) -> str:
    if not api_key:
        label = str(config.get("name") or config["type"])
        raise SearchError(SearchErrorKind.MISSING_KEY, f"{label} needs an API key.")
    return api_key


# ---------------------------------------------------------------------------
# Adapters (wire shapes mirror the desktop reference implementation)
# ---------------------------------------------------------------------------

def _fetch_searxng(config: Mapping[str, Any], query: str, api_key: str,
                   limit: int, transport: httpx.BaseTransport | None) -> list[dict[str, str]]:
    base = _effective_base(config)
    request = httpx.Request(
        "GET",
        f"{base}/search",
        params={"q": query, "format": "json"},
        headers={"Accept": "application/json"},
    )
    payload, _ = _request_json(config, transport, request)
    hits = _items(payload, "results", limit)
    if not hits and isinstance(payload, Mapping) and isinstance(payload.get("error"), str):
        raise SearchError(SearchErrorKind.PROTOCOL, str(payload["error"])[:200])
    return hits


def _fetch_tavily(config: Mapping[str, Any], query: str, api_key: str,
                  limit: int, transport: httpx.BaseTransport | None) -> list[dict[str, str]]:
    key = _require_key(config, api_key)
    base = _effective_base(config)
    body: dict[str, Any] = {"query": query, "max_results": limit, "api_key": key}
    request = httpx.Request(
        "POST",
        f"{base}/search",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {key}",
        },
        content=json.dumps(body),
    )
    payload, _ = _request_json(config, transport, request)
    return _items(payload, "results", limit)


def _fetch_brave(config: Mapping[str, Any], query: str, api_key: str,
                 limit: int, transport: httpx.BaseTransport | None) -> list[dict[str, str]]:
    key = _require_key(config, api_key)
    base = _effective_base(config)
    request = httpx.Request(
        "GET",
        f"{base}/web/search",
        params={"q": query, "count": str(limit)},
        headers={"Accept": "application/json", "X-Subscription-Token": key},
    )
    payload, _ = _request_json(config, transport, request)
    web = payload.get("web") if isinstance(payload, Mapping) else {}
    return _items(web if isinstance(web, Mapping) else {}, "results", limit)


def _fetch_exa(config: Mapping[str, Any], query: str, api_key: str,
               limit: int, transport: httpx.BaseTransport | None) -> list[dict[str, str]]:
    key = _require_key(config, api_key)
    base = _effective_base(config)
    body = {"query": query, "numResults": limit,
            "contents": {"text": {"maxCharacters": 400}}}
    request = httpx.Request(
        "POST",
        f"{base}/search",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "x-api-key": key},
        content=json.dumps(body),
    )
    payload, _ = _request_json(config, transport, request)
    return _items(payload, "results", limit)


def _fetch_serper(config: Mapping[str, Any], query: str, api_key: str,
                  limit: int, transport: httpx.BaseTransport | None) -> list[dict[str, str]]:
    key = _require_key(config, api_key)
    base = _effective_base(config)
    request = httpx.Request(
        "POST",
        f"{base}/search",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "X-API-KEY": key},
        content=json.dumps({"q": query, "num": limit}),
    )
    payload, _ = _request_json(config, transport, request)
    return _items(payload, "organic", limit)


def _fetch_google_pse(config: Mapping[str, Any], query: str, api_key: str,
                      limit: int, transport: httpx.BaseTransport | None) -> list[dict[str, str]]:
    key = _require_key(config, api_key)
    google_cx = str(config.get("google_cx", "") or "").strip()
    if not google_cx:
        raise SearchError(
            SearchErrorKind.MISSING_CONFIG,
            "Google Programmable Search needs an engine id (cx).",
        )
    base = _effective_base(config)
    request = httpx.Request(
        "GET",
        f"{base}",
        params={"key": key, "cx": google_cx, "q": query, "num": str(min(limit, 10))},
        headers={"Accept": "application/json"},
    )
    payload, _ = _request_json(config, transport, request)
    return _items(payload, "items", limit)


_FETCHERS = {
    "searxng": _fetch_searxng,
    "tavily": _fetch_tavily,
    "brave": _fetch_brave,
    "exa": _fetch_exa,
    "serper": _fetch_serper,
    "google-pse": _fetch_google_pse,
}


def perform_search(
    config: Mapping[str, Any],
    query: str,
    *,
    api_key: str = "",
    transport: httpx.BaseTransport | None = None,
    limit: int | None = None,
) -> list[dict[str, str]]:
    """Run one search against one provider; returns normalized hits."""
    normalized = normalize_provider_config(config)
    query = str(query).strip()
    if not query:
        raise SearchError(SearchErrorKind.BAD_REQUEST, "empty search query")
    effective_limit = limit if limit is not None else normalized["max_results"]
    fetcher = _FETCHERS.get(normalized["type"])
    if fetcher is None:  # pragma: no cover — normalize already guards this
        raise SearchError(
            SearchErrorKind.UNKNOWN_TYPE,
            f"unknown search provider type '{normalized['type']}'",
        )
    return fetcher(normalized, query, api_key, effective_limit, transport)


def probe_provider(
    config: Mapping[str, Any],
    *,
    api_key: str = "",
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """One benign search; report status for the UI's connection test row.

    Statuses: ok | unreachable | auth | rate_limit | json_disabled | error.
    """
    started = time.monotonic()
    try:
        hits = perform_search(config, "neuronection", api_key=api_key, transport=transport)
        return {
            "status": "ok",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "result_count": len(hits),
            "error": None,
        }
    except SearchError as error:
        kind = error.kind
        if kind == "unreachable":
            status = "unreachable"
        elif kind == "auth":
            status = "auth"
        elif kind == "rate_limit":
            status = "rate_limit"
        elif kind == "json_disabled":
            status = "json_disabled"
        else:
            status = "error"
        return {
            "status": status,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "result_count": None,
            "error": error.message,
        }


def provider_catalog_summary() -> dict[str, Any]:
    """Minimal catalog data for callers without the JSON catalog at hand."""
    return {
        "types": list(PROVIDER_TYPES),
        "base_url_required": list(BASE_URL_REQUIRED),
        "defaults": dict(DEFAULT_BASE_URLS),
    }
