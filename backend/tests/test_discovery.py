from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.orm import Session

from app.extensions.search.discovery import (
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

    provider = WebSearchProvider(
        [{"id": "sp1", "type": "tavily", "base_url": "https://tavily.example", "enabled": True}],
        {"sp1": "k"},
    )
    results = provider.search("chain rule", cap=5, transport=httpx.MockTransport(handler))
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
        [{"id": "sp2", "type": "searxng", "base_url": "https://searxng.example", "enabled": True}],
        {},
        label="Khan Academy",
    )
    results = provider.search("limits", cap=5, transport=httpx.MockTransport(handler))
    assert results == []
    assert seen == ["limits site:khanacademy.org"]


def test_youtube_provider_normalizes_flat_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.extensions.search.discovery as discovery_module

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
    import app.extensions.search.discovery as discovery_module

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


def test_resolve_providers_defaults_and_filtering(db_session: Session, owner: Any) -> None:
    from app.domain.models import Profile

    profile = Profile(user_id=owner.id, name="p")
    db_session.add(profile)
    db_session.commit()

    providers = resolve_providers(db_session, str(profile.id))
    assert [provider.id for provider in providers] == ["youtube", "arxiv", "openalex"]

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
    providers = resolve_providers(db_session, str(profile.id))
    assert [provider.id for provider in providers] == [
        "web",
        "youtube",
        f"site:{KHAN_ACADEMY_SITE}",
    ]

    filtered = resolve_providers(db_session, str(profile.id), requested=["youtube"])
    assert [provider.id for provider in filtered] == ["youtube"]


def test_resolve_providers_unconfigured_request_is_honest(
    db_session: Session,
) -> None:
    with pytest.raises(DiscoveryError, match="not configured"):
        resolve_providers(db_session, str(uuid4()), requested=["web"])


ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <published>2024-01-02T10:00:00Z</published>
    <title>Gradient descent convergence under interpolation</title>
    <summary>We bound the convergence rate of gradient descent.</summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <link rel="alternate" href="https://arxiv.org/abs/2401.00001v1"/>
    <arxiv:doi>10.1000/abc.123</arxiv:doi>
    <arxiv:journal_ref>Journal of Optimization 12 (2024)</arxiv:journal_ref>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <published>2024-02-03T10:00:00Z</published>
    <title>No link entry</title>
    <summary>Dropped because the alternate link is missing.</summary>
  </entry>
</feed>
"""


def _offline_resolver(host: str) -> list[str]:
    return ["93.184.216.34"]


def test_arxiv_provider_parses_atom_and_citation_meta() -> None:
    from app.extensions.search.discovery import ArxivSearchProvider

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["host"] == "export.arxiv.org"
        assert "search_query=all:gradient" in str(request.url)
        return httpx.Response(200, text=ARXIV_ATOM)

    provider = ArxivSearchProvider()
    rows = provider.search(
        "gradient",
        cap=5,
        transport=httpx.MockTransport(handler),
        resolver=_offline_resolver,
    )
    assert len(rows) == 2
    row = rows[0]
    assert row.provider == "arxiv"
    assert row.kind == "paper"
    assert row.url == "https://arxiv.org/abs/2401.00001v1"
    assert row.meta["doi"] == "10.1000/abc.123"
    assert row.meta["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert row.meta["year"] == 2024
    assert row.meta["citation_kind"] == "preprint"
    assert "convergence" in row.description


def test_arxiv_provider_rejects_malformed_atom() -> None:
    from app.extensions.search.discovery import ArxivSearchProvider, DiscoveryError

    provider = ArxivSearchProvider()
    with pytest.raises(DiscoveryError, match="malformed Atom"):
        provider.search(
            "gradient",
            cap=3,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<feed>")),
            resolver=_offline_resolver,
        )


def test_openalex_provider_parses_doi_and_abstract() -> None:
    from app.extensions.search.discovery import OpenAlexSearchProvider

    payload = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1000/openalex.1",
                "display_name": "Convergence of gradient descent",
                "publication_year": 2023,
                "type": "article",
                "authorships": [
                    {"author": {"display_name": "Grace Hopper"}},
                    {"author": {"display_name": "Ada Lovelace"}},
                ],
                "primary_location": {
                    "landing_page_url": "https://example.org/paper",
                    "source": {"display_name": "Optimization Letters"},
                },
                "abstract_inverted_index": {"Fast": [0], "convergence": [1], "proved": [2]},
            },
            {"display_name": "No DOI or landing page"},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["host"] == "api.openalex.org"
        return httpx.Response(200, json=payload)

    rows = OpenAlexSearchProvider().search(
        "gradient descent",
        cap=5,
        transport=httpx.MockTransport(handler),
        resolver=_offline_resolver,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "paper"
    assert row.url == "https://doi.org/10.1000/openalex.1"
    assert row.meta["container"] == "Optimization Letters"
    assert row.meta["authors"] == ["Grace Hopper", "Ada Lovelace"]
    assert row.description == "Fast convergence proved"


def test_crossref_provider_parses_items() -> None:
    from app.extensions.search.discovery import CrossrefSearchProvider

    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1000/cross.1",
                    "title": ["A survey of descent methods"],
                    "author": [{"given": "Katherine", "family": "Johnson"}],
                    "issued": {"date-parts": [[2022, 5]]},
                    "container-title": ["SIAM Review"],
                    "type": "book",
                },
                {"title": ["No DOI"], "URL": ""},
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["host"] == "api.crossref.org"
        return httpx.Response(200, json=payload)

    rows = CrossrefSearchProvider().search(
        "descent",
        cap=5,
        transport=httpx.MockTransport(handler),
        resolver=_offline_resolver,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "reference"
    assert row.url == "https://doi.org/10.1000/cross.1"
    assert row.meta["year"] == 2022
    assert row.meta["citation_kind"] == "book"
