"""Discovery provider registry: normalized results over pluggable sources.

Providers return `DiscoveryResult` rows; results are never persisted (same
posture as the chat SEARCH tool). No first-party integration with
ToS-restricted platforms — site-filtered presets are data, not scrapers
(ADR-166/170). MCP connector providers (73-G) invoke user-registered
external servers deterministically and validate every row app-side.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from sqlalchemy.orm import Session

from ..ai.mcp_client import (
    McpToolError,
    audit_mcp_invocation,
    call_tool_sync,
)
from ..core.secrets import get_secret
from ..core.vocab import DiscoveryKind
from ..domain.models import Profile
from .provider import (
    SEARCH_KEYRING_REF,
    search_provider_config,
)

logger = structlog.get_logger(__name__)

DEFAULT_ENABLED = ("web", "youtube")
KHAN_ACADEMY_SITE = "khanacademy.org"


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
        self, query: str, *, cap: int, transport: httpx.BaseTransport | None = None
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
        self, base_url: str, flavor: str, api_key: str = "", cap_limit: int = 8
    ) -> None:
        self._base_url = base_url
        self._flavor = flavor
        self._api_key = api_key
        self._cap_limit = cap_limit

    def search(
        self, query: str, *, cap: int, transport: httpx.BaseTransport | None = None
    ) -> list[DiscoveryResult]:
        from .provider import perform_search

        hits = perform_search(
            self._base_url,
            self._flavor,
            query,
            api_key=self._api_key,
            transport=transport,
            limit=min(cap, self._cap_limit),
        )
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
        base_url: str,
        flavor: str,
        api_key: str = "",
        label: str | None = None,
        default_kind: str = DiscoveryKind.COURSE.value,
        cap_limit: int = 8,
    ) -> None:
        self.site = site
        self._base_url = base_url
        self._flavor = flavor
        self._api_key = api_key
        self.id = f"site:{site}"
        self.label = label or site
        self._default_kind = default_kind
        self._cap_limit = cap_limit

    def search(
        self, query: str, *, cap: int, transport: httpx.BaseTransport | None = None
    ) -> list[DiscoveryResult]:
        from .provider import perform_search

        hits = perform_search(
            self._base_url,
            self._flavor,
            f"{query} site:{self.site}",
            api_key=self._api_key,
            transport=transport,
            limit=min(cap, self._cap_limit),
        )
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

    with yt_dlp.YoutubeDL(
        {"quiet": True, "no_warnings": True, "extract_flat": True}
    ) as ydl:
        info = dict(ydl.extract_info(f"ytsearch{cap}:{query}", download=False))
    entries = info.get("entries") if isinstance(info, dict) else None
    return [entry for entry in entries if isinstance(entry, dict)] if entries else []


class YouTubeSearchProvider(DiscoveryProvider):
    id = "youtube"
    label = "YouTube"

    def search(
        self, query: str, *, cap: int, transport: httpx.BaseTransport | None = None
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


class McpDiscoveryProvider(DiscoveryProvider):
    """External MCP server tool speaking the discovery contract (73-G).

    The tool receives `{"query": str}` and its text must be JSON — either a
    list of rows or `{"results": [...]}` — with every valid row carrying a
    non-empty `title` and an http(s) `url`. Invalid rows are dropped with a
    logged warning (never trusted, never faked).
    """

    def __init__(self, server: dict[str, Any], tool: dict[str, Any], audit: Any = None):
        from ..services.platform.mcp_servers import build_mcp_config

        tool_name = str(tool.get("name"))
        self.id = f"mcp.{server.get('name')}.{tool_name}"
        self.label = f"{server.get('name')}.{tool_name}"
        self._tool_name = tool_name
        self._config = build_mcp_config(server)
        self._audit_session = audit

    def search(
        self, query: str, *, cap: int, transport: httpx.BaseTransport | None = None
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
            raise McpToolError(
                f"MCP tool '{self._tool_name}' returned non-JSON output"
            ) from None
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


def discovery_preferences(session: Session, profile_id: int) -> dict[str, Any]:
    profile = session.get(Profile, profile_id)
    preferences = profile.preferences if profile is not None else None
    if not isinstance(preferences, dict):
        return {}
    raw = preferences.get("discovery")
    return raw if isinstance(raw, dict) else {}


def resolve_providers(
    session: Session,
    profile_id: int,
    transport: httpx.BaseTransport | None = None,
    requested: list[str] | None = None,
) -> list[DiscoveryProvider]:
    config = search_provider_config(session, profile_id)
    api_key = get_secret(SEARCH_KEYRING_REF) or ""
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
    if "web" in enabled and config is not None:
        providers.append(
            WebSearchProvider(config["base_url"], config["flavor"], api_key)
        )
    if "youtube" in enabled:
        providers.append(YouTubeSearchProvider())

    sites_raw = preferences.get("sites")
    sites = (
        [entry for entry in sites_raw if isinstance(entry, dict)]
        if isinstance(sites_raw, list)
        else []
    )
    if config is not None:
        if not sites:
            sites = [
                {
                    "site": KHAN_ACADEMY_SITE,
                    "label": "Khan Academy",
                    "kind": DiscoveryKind.COURSE.value,
                }
            ]
        for entry in sites:
            site = str(entry.get("site", "")).strip()
            if not site or f"site:{site}" not in enabled:
                continue
            providers.append(
                SiteSearchProvider(
                    site,
                    config["base_url"],
                    config["flavor"],
                    api_key=api_key,
                    label=str(entry.get("label") or site),
                    default_kind=str(
                        entry.get("kind") or DiscoveryKind.COURSE.value
                    ),
                )
            )

    from ..services.platform.mcp_servers import enabled_tools

    for server, tool in enabled_tools(session, profile_id, "discovery"):
        provider = McpDiscoveryProvider(server, tool, audit=session)
        if requested is not None and provider.id not in requested:
            continue
        providers.append(provider)

    if requested is not None:
        available_ids = [provider.id for provider in providers]
        missing = [entry for entry in requested if entry not in available_ids]
        if missing:
            raise DiscoveryError(
                f"discovery provider(s) not configured: {', '.join(missing)}"
            )
    return providers
