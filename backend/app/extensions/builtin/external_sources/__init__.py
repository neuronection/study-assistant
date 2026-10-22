"""Bundled ``external-sources`` connector (plan 73-E, ADR-167/170).

A source (RSS feed, YouTube channel/playlist, site-filtered search) is
polled on a schedule and every new item lands as a *suggestion* — never a
material, never an auto-import. Feed and yt-dlp metadata is untrusted
input: title/snippet are stripped to plain text, URLs are re-validated
http(s) before upsert (family-security). Declared capabilities (D3):
``sync`` only — the fetch URLs are user-configured, so there is no fixed
domain list for an honest ``net`` grant (the fetch-leg honesty lives in
the manifest description and the charter's connector profile). Sync
orchestration (the scheduler, cadence policy) stays in ``services/`` —
D24 rule 4; the host adapter that feeds the suggestion funnel is
:mod:`app.services.content.external_sources`.

Errors follow the charter typed model (D4/D18) via
:class:`app.extensions.errors.ExtensionError`.
"""

import calendar
import contextlib
from datetime import UTC, datetime
from datetime import timedelta as td
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from ....core.urls import normalize_url
from ....core.vocab import DiscoveryKind, ExternalSourceKind
from ....domain.models import ExternalSource, utcnow
from ...errors import ExtensionError
from ...registry import extension_registry
from ...search.provider import search_with_fallback
from . import providers as provider_catalog
from .adapters.base import MEDIA_EXTENSIONS, MEDIA_MIME_ALLOWLIST
from .engine import fetch_entry, reconcile

MIN_SCAN_INTERVAL_SEC = 900
DEFAULT_SCAN_INTERVAL_SEC = 6 * 3600
RSS_TIMEOUT_SEC = 30.0
YTDLP_SOCKET_TIMEOUT_SEC = 120
DEFAULT_MAX_ITEMS = 20
MAX_SEEN_IDS = 1000
SNIPPET_LIMIT = 2000
MEDIA_SIZE_CAP = 200 * 1024 * 1024

CORE_PROVIDERS = {"rss", "youtube", "site-search"}
MEDIA_PROVIDER_FIELDS = frozenset(
    {"max_items", "query", "site", "username", "folder_id", "folder_path", "collection", "decks"}
)

RecordFn = Any


def effective_interval(source: ExternalSource) -> int:
    return max(source.scan_interval_sec or DEFAULT_SCAN_INTERVAL_SEC, MIN_SCAN_INTERVAL_SEC)


def next_due_at(source: ExternalSource) -> datetime:
    base = source.last_scanned_at or datetime.min.replace(tzinfo=None)
    return base + td(seconds=effective_interval(source))


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""

    class _Text(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag in ("script", "style"):
                self.skip += 1

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style") and self.skip > 0:
                self.skip -= 1

        def handle_data(self, data: str) -> None:
            if self.skip == 0:
                self.parts.append(data)

    parser = _Text()
    with contextlib.suppress(Exception):
        parser.feed(raw)
        parser.close()
    return " ".join(" ".join(parser.parts).split())


def _validated_source_url(kind: str, url: str) -> str:
    text = (url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ExtensionError("invalid", "expecting an http(s) URL")
    if kind in (
        ExternalSourceKind.YOUTUBE_CHANNEL.value,
        ExternalSourceKind.YOUTUBE_PLAYLIST.value,
    ):
        host = parsed.netloc.lower().split(":")[0]
        if not (host == "youtu.be" or host.endswith("youtube.com")):
            raise ExtensionError("invalid", "YouTube sources expect a youtube.com URL")
    return text[:2048]


def _validated_options(
    kind: str, options: dict[str, Any] | None, provider: str | None = None
) -> dict[str, Any]:
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ExtensionError("invalid", "options must be an object")
    cleaned: dict[str, Any] = {}
    max_items = options.get("max_items")
    if max_items is not None:
        if not isinstance(max_items, int) or not 1 <= max_items <= 100:
            raise ExtensionError("invalid", "max_items must be 1-100")
        cleaned["max_items"] = max_items
    provider_row = provider_catalog.get_provider(provider) if provider else None
    allowed = set(provider_row.fields) if provider_row is not None else set()
    if kind == ExternalSourceKind.SITE_SEARCH.value:
        query = str(options.get("query", "")).strip()
        if not query:
            raise ExtensionError("invalid", "site_search sources need a query option")
        cleaned["query"] = query[:300]
        site = str(options.get("site", "")).strip()
        if site:
            cleaned["site"] = site[:200]
        return cleaned
    if provider_row is None:
        return cleaned
    for field in ("username", "folder_id", "folder_path", "collection"):
        if field not in allowed:
            continue
        value = str(options.get(field, "")).strip()
        if value:
            cleaned[field] = value[:300]
    if "decks" in allowed:
        raw = options.get("decks")
        if isinstance(raw, str):
            decks = [part.strip() for part in raw.split(",") if part.strip()]
        elif isinstance(raw, list):
            decks = [str(part).strip() for part in raw if str(part).strip()]
        else:
            decks = []
        if decks:
            cleaned["decks"] = decks[:20]
    return cleaned


def resolve_provider(kind: str, provider: str | None) -> str:
    if provider is None or provider == "":
        return provider_catalog.provider_for_kind(kind)
    try:
        provider_catalog.validate_registration(provider, kind)
    except ExtensionError:
        raise
    return provider


def validate_source(
    kind: str,
    url: str,
    options: dict[str, Any] | None,
    provider: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    try:
        kind_value = ExternalSourceKind.parse(kind)
    except ValueError as error:
        raise ExtensionError("invalid", str(error)) from error
    provider_id = resolve_provider(kind_value.value, provider)
    provider_row = provider_catalog.validate_registration(provider_id, kind_value.value)
    clean_url = ""
    if provider_row.url_required:
        clean_url = _validated_source_url(kind_value.value, url)
    else:
        raw_url = (url or "").strip()
        if raw_url:
            clean_url = _validated_source_url(kind_value.value, raw_url)
    clean_options = _validated_options(kind_value.value, options, provider_id)
    if kind_value is ExternalSourceKind.SITE_SEARCH and "site" not in clean_options:
        parsed = urlparse(clean_url)
        clean_options["site"] = parsed.netloc.lower().split(":")[0][:200]
    return kind_value.value, clean_url, clean_options


def _media_meta(entry: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    for enclosure in entry.get("enclosures") or []:
        if not isinstance(enclosure, dict):
            continue
        url = str(enclosure.get("href") or enclosure.get("url") or "").strip()
        mime = str(enclosure.get("type") or "").split(";")[0].strip().lower()
        if not url.startswith(("http://", "https://")):
            continue
        extension = "." + url.rsplit(".", 1)[-1].lower() if "." in url.rsplit("/", 1)[-1] else ""
        if mime not in MEDIA_MIME_ALLOWLIST and extension not in MEDIA_EXTENSIONS:
            continue
        length_raw = enclosure.get("length")
        size = (
            int(length_raw)
            if isinstance(length_raw, (int, str)) and str(length_raw).isdigit()
            else None
        )
        if size is not None and size > MEDIA_SIZE_CAP:
            return {"enclosure_type": mime or None, "enclosure_oversize": True}, None
        material_kind = (
            "audio"
            if mime.startswith("audio")
            or extension
            in {
                ".mp3",
                ".m4a",
                ".wav",
                ".ogg",
                ".opus",
                ".mpga",
            }
            else "video"
        )
        return (
            {
                "enclosure_url": url,
                "enclosure_type": mime or None,
                "size": size,
                "material_kind": material_kind,
            },
            material_kind,
        )
    return {}, None


def fetch_url(url: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.get(url, timeout=RSS_TIMEOUT_SEC, follow_redirects=True, headers=headers)


def parse_feed(data: bytes) -> Any:
    """Module-level seam: tests inject fake feeds; no network here."""
    import feedparser  # type: ignore[import-untyped]

    return feedparser.parse(data)


def extract_flat_entries(url: str) -> list[dict[str, Any]]:
    """Module-level seam: yt-dlp flat extract, no download (tests fake it)."""
    import yt_dlp  # type: ignore[import-untyped]

    with yt_dlp.YoutubeDL(
        {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "socket_timeout": YTDLP_SOCKET_TIMEOUT_SEC,
        }
    ) as ydl:
        info = dict(ydl.extract_info(url, download=False))
    entries = info.get("entries") if isinstance(info, dict) else None
    return [entry for entry in entries if isinstance(entry, dict)] if entries else []


def _entry_kind(entry: dict[str, Any]) -> str:
    enclosures = entry.get("enclosures") or []
    media_types = " ".join(
        str(enclosure.get("type", "")).lower()
        for enclosure in enclosures
        if isinstance(enclosure, dict)
    )
    if "video" in media_types:
        return DiscoveryKind.VIDEO.value
    if "course" in str(entry.get("category", "")).lower():
        return DiscoveryKind.COURSE.value
    tags = " ".join(
        str(term.get("term", "")).lower()
        for term in entry.get("tags") or []
        if isinstance(term, dict)
    )
    blob = f"{entry.get('category', '')} {tags}".lower()
    if "course" in blob or "lesson" in blob:
        return DiscoveryKind.COURSE.value
    if any(word in blob for word in ("exercise", "problem", "quiz", "practice")):
        return DiscoveryKind.EXERCISE.value
    if "audio" in media_types or "podcast" in blob:
        return DiscoveryKind.OTHER.value
    return DiscoveryKind.ARTICLE.value


def _entry_published(entry: dict[str, Any]) -> str | None:
    parsed = entry.get("published_parsed")
    if not parsed:
        return None
    with contextlib.suppress(Exception, ValueError):
        stamp = calendar.timegm(parsed)
        return datetime.fromtimestamp(stamp, tz=UTC).isoformat()
    return None


def _entry_id(entry: dict[str, Any]) -> str | None:
    value = entry.get("id") or entry.get("link")
    return str(value).strip() if value else None


def _cap_seen(seen: list[str]) -> list[str]:
    return seen[-MAX_SEEN_IDS:]


def _scan_rss(
    session: Session,
    source: ExternalSource,
    record: RecordFn,
) -> dict[str, int]:
    options = source.options if isinstance(source.options, dict) else {}
    max_items = int(options.get("max_items") or DEFAULT_MAX_ITEMS)
    cursor = source.cursor if isinstance(source.cursor, dict) else {}
    headers: dict[str, str] = {}
    if cursor.get("etag"):
        headers["If-None-Match"] = str(cursor["etag"])
    if cursor.get("last_modified"):
        headers["If-Modified-Since"] = str(cursor["last_modified"])
    response = fetch_url(source.url, headers or None)
    if response.status_code == 304:
        return {"new": 0, "updated": 0}
    if response.status_code != 200:
        code = "provider" if response.status_code >= 500 else "protocol"
        raise ExtensionError(
            code, f"feed returned {response.status_code}", status=response.status_code
        )
    feed = parse_feed(response.content)
    entries = [
        entry
        for entry in getattr(feed, "entries", []) or []
        if isinstance(entry, dict) or hasattr(entry, "get")
    ]
    seen = [str(item) for item in cursor.get("seen", []) if item]
    seen_set = set(seen)
    stats = {"new": 0, "updated": 0}
    fresh_ids: list[str] = []
    for entry in entries[: max_items * 3]:
        entry_id = _entry_id(entry)
        if entry_id:
            fresh_ids.append(entry_id)
        url = str(entry.get("link") or "").strip()
        if not url:
            continue
        if entry_id and entry_id in seen_set:
            continue
        entry_meta, _media_kind = _media_meta(entry)
        meta: dict[str, Any] = {"published": _entry_published(entry), "source_id": source.id}
        meta.update(entry_meta)
        outcome = record(
            session,
            source.profile_id,
            provider=f"rss:{source.label or 'feed'}",
            url=url,
            title=_strip_html(str(entry.get("title") or url)),
            snippet=_strip_html(str(entry.get("summary") or ""))[:SNIPPET_LIMIT],
            kind=_entry_kind(entry),
            meta=meta,
            course_id=source.course_id,
        )
        if outcome == "created":
            stats["new"] += 1
        elif outcome == "updated":
            stats["updated"] += 1
    stats["new"] = min(stats["new"], max_items)
    new_cursor: dict[str, Any] = {}
    if getattr(response.headers, "get", None):
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        if etag:
            new_cursor["etag"] = etag
        if last_modified:
            new_cursor["last_modified"] = last_modified
    merged = seen + [entry_id for entry_id in fresh_ids if entry_id not in seen_set]
    new_cursor["seen"] = _cap_seen(merged)
    source.cursor = new_cursor
    return stats


def _scan_youtube(
    session: Session,
    source: ExternalSource,
    record: RecordFn,
) -> dict[str, int]:
    options = source.options if isinstance(source.options, dict) else {}
    max_items = int(options.get("max_items") or DEFAULT_MAX_ITEMS)
    cursor = source.cursor if isinstance(source.cursor, dict) else {}
    seen = [str(item) for item in cursor.get("seen", []) if item]
    seen_set = set(seen)
    stats = {"new": 0, "updated": 0}
    fresh_ids: list[str] = []
    provider = f"youtube:{source.label or source.kind}"
    for entry in extract_flat_entries(source.url):
        if stats["new"] >= max_items:
            break
        video_id = str(entry.get("id") or "").strip()
        url = str(entry.get("url") or "").strip()
        if video_id and not url:
            url = f"https://www.youtube.com/watch?v={video_id}"
        if not url:
            continue
        if video_id and video_id in seen_set:
            continue
        if video_id:
            fresh_ids.append(video_id)
        meta: dict[str, Any] = {"source_id": source.id}
        duration = entry.get("duration")
        if isinstance(duration, (int, float)) and duration > 0:
            minutes, seconds = divmod(int(duration), 60)
            meta["duration"] = f"{minutes:02d}:{seconds:02d}"
        channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
        if channel:
            meta["channel"] = channel
        outcome = record(
            session,
            source.profile_id,
            provider=provider,
            url=url,
            title=_strip_html(str(entry.get("title") or url)),
            snippet=None,
            kind=DiscoveryKind.VIDEO.value,
            meta=meta,
            course_id=source.course_id,
        )
        if outcome == "created":
            stats["new"] += 1
        elif outcome == "updated":
            stats["updated"] += 1
    source.cursor = {"seen": _cap_seen(seen + [item for item in fresh_ids if item not in seen_set])}
    return stats


def _scan_site_search(
    session: Session,
    source: ExternalSource,
    record: RecordFn,
) -> dict[str, int]:
    options = source.options if isinstance(source.options, dict) else {}
    site = str(options.get("site") or "").strip()
    query = f"{options.get('query', '')}".strip()
    if site:
        query = f"{query} site:{site}"
    try:
        hits = search_with_fallback(session, source.profile_id, query)
    except httpx.HTTPError as error:
        raise ExtensionError("unreachable", f"search provider failed: {error}") from error
    if hits is None:
        raise ExtensionError(
            "not-ready",
            "no search provider configured — connect one in Settings → Tools → Web search",
        )
    stats = {"new": 0, "updated": 0}
    provider = f"site:{site}" if site else "site-search"
    for hit in hits:
        outcome = record(
            session,
            source.profile_id,
            provider=provider,
            url=hit.get("url", ""),
            title=_strip_html(hit.get("title", "")),
            snippet=_strip_html(hit.get("content", ""))[:SNIPPET_LIMIT],
            kind=DiscoveryKind.ARTICLE.value,
            meta={"site": site, "source_id": source.id} if site else {"source_id": source.id},
            course_id=source.course_id,
        )
        if outcome == "created":
            stats["new"] += 1
        elif outcome == "updated":
            stats["updated"] += 1
    return stats


def run_scan(
    session: Session,
    source: ExternalSource,
    record: RecordFn,
) -> dict[str, int]:
    """One scan leg of the bundled external-sources connector.

    ``record`` is the HOST's suggestion funnel — injected, never imported
    (the dependency direction is host → extensions). Enable state, URL
    normalization and the declared-capability gate are checked here;
    cadence and scheduling stay host policy (D24 rule 4). Catalog-known
    providers outside the core trio reconcile through the shared engine.
    """
    if not extension_registry.has_capability("external-sources", "sync"):
        raise ExtensionError("not-ready", "the external-sources bundle does not declare 'sync'")
    if not source.enabled:
        raise ExtensionError("not-ready", "source is disabled")
    provider_id = source.provider or provider_catalog.provider_for_kind(source.kind)
    provider_catalog.validate_registration(provider_id, source.kind, source.auth_kind)
    if provider_id not in CORE_PROVIDERS:
        return reconcile(session, source, record)
    normalized = normalize_url(source.url)
    if not normalized.startswith(("http://", "https://")):
        raise ExtensionError("invalid", "expecting an http(s) URL")
    kind = ExternalSourceKind.parse(source.kind)
    if kind is ExternalSourceKind.RSS:
        stats = _scan_rss(session, source, record)
    elif kind in (
        ExternalSourceKind.YOUTUBE_CHANNEL,
        ExternalSourceKind.YOUTUBE_PLAYLIST,
    ):
        stats = _scan_youtube(session, source, record)
    else:
        stats = _scan_site_search(session, source, record)
    source.last_scan_error = None
    source.last_scanned_at = utcnow()
    source.consecutive_failures = 0
    return stats


def provider_entry(source: ExternalSource, meta: dict[str, Any], url: str, title: str) -> Any:
    from .adapters.base import RemoteEntry

    return RemoteEntry(
        remote_id=str(meta.get("remote_id") or url),
        name=str(meta.get("remote_name") or title),
        url=str(meta.get("enclosure_url") or meta.get("attachment_url") or url),
        mime=str(meta.get("mime") or meta.get("enclosure_type") or "") or None,
        size=meta.get("size") if isinstance(meta.get("size"), int) else None,
        kind=str(meta.get("discovery_kind") or "") or None,
        meta=meta,
    )


__all__ = [
    "DEFAULT_MAX_ITEMS",
    "DEFAULT_SCAN_INTERVAL_SEC",
    "MIN_SCAN_INTERVAL_SEC",
    "effective_interval",
    "fetch_entry",
    "next_due_at",
    "provider_entry",
    "reconcile",
    "run_scan",
    "validate_source",
]
