import httpx
import pytest
from sqlalchemy.orm import Session

from app.search.discovery import (
    KHAN_ACADEMY_SITE,
    DiscoveryError,
    SiteSearchProvider,
    WebSearchProvider,
    YouTubeSearchProvider,
    resolve_providers,
)


def test_web_provider_normalizes_tavily_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/search")
        body = httpx.request.__class__  # unused; keep handler pure
        del body
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Chain rule",
                        "url": "https://en.wikipedia.org/wiki/Chain_rule",
                        "content": "The chain rule differentiates compositions.",
                    },
                    {"url": ""},
                ]
            },
        )

    provider = WebSearchProvider("https://tavily.example", "tavily", api_key="k")
    results = provider.search(
        "chain rule", cap=5, transport=httpx.MockTransport(handler)
    )
    assert len(results) == 1
    assert results[0].provider == "web"
    assert results[0].kind == "article"
    assert "differentiates" in results[0].description


def test_site_provider_appends_site_filter() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(str(request.url))
        seen.extend(parse_qs(parsed.query).get("q", []))
        return httpx.Response(200, json={"results": []})

    provider = SiteSearchProvider(
        KHAN_ACADEMY_SITE,
        "https://searxng.example",
        "searxng",
        label="Khan Academy",
    )
    results = provider.search(
        "limits", cap=5, transport=httpx.MockTransport(handler)
    )
    assert results == []
    assert seen == ["limits site:khanacademy.org"]


def test_youtube_provider_normalizes_flat_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.search.discovery as discovery_module

    def fake_search(query: str, cap: int) -> list[dict[str, object]]:
        assert query == "integration by parts"
        assert cap == 3
        return [
            {
                "title": "Integration by parts",
                "url": "https://youtube.com/watch?v=xyz",
                "duration": 754,
                "channel": "Math Academy",
            },
            {"title": "no url"},
        ]

    monkeypatch.setattr(discovery_module, "search_videos", fake_search)
    provider = YouTubeSearchProvider()
    results = provider.search("integration by parts", cap=3)
    assert len(results) == 1
    assert results[0].kind == "video"
    assert results[0].meta["duration"] == "12:34"
    assert results[0].meta["channel"] == "Math Academy"


def test_search_videos_builds_ytsearch_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.search.discovery as discovery_module

    captured: dict[str, str] = {}

    class FakeYdl:
        def __init__(self, options: dict[str, object]) -> None:
            pass

        def __enter__(self) -> "FakeYdl":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def extract_info(self, url: str, download: bool) -> dict[str, object]:
            captured["url"] = url
            assert download is False
            return {"entries": [{"title": "t", "url": "https://x"}]}

    import sys
    import types

    fake_module = types.ModuleType("yt_dlp")
    fake_module.YoutubeDL = FakeYdl  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)
    rows = discovery_module.search_videos("chain rule", 4)
    assert captured["url"] == "ytsearch4:chain rule"
    assert len(rows) == 1


def test_resolve_providers_defaults_and_filtering(db_session: Session) -> None:
    from app.domain.models import Profile

    profile = Profile(name="p")
    db_session.add(profile)
    db_session.commit()

    providers = resolve_providers(db_session, int(profile.id))
    assert [provider.id for provider in providers] == ["youtube"]

    profile.preferences = {
        "search_provider": {
            "base_url": "https://searxng.example",
            "flavor": "searxng",
        },
        "discovery": {
            "enabled": ["web", "youtube", f"site:{KHAN_ACADEMY_SITE}"],
            "sites": [
                {
                    "site": KHAN_ACADEMY_SITE,
                    "label": "Khan Academy",
                    "kind": "course",
                }
            ],
        },
    }
    db_session.commit()
    providers = resolve_providers(db_session, int(profile.id))
    assert [provider.id for provider in providers] == [
        "web",
        "youtube",
        f"site:{KHAN_ACADEMY_SITE}",
    ]

    filtered = resolve_providers(
        db_session, int(profile.id), requested=["youtube"]
    )
    assert [provider.id for provider in filtered] == ["youtube"]


def test_resolve_providers_unconfigured_request_is_honest(
    db_session: Session,
) -> None:
    with pytest.raises(DiscoveryError, match="not configured"):
        resolve_providers(db_session, 1, requested=["web"])
