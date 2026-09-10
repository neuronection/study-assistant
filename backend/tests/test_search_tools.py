import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, make_course

from app.ai.contracts.contracts import Constraint, validate
from app.core.config import Settings
from app.core.secrets import get_secret
from app.main import create_app
from app.search import SEARCH_KEYRING_REF, SearchError, perform_fetch, perform_search

TAVILY_BODY = {
    "results": [
        {
            "title": "P versus NP — Wikipedia",
            "url": "https://en.wikipedia.org/wiki/P_versus_NP",
            "content": "The P versus NP problem is a major unsolved problem.",
        },
        {
            "title": "Teaching P vs NP",
            "url": "https://example.edu/pnp",
            "content": "Most undergraduate curricula introduce it in theory courses.",
        },
    ]
}

SEARCH_PAGE = (
    "<html><body><h1>P vs NP in curricula</h1>"
    "<p>The problem anchors most undergraduate theory courses.</p></body></html>"
)


def tavily_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/search")
        body = json.loads(request.content)
        assert body["query"]
        return httpx.Response(200, json=TAVILY_BODY)

    return httpx.MockTransport(handler)


def searxng_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        assert request.url.params["q"]
        return httpx.Response(200, json=TAVILY_BODY)

    return httpx.MockTransport(handler)


def test_perform_search_tavily_flavor() -> None:
    hits = perform_search(
        "https://api.tavily.com",
        "tavily",
        "p vs np curriculum",
        api_key="tvly-key",
        transport=tavily_transport(),
    )
    assert [hit["url"] for hit in hits] == [
        "https://en.wikipedia.org/wiki/P_versus_NP",
        "https://example.edu/pnp",
    ]
    assert hits[0]["title"] == "P versus NP — Wikipedia"


def test_perform_search_searxng_flavor() -> None:
    hits = perform_search(
        "http://localhost:8888",
        "searxng",
        "p vs np curriculum",
        transport=searxng_transport(),
    )
    assert len(hits) == 2


def test_perform_search_errors_surface_as_search_error() -> None:
    error_transport = httpx.MockTransport(
        lambda request: httpx.Response(503, text="down")
    )
    with pytest.raises(SearchError):
        perform_search(
            "https://api.tavily.com",
            "tavily",
            "query",
            transport=error_transport,
        )
    with pytest.raises(SearchError):
        perform_fetch("ftp://example.com/x")
    with pytest.raises(SearchError):
        perform_search("https://x", "bogus", "query", transport=tavily_transport())


def test_perform_fetch_converts_html_and_truncates() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=SEARCH_PAGE, headers={"content-type": "text/html"})
    )
    text = perform_fetch("https://example.edu/pnp", transport=transport)
    assert "P vs NP in curricula" in text
    assert "undergraduate theory courses" in text

    huge = "x" * 6000
    long_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=huge, headers={"content-type": "text/plain"})
    )
    truncated = perform_fetch("https://example.edu/big", transport=long_transport)
    assert len(truncated) == 4001 and truncated.endswith("…")


@fixture
def gateway() -> ScriptedGateway:
    return ScriptedGateway([])


@fixture
def client(
    tmp_path: Path, gateway: ScriptedGateway
) -> Iterator[tuple[TestClient, ScriptedGateway, FastAPI]]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway, app


def test_search_provider_settings_roundtrip(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        empty = test_client.get("/api/v1/search-provider")
        assert empty.status_code == 200
        assert empty.json() == {
            "assigned": False,
            "base_url": None,
            "flavor": None,
            "key_set": False,
        }

        saved = test_client.put(
            "/api/v1/search-provider",
            json={
                "base_url": "https://api.tavily.com/",
                "flavor": "tavily",
                "api_key": "tvly-secret",
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["assigned"] is True
        assert saved.json()["base_url"] == "https://api.tavily.com"
        assert saved.json()["key_set"] is True
        assert get_secret(SEARCH_KEYRING_REF) == "tvly-secret"

        fetched = test_client.get("/api/v1/search-provider").json()
        assert fetched["assigned"] is True

        cleared = test_client.delete("/api/v1/search-provider")
        assert cleared.status_code == 204
        assert test_client.get("/api/v1/search-provider").json()["assigned"] is False
        assert get_secret(SEARCH_KEYRING_REF) in (None, "")


def test_search_provider_settings_reject_bad_input(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        bad_url = test_client.put(
            "/api/v1/search-provider",
            json={"base_url": "api.tavily.com", "flavor": "tavily"},
        )
        assert bad_url.status_code == 422
        bad_flavor = test_client.put(
            "/api/v1/search-provider",
            json={"base_url": "https://api.tavily.com", "flavor": "google"},
        )
        assert bad_flavor.status_code == 422


def wait_for_assistant(
    client: TestClient, session_id: int, timeout: float = 5.0
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages: list[dict[str, Any]] = client.get(
            f"/api/v1/chat/sessions/{session_id}/messages"
        ).json()
        if messages and messages[-1]["role"] == "assistant":
            return messages
        time.sleep(0.05)
    raise AssertionError("assistant never replied")


def test_chat_search_tool_unconfigured_is_honest(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        gateway.responses.append("SEARCH p vs np curriculum")
        gateway.responses.append("I could not search the web right now.")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "search for p vs np"},
        )
        assistant = wait_for_assistant(test_client, session["id"])[-1]
        assert len(assistant["tool_calls"]) == 1
        call = assistant["tool_calls"][0]
        assert call["name"] == "SEARCH"
        assert "no search provider configured" in call["result"]


def test_chat_search_tool_returns_cited_results(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        app.state.search_transport = tavily_transport()
        saved = test_client.put(
            "/api/v1/search-provider",
            json={"base_url": "https://api.tavily.com", "flavor": "tavily"},
        )
        assert saved.status_code == 200, saved.text

        course_id = make_course(test_client)
        gateway.responses.append("SEARCH p vs np curriculum")
        gateway.responses.append(
            "See https://en.wikipedia.org/wiki/P_versus_NP for the canonical statement."
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "search p vs np"},
        )
        assistant = wait_for_assistant(test_client, session["id"])[-1]
        call = assistant["tool_calls"][0]
        assert call["name"] == "SEARCH"
        assert "2 results" in (call["result"] or "")
        assert "wikipedia.org" in (call["result"] or "")
        assert assistant["markdown"] == (
            "See https://en.wikipedia.org/wiki/P_versus_NP for the canonical statement."
        )


def test_sources_advisory_fires_only_without_citations() -> None:
    sources = {"search_sources": ["https://en.wikipedia.org/wiki/P_versus_NP"]}
    contract = [Constraint("sources_cited_when_search_used", advisory=True)]

    cited = validate(
        "Per https://en.wikipedia.org/wiki/P_versus_NP the problem is open.",
        contract,
        dict(sources),
    )
    assert cited.advisories == []

    domain_cited = validate(
        "As wikipedia.org describes, the problem is open.", contract, dict(sources)
    )
    assert domain_cited.advisories == []

    uncited = validate("The problem is open.", contract, dict(sources))
    assert len(uncited.advisories) == 1
    assert uncited.advisories[0].constraint == "sources_cited_when_search_used"

    no_search = validate("The problem is open.", contract, {})
    assert no_search.advisories == []


def test_genesis_grounding_uses_search_provider(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        app.state.search_transport = tavily_transport()
        saved = test_client.put(
            "/api/v1/search-provider",
            json={"base_url": "https://api.tavily.com", "flavor": "tavily"},
        )
        assert saved.status_code == 200
        gateway.responses.append(
            json.dumps(
                {
                    "title": "P vs NP course",
                    "description": "d",
                    "subject": "CS",
                    "level": "university-intro",
                    "goals": [],
                    "chapters": [
                        {
                            "title": "Foundations",
                            "summary": "s",
                            "sections": [
                                {"title": "Basics", "objectives": ["Define P and NP"]}
                            ],
                        }
                    ],
                }
            )
        )
        response = test_client.post(
            "/api/v1/courses/genesis/draft",
            json={"topic": "P vs NP", "ground": True},
        )
        assert response.status_code == 200, response.text
        draft = response.json()
        assert "https://en.wikipedia.org/wiki/P_versus_NP" in draft["sources"]
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert "Web sources" in prompt
        assert "en.wikipedia.org" in prompt

        committed = test_client.post(
            "/api/v1/courses/genesis",
            json={"draft": draft, "lessons": False, "sources": draft["sources"]},
        )
        assert committed.status_code == 201, committed.text
        description = committed.json()["course"]["description"] or ""
        assert "Drafted with sources:" in description
