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
from app.search import SearchError, perform_fetch, perform_search, provider_key_ref

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


TAVILY_CONFIG = {"id": "sp1", "name": "Tavily", "type": "tavily", "enabled": True}


def test_perform_search_tavily_flavor() -> None:
    hits = perform_search(
        TAVILY_CONFIG,
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
        {"id": "sp2", "type": "searxng", "base_url": "http://localhost:8888"},
        "p vs np curriculum",
        transport=searxng_transport(),
    )
    assert len(hits) == 2


def test_perform_search_errors_surface_as_search_error() -> None:
    error_transport = httpx.MockTransport(lambda request: httpx.Response(503, text="down"))
    with pytest.raises(SearchError):
        perform_search(
            TAVILY_CONFIG,
            "query",
            api_key="k",
            transport=error_transport,
        )
    with pytest.raises(SearchError):
        perform_fetch("ftp://example.com/x")
    with pytest.raises(SearchError):
        perform_search({"id": "sp3", "type": "bogus"}, "query", transport=tavily_transport())


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


def test_search_providers_crud_roundtrip(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        empty = test_client.get("/api/v1/search-providers")
        assert empty.status_code == 200
        assert empty.json() == {"providers": []}

        created = test_client.post(
            "/api/v1/search-providers",
            json={"type": "tavily", "name": "Tavily", "api_key": "tvly-secret"},
        )
        assert created.status_code == 201, created.text
        provider = created.json()
        assert provider["type"] == "tavily"
        assert provider["enabled"] is True
        assert provider["key_set"] is True
        assert provider["key_hint"] == "••••cret"
        assert get_secret(provider_key_ref(provider["id"])) == "tvly-secret"

        # key semantics (desktop): absent keeps the stored key, "" clears it
        kept = test_client.put(
            f"/api/v1/search-providers/{provider['id']}",
            json={"name": "Tavily main"},
        )
        assert kept.status_code == 200, kept.text
        assert kept.json()["key_set"] is True
        assert kept.json()["name"] == "Tavily main"

        cleared = test_client.put(
            f"/api/v1/search-providers/{provider['id']}", json={"api_key": ""}
        )
        assert cleared.json()["key_set"] is False
        assert get_secret(provider_key_ref(provider["id"])) in (None, "")

        # ordered list: move up swaps, delete removes
        second = test_client.post(
            "/api/v1/search-providers", json={"type": "searxng", "base_url": "https://searx.example.org"}
        )
        assert second.status_code == 201, second.text
        second_id = second.json()["id"]
        moved = test_client.post(
            f"/api/v1/search-providers/{second_id}/move", json={"direction": "up"}
        )
        assert [entry["id"] for entry in moved.json()["providers"]] == [second_id, provider["id"]]

        assert (
            test_client.delete(f"/api/v1/search-providers/{second_id}").status_code == 204
        )
        remaining = test_client.get("/api/v1/search-providers").json()["providers"]
        assert [entry["id"] for entry in remaining] == [provider["id"]]

        catalog = test_client.get("/api/v1/search-providers/catalog")
        assert catalog.status_code == 200
        assert "searxng" in catalog.json()["providers"]
        assert catalog.json()["providers"]["tavily"]["requiresKey"] is True


def test_search_provider_settings_reject_bad_input(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        bad_type = test_client.post("/api/v1/search-providers", json={"type": "google"})
        assert bad_type.status_code == 422
        missing_base = test_client.post("/api/v1/search-providers", json={"type": "searxng"})
        assert missing_base.status_code == 422
        bad_url = test_client.post(
            "/api/v1/search-providers",
            json={"type": "tavily", "base_url": "api.tavily.com"},
        )
        assert bad_url.status_code == 422
        unknown = test_client.put(
            "/api/v1/search-providers/nope", json={"name": "x"}
        )
        assert unknown.status_code == 404


def test_search_provider_test_endpoint_probes(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        app.state.search_transport = searxng_transport()
        created = test_client.post(
            "/api/v1/search-providers",
            json={"type": "searxng", "base_url": "https://searx.example.org"},
        )
        provider_id = created.json()["id"]
        probe = test_client.post(f"/api/v1/search-providers/{provider_id}/test")
        assert probe.status_code == 200, probe.text
        assert probe.json()["status"] == "ok"
        assert probe.json()["result_count"] == 2


def test_legacy_single_provider_preference_migrates(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        from sqlalchemy import select
        from sqlalchemy.orm import sessionmaker

        from app.core.secrets import set_secret
        from app.domain.models import Profile

        # first request ensures the default profile exists
        assert test_client.get("/api/v1/search-providers").json() == {"providers": []}

        # seed the pre-plan-28 shape directly: one {base_url, flavor}
        # preference + the single legacy key slot
        factory = sessionmaker(bind=app.state.engine)
        with factory() as db:
            profile = db.scalars(select(Profile)).first()
            assert profile is not None
            profile.preferences = {
                "search_provider": {
                    "base_url": "https://searx.example.org/",
                    "flavor": "searxng",
                }
            }
            db.commit()
        set_secret("search:api_key", "legacy-secret")

        migrated = test_client.get("/api/v1/search-providers").json()["providers"]
        assert len(migrated) == 1
        provider = migrated[0]
        assert provider["id"] == "legacy"
        assert provider["type"] == "searxng"
        assert provider["base_url"] == "https://searx.example.org"
        assert provider["enabled"] is True
        assert provider["key_set"] is True
        assert get_secret(provider_key_ref("legacy")) == "legacy-secret"
        assert get_secret("search:api_key") in (None, "")

        # the legacy preference key is gone — migration is one-shot
        factory = sessionmaker(bind=app.state.engine)
        with factory() as db:
            profile = db.scalars(select(Profile)).first()
            assert isinstance(profile.preferences, dict)
            assert "search_provider" not in profile.preferences


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
        session = test_client.post("/api/v1/chat/sessions", json={"course_id": course_id}).json()
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
        saved = test_client.post(
            "/api/v1/search-providers",
            json={"type": "tavily", "base_url": "https://api.tavily.com", "api_key": "tvly-key"},
        )
        assert saved.status_code == 201, saved.text

        course_id = make_course(test_client)
        gateway.responses.append("SEARCH p vs np curriculum")
        gateway.responses.append(
            "See https://en.wikipedia.org/wiki/P_versus_NP for the canonical statement."
        )
        session = test_client.post("/api/v1/chat/sessions", json={"course_id": course_id}).json()
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
        saved = test_client.post(
            "/api/v1/search-providers",
            json={"type": "tavily", "base_url": "https://api.tavily.com", "api_key": "tvly-key"},
        )
        assert saved.status_code == 201
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
                            "sections": [{"title": "Basics", "objectives": ["Define P and NP"]}],
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
