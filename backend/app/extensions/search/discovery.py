"""Discovery provider registry: normalized results over pluggable sources.

Providers return `DiscoveryResult` rows; results are never persisted (same
posture as the chat SEARCH tool). No first-party integration with
ToS-restricted platforms — site-filtered presets are data, not scrapers
(ADR-166/170). MCP connector providers (73-G) invoke user-registered
external servers deterministically and validate every row app-side.
"""

import json
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx
import structlog
from sqlalchemy.orm import Session

from ...ai.mcp_client import (
    McpToolError,
    audit_mcp_invocation,
    call_tool_sync,
)
from ...core.secrets import get_secret
from ...core.vocab import CitationKind, DiscoveryKind
from ...domain.models import Profile
from .polite_fetch import fetch_document
from .provider import list_search_providers, provider_key_ref, search_with_fallback_configs

logger = structlog.get_logger(__name__)

DEFAULT_ENABLED = ("web", "youtube", "arxiv", "openalex")
KHAN_ACADEMY_SITE = "khanacademy.org"
DEFAULT_SITE_PRESETS: tuple[dict[str, str], ...] = (
    {"site": KHAN_ACADEMY_SITE, "label": "Khan Academy", "kind": DiscoveryKind.COURSE.value},
    {
        "site": "en.wikipedia.org",
        "label": "Wikipedia",
        "kind": DiscoveryKind.REFERENCE.value,
    },
    {"site": "ocw.mit.edu", "label": "MIT OpenCourseWare", "kind": DiscoveryKind.COURSE.value},
    {"site": "openstax.org", "label": "OpenStax", "kind": DiscoveryKind.REFERENCE.value},
)
SCHOLARLY_PROVIDER_IDS = ("arxiv", "openalex", "crossref")

ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"
CROSSREF_ENDPOINT = "https://api.crossref.org/works"
SCHOLARLY_MAILTO = "study-assistant@neuronection.com"

Resolver = Callable[[str], list[str]]


class DiscoveryError(ValueError):
    pass


@dataclass
class DiscoveryResult:
    provider: str
    title: str
    url: str
    kind: str = DiscoveryKind.ARTICLE.value
    description: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class DiscoveryProvider:
    id: str
    label: str

    def search(
        self,
        query: str,
        *,
        cap: int,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> list[DiscoveryResult]:  # pragma: no cover - interface
        raise NotImplementedError

    def configured(self, session: Session) -> bool:  # pragma: no cover
        return True


def _duration_text(seconds: object) -> str | None:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return None
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class WebSearchProvider(DiscoveryProvider):
    id = "web"
    label = "Web"

    def __init__(
        self,
        providers: list[dict[str, object]],
        keys: dict[str, str],
        cap_limit: int = 8,
    ) -> None:
        self._providers = providers
        self._keys = keys
        self._cap_limit = cap_limit

    def search(
        self,
        query: str,
        *,
        cap: int,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> list[DiscoveryResult]:
        hits = search_with_fallback_configs(
            self._providers,
            self._keys,
            query,
            transport=transport,
            limit=min(cap, self._cap_limit),
        )
        if not hits:
            return []
        return [
            DiscoveryResult(
                provider=self.id,
                title=hit["title"],
                url=hit["url"],
                kind=DiscoveryKind.ARTICLE.value,
                description=hit.get("content", ""),
            )
            for hit in hits
        ]


class SiteSearchProvider(DiscoveryProvider):
    def __init__(
        self,
        site: str,
        providers: list[dict[str, object]],
        keys: dict[str, str],
        label: str | None = None,
        default_kind: str = DiscoveryKind.COURSE.value,
        cap_limit: int = 8,
    ) -> None:
        self.site = site
        self._providers = providers
        self._keys = keys
        self.id = f"site:{site}"
        self.label = label or site
        self._default_kind = default_kind
        self._cap_limit = cap_limit

    def search(
        self,
        query: str,
        *,
        cap: int,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> list[DiscoveryResult]:
        hits = search_with_fallback_configs(
            self._providers,
            self._keys,
            f"{query} site:{self.site}",
            transport=transport,
            limit=min(cap, self._cap_limit),
        )
        if not hits:
            return []
        return [
            DiscoveryResult(
                provider=self.id,
                title=hit["title"],
                url=hit["url"],
                kind=self._default_kind,
                description=hit.get("content", ""),
                meta={"site": self.site},
            )
            for hit in hits
        ]


def search_videos(query: str, cap: int) -> list[dict[str, Any]]:
    """yt-dlp flat search — module-level so tests inject fakes."""
    import yt_dlp  # type: ignore[import-untyped]

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
        info = dict(ydl.extract_info(f"ytsearch{cap}:{query}", download=False))
    entries = info.get("entries") if isinstance(info, dict) else None
    return [entry for entry in entries if isinstance(entry, dict)] if entries else []


class YouTubeSearchProvider(DiscoveryProvider):
    id = "youtube"
    label = "YouTube"

    def search(
        self,
        query: str,
        *,
        cap: int,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> list[DiscoveryResult]:
        rows = search_videos(query, cap)
        results: list[DiscoveryResult] = []
        for row in rows[:cap]:
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            meta: dict[str, Any] = {}
            duration = _duration_text(row.get("duration"))
            if duration:
                meta["duration"] = duration
            channel = str(row.get("channel") or row.get("uploader") or "").strip()
            if channel:
                meta["channel"] = channel
            results.append(
                DiscoveryResult(
                    provider=self.id,
                    title=str(row.get("title") or "").strip() or url,
                    url=url,
                    kind=DiscoveryKind.VIDEO.value,
                    description="",
                    meta=meta,
                )
            )
        return results


def _fetch_text(
    url: str, *, transport: httpx.BaseTransport | None, resolver: Resolver | None
) -> str:
    result = fetch_document(url, transport=transport, resolver=resolver)
    if result.status != 200:
        raise DiscoveryError(f"scholarly endpoint returned HTTP {result.status}")
    raw = result.text
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return str(raw)


def _first(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value or "").strip()


def _doi_value(value: Any) -> str:
    text = str(value or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            return text[len(prefix) :]
    return text


def _doi_url(doi: str) -> str:
    return f"https://doi.org/{quote(doi, safe='/')}" if doi else ""


def _year_value(value: Any) -> int | None:
    text = str(value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    if isinstance(value, int) and 1000 <= value <= 3000:
        return value
    return None


def _citation_kind(raw: str) -> str:
    value = raw.strip().lower()
    if value == "dataset":
        return CitationKind.DATASET.value
    if value == "preprint":
        return CitationKind.PREPRINT.value
    if value in ("book", "book-chapter", "reference-entry", "reference", "edited-book"):
        return CitationKind.BOOK.value if value != "book-chapter" else CitationKind.CHAPTER.value
    if value in ("proceedings-article", "conference-paper"):
        return CitationKind.CONFERENCE.value
    if value == "dissertation":
        return CitationKind.THESIS.value
    if value in ("report", "standard"):
        return CitationKind.REPORT.value
    return CitationKind.ARTICLE.value


def _discovery_kind(citation_kind: str) -> str:
    if citation_kind == CitationKind.DATASET.value:
        return DiscoveryKind.DATASET.value
    if citation_kind in (
        CitationKind.BOOK.value,
        CitationKind.CHAPTER.value,
        CitationKind.REPORT.value,
    ):
        return DiscoveryKind.REFERENCE.value
    return DiscoveryKind.PAPER.value


def _citation_meta(
    *,
    doi: str,
    authors: list[str],
    year: int | None,
    container: str,
    citation_kind: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "doi": doi,
        "authors": [name for name in authors if name][:20],
        "container": container,
        "citation_kind": citation_kind,
    }
    if year is not None:
        meta["year"] = year
    if extra:
        meta.update(extra)
    return meta


class ArxivSearchProvider(DiscoveryProvider):
    id = "arxiv"
    label = "arXiv"

    def search(
        self,
        query: str,
        *,
        cap: int,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> list[DiscoveryResult]:
        url = f"{ARXIV_ENDPOINT}?search_query=all:{quote(query.strip())}&start=0&max_results={cap}"
        text = _fetch_text(url, transport=transport, resolver=resolver)
        return _parse_arxiv(text, self.id, cap)


ATOM_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _parse_arxiv(text: str, provider: str, cap: int) -> list[DiscoveryResult]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise DiscoveryError(f"arXiv returned malformed Atom ({error})") from error
    results: list[DiscoveryResult] = []
    for entry in root.findall("a:entry", ATOM_NS):
        title = " ".join((entry.findtext("a:title", default="", namespaces=ATOM_NS) or "").split())
        link = ""
        for node in entry.findall("a:link", ATOM_NS):
            if node.get("rel") == "alternate" and node.get("href"):
                link = str(node.get("href"))
        if not link:
            raw_id = entry.findtext("a:id", default="", namespaces=ATOM_NS) or ""
            link = raw_id.replace("http://arxiv.org/abs/", "https://arxiv.org/abs/")
        if not title or not link:
            continue
        summary = " ".join(
            (entry.findtext("a:summary", default="", namespaces=ATOM_NS) or "").split()
        )
        published = entry.findtext("a:published", default="", namespaces=ATOM_NS) or ""
        authors = [
            " ".join((node.text or "").split())
            for node in entry.findall("a:author/a:name", ATOM_NS)
        ]
        doi = _doi_value(entry.findtext("arxiv:doi", default="", namespaces=ATOM_NS))
        container = (
            entry.findtext("arxiv:journal_ref", default="", namespaces=ATOM_NS) or ""
        ).strip() or "arXiv"
        results.append(
            DiscoveryResult(
                provider=provider,
                title=title[:300],
                url=link[:2048],
                kind=DiscoveryKind.PAPER.value,
                description=summary[:800],
                meta=_citation_meta(
                    doi=doi,
                    authors=authors,
                    year=_year_value(published),
                    container=container,
                    citation_kind=CitationKind.PREPRINT.value,
                ),
            )
        )
        if len(results) >= cap:
            break
    return results


def _openalex_abstract(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, places in index.items():
        if not isinstance(places, list):
            continue
        for place in places:
            if isinstance(place, int):
                positions.append((place, str(word)))
    positions.sort()
    return " ".join(word for _position, word in positions)[:800]


class OpenAlexSearchProvider(DiscoveryProvider):
    id = "openalex"
    label = "OpenAlex"

    def search(
        self,
        query: str,
        *,
        cap: int,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> list[DiscoveryResult]:
        url = (
            f"{OPENALEX_ENDPOINT}?search={quote(query.strip())}"
            f"&per-page={cap}&mailto={quote(SCHOLARLY_MAILTO)}"
        )
        text = _fetch_text(url, transport=transport, resolver=resolver)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise DiscoveryError(f"OpenAlex returned non-JSON ({error})") from error
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise DiscoveryError("OpenAlex payload has no results")
        results: list[DiscoveryResult] = []
        for row in rows[:cap]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("display_name") or "").strip()
            doi = _doi_value(row.get("doi"))
            primary = row.get("primary_location")
            landing = ""
            container = ""
            if isinstance(primary, dict):
                landing = str(primary.get("landing_page_url") or "").strip()
                source = primary.get("source")
                if isinstance(source, dict):
                    container = str(source.get("display_name") or "").strip()
            openalex_id = str(row.get("id") or "").strip()
            url = _doi_url(doi) or landing or openalex_id
            if not title or not url:
                continue
            authors: list[str] = []
            for authorship in row.get("authorships") or []:
                if not isinstance(authorship, dict):
                    continue
                author = authorship.get("author")
                if isinstance(author, dict):
                    name = str(author.get("display_name") or "").strip()
                    if name:
                        authors.append(name)
            citation_kind = _citation_kind(str(row.get("type") or ""))
            results.append(
                DiscoveryResult(
                    provider=self.id,
                    title=title[:300],
                    url=url[:2048],
                    kind=_discovery_kind(citation_kind),
                    description=_openalex_abstract(row.get("abstract_inverted_index")),
                    meta=_citation_meta(
                        doi=doi,
                        authors=authors,
                        year=_year_value(row.get("publication_year")),
                        container=container,
                        citation_kind=citation_kind,
                    ),
                )
            )
        return results


class CrossrefSearchProvider(DiscoveryProvider):
    id = "crossref"
    label = "Crossref"

    def search(
        self,
        query: str,
        *,
        cap: int,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> list[DiscoveryResult]:
        fields = "DOI,title,author,issued,container-title,URL,type,abstract"
        url = (
            f"{CROSSREF_ENDPOINT}?query={quote(query.strip())}&rows={cap}"
            f"&select={quote(fields)}&mailto={quote(SCHOLARLY_MAILTO)}"
        )
        text = _fetch_text(url, transport=transport, resolver=resolver)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise DiscoveryError(f"Crossref returned non-JSON ({error})") from error
        message = payload.get("message") if isinstance(payload, dict) else None
        rows = message.get("items") if isinstance(message, dict) else None
        if not isinstance(rows, list):
            raise DiscoveryError("Crossref payload has no items")
        results: list[DiscoveryResult] = []
        for row in rows[:cap]:
            if not isinstance(row, dict):
                continue
            title = _first(row.get("title"))
            doi = _doi_value(row.get("DOI"))
            url = _doi_url(doi) or str(row.get("URL") or "").strip()
            if not title or not url:
                continue
            authors: list[str] = []
            for author in row.get("author") or []:
                if not isinstance(author, dict):
                    continue
                name = " ".join(
                    part
                    for part in (str(author.get("given") or ""), str(author.get("family") or ""))
                    if part.strip()
                ).strip()
                if name:
                    authors.append(name)
            issued = row.get("issued")
            year: int | None = None
            if isinstance(issued, dict):
                parts = issued.get("date-parts")
                if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                    year = _year_value(parts[0][0])
            citation_kind = _citation_kind(str(row.get("type") or ""))
            abstract = str(row.get("abstract") or "")
            results.append(
                DiscoveryResult(
                    provider=self.id,
                    title=title[:300],
                    url=url[:2048],
                    kind=_discovery_kind(citation_kind),
                    description=" ".join(abstract.split())[:800],
                    meta=_citation_meta(
                        doi=doi,
                        authors=authors,
                        year=year,
                        container=_first(row.get("container-title")),
                        citation_kind=citation_kind,
                    ),
                )
            )
        return results


class McpDiscoveryProvider(DiscoveryProvider):
    """External MCP server tool speaking the discovery contract (73-G).

    The tool receives `{"query": str}` and its text must be JSON — either a
    list of rows or `{"results": [...]}` — with every valid row carrying a
    non-empty `title` and an http(s) `url`. Invalid rows are dropped with a
    logged warning (never trusted, never faked).
    """

    def __init__(self, server: dict[str, Any], tool: dict[str, Any], audit: Any = None):
        from ..mcp_servers import build_mcp_config

        tool_name = str(tool.get("name"))
        self.id = f"mcp.{server.get('name')}.{tool_name}"
        self.label = f"{server.get('name')}.{tool_name}"
        self._tool_name = tool_name
        self._config = build_mcp_config(server)
        self._audit_session = audit

    def search(
        self,
        query: str,
        *,
        cap: int,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> list[DiscoveryResult]:
        started = time.monotonic()
        try:
            text = call_tool_sync(self._config, self._tool_name, {"query": query})
        except (McpToolError, Exception) as error:
            if self._audit_session is not None:
                audit_mcp_invocation(
                    self._audit_session,
                    tool_ref=self.id,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    ok=False,
                    error=str(error),
                )
            raise
        if self._audit_session is not None:
            audit_mcp_invocation(
                self._audit_session,
                tool_ref=self.id,
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=True,
            )
        return self._rows(text, cap)

    def _rows(self, text: str, cap: int) -> list[DiscoveryResult]:
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            logger.warning("mcp_discovery_non_json", provider=self.id)
            raise McpToolError(f"MCP tool '{self._tool_name}' returned non-JSON output") from None
        if isinstance(data, dict):
            data = data.get("results")
        if not isinstance(data, list):
            logger.warning("mcp_discovery_bad_shape", provider=self.id)
            return []
        results: list[DiscoveryResult] = []
        for row in data[: cap * 2]:
            if not isinstance(row, dict):
                logger.warning("mcp_discovery_invalid_row", provider=self.id)
                continue
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            if not title or not url.lower().startswith(("http://", "https://")):
                logger.warning("mcp_discovery_invalid_row", provider=self.id)
                continue
            try:
                kind = DiscoveryKind.parse(str(row.get("kind") or "other"))
            except ValueError:
                kind = DiscoveryKind.OTHER
            results.append(
                DiscoveryResult(
                    provider=self.id,
                    title=title[:300],
                    url=url[:2048],
                    kind=kind.value,
                    description=str(row.get("description") or "")[:800],
                    meta={"mcp": True},
                )
            )
            if len(results) >= cap:
                break
        return results


def discovery_preferences(session: Session, profile_id: str) -> dict[str, Any]:
    profile = session.get(Profile, profile_id)
    preferences = profile.preferences if profile is not None else None
    if not isinstance(preferences, dict):
        return {}
    raw = preferences.get("discovery")
    return raw if isinstance(raw, dict) else {}


def resolve_providers(
    session: Session,
    profile_id: str,
    transport: httpx.BaseTransport | None = None,
    requested: list[str] | None = None,
) -> list[DiscoveryProvider]:
    search_providers = [
        provider for provider in list_search_providers(session, profile_id) if provider["enabled"]
    ]
    keys = {
        provider["id"]: get_secret(provider_key_ref(provider["id"])) or ""
        for provider in search_providers
    }
    preferences = discovery_preferences(session, profile_id)
    enabled_raw = preferences.get("enabled")
    enabled = (
        [str(entry) for entry in enabled_raw]
        if isinstance(enabled_raw, list)
        else list(DEFAULT_ENABLED)
    )
    if requested is not None:
        enabled = [entry for entry in enabled if entry in requested]

    providers: list[DiscoveryProvider] = []
    if "web" in enabled and search_providers:
        providers.append(WebSearchProvider(search_providers, keys))
    if "youtube" in enabled:
        providers.append(YouTubeSearchProvider())
    scholarly: dict[str, type[DiscoveryProvider]] = {
        "arxiv": ArxivSearchProvider,
        "openalex": OpenAlexSearchProvider,
        "crossref": CrossrefSearchProvider,
    }
    for provider_id, provider_class in scholarly.items():
        if provider_id in enabled:
            providers.append(provider_class())

    sites_raw = preferences.get("sites")
    sites = (
        [entry for entry in sites_raw if isinstance(entry, dict)]
        if isinstance(sites_raw, list)
        else []
    )
    if search_providers:
        if not sites:
            sites = [dict(entry) for entry in DEFAULT_SITE_PRESETS]
        for entry in sites:
            site = str(entry.get("site", "")).strip()
            provider_id = f"site:{site}"
            if not site:
                continue
            if provider_id not in enabled and not (
                requested is not None and provider_id in requested
            ):
                continue
            providers.append(
                SiteSearchProvider(
                    site,
                    search_providers,
                    keys,
                    label=str(entry.get("label") or site),
                    default_kind=str(entry.get("kind") or DiscoveryKind.COURSE.value),
                )
            )
        if requested is not None:
            covered = {f"site:{entry.get('site', '')}" for entry in sites}
            for entry in DEFAULT_SITE_PRESETS:
                provider_id = f"site:{entry['site']}"
                if provider_id in requested and provider_id not in covered:
                    providers.append(
                        SiteSearchProvider(
                            entry["site"],
                            search_providers,
                            keys,
                            label=entry["label"],
                            default_kind=entry["kind"],
                        )
                    )

    from ..mcp_servers import enabled_tools

    for server, tool in enabled_tools(session, profile_id, "discovery"):
        provider = McpDiscoveryProvider(server, tool, audit=session)
        if requested is not None and provider.id not in requested:
            continue
        providers.append(provider)

    if requested is not None:
        available_ids = [provider.id for provider in providers]
        missing = [entry for entry in requested if entry not in available_ids]
        if missing:
            raise DiscoveryError(f"discovery provider(s) not configured: {', '.join(missing)}")
    return providers
