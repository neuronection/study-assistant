"""External web sources: declarative, deterministic, LLM-free scans (73-E).

A source (RSS feed, YouTube channel/playlist, site-filtered search) is
polled on a schedule and every new item lands as a *suggestion* — never a
material, never an auto-import (ADR-167/170). Feed and yt-dlp metadata is
untrusted input: title/snippet are stripped to plain text, URLs are
re-validated http(s) before upsert (family-security).
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

from ...core.secrets import get_secret
from ...core.urls import normalize_url
from ...core.vocab import DiscoveryKind, ExternalSourceKind
from ...domain.models import ExternalSource, utcnow
from ...search.provider import SEARCH_KEYRING_REF, search_provider_config
from ..content.discovery import record_scan_suggestion

MIN_SCAN_INTERVAL_SEC = 900
DEFAULT_SCAN_INTERVAL_SEC = 6 * 3600
RSS_TIMEOUT_SEC = 30.0
YTDLP_SOCKET_TIMEOUT_SEC = 120
DEFAULT_MAX_ITEMS = 20
MAX_SEEN_IDS = 1000
SNIPPET_LIMIT = 2000


class ExternalSourcesError(ValueError):
    pass


def effective_interval(source: ExternalSource) -> int:
    return max(source.scan_interval_sec or DEFAULT_SCAN_INTERVAL_SEC, MIN_SCAN_INTERVAL_SEC)


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
        raise ExternalSourcesError("expecting an http(s) URL")
    if kind in (
        ExternalSourceKind.YOUTUBE_CHANNEL.value,
        ExternalSourceKind.YOUTUBE_PLAYLIST.value,
    ):
        host = parsed.netloc.lower().split(":")[0]
        if not (host == "youtu.be" or host.endswith("youtube.com")):
            raise ExternalSourcesError("YouTube sources expect a youtube.com URL")
    return text[:2048]


def _validated_options(
    kind: str, options: dict[str, Any] | None
) -> dict[str, Any]:
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ExternalSourcesError("options must be an object")
    cleaned: dict[str, Any] = {}
    max_items = options.get("max_items")
    if max_items is not None:
        if not isinstance(max_items, int) or not 1 <= max_items <= 100:
            raise ExternalSourcesError("max_items must be 1-100")
        cleaned["max_items"] = max_items
    if kind == ExternalSourceKind.SITE_SEARCH.value:
        query = str(options.get("query", "")).strip()
        if not query:
            raise ExternalSourcesError("site_search sources need a query option")
        cleaned["query"] = query[:300]
        site = str(options.get("site", "")).strip()
        if site:
            cleaned["site"] = site[:200]
    return cleaned


def validate_source(
    kind: str, url: str, options: dict[str, Any] | None
) -> tuple[str, str, dict[str, Any]]:
    kind_value = ExternalSourceKind.parse(kind)
    clean_url = _validated_source_url(kind_value.value, url)
    clean_options = _validated_options(kind_value.value, options)
    if kind_value is ExternalSourceKind.SITE_SEARCH and "site" not in clean_options:
        parsed = urlparse(clean_url)
        clean_options["site"] = parsed.netloc.lower().split(":")[0][:200]
    return kind_value.value, clean_url, clean_options


def fetch_url(
    url: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.get(
        url, timeout=RSS_TIMEOUT_SEC, follow_redirects=True, headers=headers
    )


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


def _scan_rss(session: Session, source: ExternalSource) -> dict[str, int]:
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
        raise ExternalSourcesError(
            f"feed returned {response.status_code}"
        )
    feed = parse_feed(response.content)
    entries = [
        entry for entry in getattr(feed, "entries", []) or []
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
        outcome = record_scan_suggestion(
            session,
            source.profile_id,
            provider=f"rss:{source.label or 'feed'}",
            url=url,
            title=_strip_html(str(entry.get("title") or url)),
            snippet=_strip_html(str(entry.get("summary") or ""))[:SNIPPET_LIMIT],
            kind=_entry_kind(entry),
            meta={"published": _entry_published(entry)},
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


def _scan_youtube(session: Session, source: ExternalSource) -> dict[str, int]:
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
        meta: dict[str, Any] = {}
        duration = entry.get("duration")
        if isinstance(duration, (int, float)) and duration > 0:
            minutes, seconds = divmod(int(duration), 60)
            meta["duration"] = f"{minutes:02d}:{seconds:02d}"
        channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
        if channel:
            meta["channel"] = channel
        outcome = record_scan_suggestion(
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


def _perform_site_search(
    base_url: str, flavor: str, query: str, api_key: str
) -> list[dict[str, str]]:
    from ...search.provider import perform_search

    return perform_search(base_url, flavor, query, api_key=api_key)


def _scan_site_search(session: Session, source: ExternalSource) -> dict[str, int]:
    options = source.options if isinstance(source.options, dict) else {}
    config = search_provider_config(session, source.profile_id)
    if config is None:
        raise ExternalSourcesError(
            "no search provider configured — connect one in Settings"
        )
    api_key = get_secret(SEARCH_KEYRING_REF) or ""
    site = str(options.get("site") or "").strip()
    query = f"{options.get('query', '')}".strip()
    if site:
        query = f"{query} site:{site}"
    stats = {"new": 0, "updated": 0}
    provider = f"site:{site}" if site else "site-search"
    for hit in _perform_site_search(config["base_url"], config["flavor"], query, api_key):
        outcome = record_scan_suggestion(
            session,
            source.profile_id,
            provider=provider,
            url=hit.get("url", ""),
            title=_strip_html(hit.get("title", "")),
            snippet=_strip_html(hit.get("content", ""))[:SNIPPET_LIMIT],
            kind=DiscoveryKind.ARTICLE.value,
            meta={"site": site} if site else None,
            course_id=source.course_id,
        )
        if outcome == "created":
            stats["new"] += 1
        elif outcome == "updated":
            stats["updated"] += 1
    return stats


def run_scan(session: Session, source: ExternalSource) -> dict[str, int]:
    if not source.enabled:
        raise ExternalSourcesError("source is disabled")
    normalized = normalize_url(source.url)
    if not normalized.startswith(("http://", "https://")):
        raise ExternalSourcesError("expecting an http(s) URL")
    kind = ExternalSourceKind.parse(source.kind)
    if kind is ExternalSourceKind.RSS:
        stats = _scan_rss(session, source)
    elif kind in (
        ExternalSourceKind.YOUTUBE_CHANNEL,
        ExternalSourceKind.YOUTUBE_PLAYLIST,
    ):
        stats = _scan_youtube(session, source)
    else:
        stats = _scan_site_search(session, source)
    source.last_scan_error = None
    source.last_scanned_at = utcnow()
    return stats


def next_due_at(source: ExternalSource) -> datetime:
    base = source.last_scanned_at or datetime.min.replace(tzinfo=None)
    return base + td(seconds=effective_interval(source))
