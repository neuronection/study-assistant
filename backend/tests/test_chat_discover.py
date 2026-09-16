import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pytest import fixture
from sqlalchemy import select
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, make_course

from app.ai.proposals import PROPOSAL_ACTIONS, AttachLinkPayload
from app.core.config import Settings
from app.domain.models import Material, MaterialLink
from app.main import create_app
from app.services.platform.chat import MAX_DISCOVER_ROUNDS

seen_queries: list[str] = []


def tavily_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen_queries.append(body["query"])
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Chain rule video",
                        "url": "https://youtube.com/watch?v=abc",
                        "content": "A walkthrough of the chain rule.",
                    },
                    {
                        "title": "Khan Academy — chain rule",
                        "url": "https://khanacademy.org/math/chain-rule",
                        "content": "Practice the chain rule.",
                    },
                ]
            },
        )

    return httpx.MockTransport(handler)


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


def wait_for_assistant(
    client: TestClient, session_id: int, timeout: float = 30.0
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages: list[dict[str, Any]] = client.get(
            f"/api/v1/chat/sessions/{session_id}/messages"
        ).json()
        if messages and messages[-1]["role"] == "assistant":
            return messages
        time.sleep(0.05)
    raise AssertionError(
        f"assistant never replied; last messages: {messages[-1] if messages else None}"
    )


def enable_web_only(test_client: TestClient) -> None:
    prefs = test_client.put(
        "/api/v1/profiles/preferences",
        json={"discovery": {"enabled": ["web"], "sites": []}},
    )
    assert prefs.status_code == 200, prefs.text


def test_discover_catalog_entry_and_grammar() -> None:
    from app.ai.tools import CHAT_TOOL_CATALOG, CHAT_TOOL_DOC, extract_tool_calls

    entry = next(tool for tool in CHAT_TOOL_CATALOG if tool["name"] == "DISCOVER")
    assert "here" in entry["description"]
    assert "DISCOVER" in CHAT_TOOL_DOC

    calls = extract_tool_calls("DISCOVER here\nSEARCH something else")
    assert ("DISCOVER", "here") in calls


def test_discover_here_builds_query_from_node_context(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    seen_queries.clear()
    with test_client:
        app.state.search_transport = tavily_transport()
        assert (
            test_client.put(
                "/api/v1/search-provider",
                json={"base_url": "https://api.tavily.com", "flavor": "tavily"},
            )
        ).status_code == 200
        enable_web_only(test_client)

        course_id = make_course(test_client)
        tree = test_client.get(f"/api/v1/courses/{course_id}/tree").json()
        root_id = int(tree[0]["id"])
        node = test_client.post(
            f"/api/v1/courses/{course_id}/nodes",
            json={
                "course_id": course_id,
                "parent_id": root_id,
                "title": "Integration techniques",
                "summary": "Substitution and parts",
            },
        ).json()

        gateway.responses.append("DISCOVER here")
        gateway.responses.append("Here is what I found.")
        session = test_client.post(
            "/api/v1/chat/sessions",
            json={"course_id": course_id, "node_id": int(node["id"])},
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "find me material here"},
        )
        assistant = wait_for_assistant(test_client, session["id"])[-1]
        call = assistant["tool_calls"][0]
        assert call["name"] == "DISCOVER"
        assert "2 results" in (call["result"] or "")
        assert "youtube.com" in (call["result"] or "")

        assert len(seen_queries) == 1
        query = seen_queries[0]
        assert "Integration techniques" in query
        assert "Substitution and parts" in query


def test_discover_here_falls_back_to_course_context(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    seen_queries.clear()
    with test_client:
        app.state.search_transport = tavily_transport()
        test_client.put(
            "/api/v1/search-provider",
            json={"base_url": "https://api.tavily.com", "flavor": "tavily"},
        )
        enable_web_only(test_client)
        course_id = make_course(test_client, title="Linear Algebra")

        gateway.responses.append("DISCOVER here")
        gateway.responses.append("Answer.")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "discover"},
        )
        wait_for_assistant(test_client, session["id"])
        assert seen_queries and "Linear Algebra" in seen_queries[0]


def test_discover_here_without_course_is_honest(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        app.state.search_transport = tavily_transport()
        test_client.put(
            "/api/v1/search-provider",
            json={"base_url": "https://api.tavily.com", "flavor": "tavily"},
        )
        enable_web_only(test_client)

        gateway.responses.append("DISCOVER here")
        gateway.responses.append("Answer.")
        session = test_client.post("/api/v1/chat/sessions", json={}).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "discover here"},
        )
        assistant = wait_for_assistant(test_client, session["id"])[-1]
        call = assistant["tool_calls"][0]
        assert call["name"] == "DISCOVER"
        assert "no course context" in call["result"]


def test_discover_unconfigured_is_honest(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        enable_web_only(test_client)
        course_id = make_course(test_client)
        gateway.responses.append("DISCOVER chain rule videos")
        gateway.responses.append("Answer.")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "discover chain rule"},
        )
        assistant = wait_for_assistant(test_client, session["id"])[-1]
        call = assistant["tool_calls"][0]
        assert "no discovery providers configured" in call["result"]


def test_discover_budget_is_two_per_turn(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        app.state.search_transport = tavily_transport()
        test_client.put(
            "/api/v1/search-provider",
            json={"base_url": "https://api.tavily.com", "flavor": "tavily"},
        )
        enable_web_only(test_client)
        course_id = make_course(test_client)
        gateway.responses.append(
            "DISCOVER limits\nDISCOVER derivatives\nDISCOVER integrals"
        )
        gateway.responses.append("Answer.")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "discover a lot"},
        )
        assistant = wait_for_assistant(test_client, session["id"])[-1]
        calls = [call for call in assistant["tool_calls"] if call["name"] == "DISCOVER"]
        assert len(calls) == 2
        assert MAX_DISCOVER_ROUNDS == 2
        feedback = "\n".join(
            str(message.content)
            for call_round in gateway.calls
            for message in call_round
        )
        assert "DISCOVER budget for this turn is spent" in feedback


def test_attach_link_payload_rejects_non_http() -> None:
    assert "attach_link" in PROPOSAL_ACTIONS
    with pytest.raises(ValidationError):
        AttachLinkPayload.model_validate({"url": "ftp://example.com/file"})
    payload = AttachLinkPayload.model_validate(
        {"url": "https://example.com/chain-rule", "node_id": None}
    )
    assert payload.url == "https://example.com/chain-rule"


def test_attach_link_executes_creates_link_material(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        node_id = make_node(test_client, course_id, "Ch7")
        proposal_text = (
            "```proposal\n"
            + json.dumps(
                {
                    "action": "attach_link",
                    "url": "https://youtube.com/watch?v=abc123",
                    "title": "Chain rule video",
                    "node_id": node_id,
                }
            )
            + "\n```"
        )
        gateway.responses.append(f"Found this.\n\n{proposal_text}")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "attach that video"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "attach_link"
        assert proposal["payload"]["target_kind"] == "link"
        assert proposal["payload"]["target_name"] == "Chain rule video"

        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "executed"
        assert body["result"]["deduped"] is False

        stored = app.state.session_factory()
        material = stored.get(Material, int(body["result"]["material_id"]))
        assert material is not None
        assert material.kind == "link"
        assert material.course_id == course_id
        link = stored.scalars(
            select(MaterialLink).where(
                MaterialLink.node_id == node_id,
                MaterialLink.material_id == material.id,
            )
        ).first()
        stored.close()
        assert link is not None


def test_attach_link_stale_node_fails_honestly(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        node_id = make_node(test_client, course_id, "Temp")
        proposal_text = (
            "```proposal\n"
            + json.dumps(
                {
                    "action": "attach_link",
                    "url": "https://example.com/x",
                    "node_id": node_id,
                }
            )
            + "\n```"
        )
        gateway.responses.append(f"Proposal.\n\n{proposal_text}")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "attach"},
        )
        proposal = get_proposal(test_client, session["id"])
        deleted = test_client.delete(f"/api/v1/nodes/{node_id}")
        assert deleted.status_code == 200
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] in ("stale", "failed")


def test_attach_link_second_attach_dedupes(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        url = "https://example.com/chain-rule?utm_source=x"

        def propose_and_approve() -> dict[str, Any]:
            proposal_text = (
                "```proposal\n"
                + json.dumps({"action": "attach_link", "url": url})
                + "\n```"
            )
            gateway.responses.append(f"Found this.\n\n{proposal_text}")
            session = test_client.post(
                "/api/v1/chat/sessions", json={"course_id": course_id}
            ).json()
            test_client.post(
                f"/api/v1/chat/sessions/{session['id']}/messages",
                json={"content": "attach it"},
            )
            proposal = get_proposal(test_client, session["id"])
            approved = test_client.post(
                f"/api/v1/chat/proposals/{proposal['id']}/approve"
            )
            assert approved.status_code == 200, approved.text
            data: dict[str, Any] = approved.json()
            return data

        first = propose_and_approve()
        assert first["status"] == "executed"
        assert first["result"]["deduped"] is False
        second = propose_and_approve()
        assert second["status"] == "executed"
        assert second["result"]["deduped"] is True


def make_node(test_client: TestClient, course_id: int, title: str) -> int:
    tree = test_client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = int(tree[0]["id"])
    created = test_client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": title},
    )
    return int(created.json()["id"])


def get_proposal(test_client: TestClient, session_id: int) -> dict[str, Any]:
    messages = wait_for_assistant(test_client, session_id)
    proposals: list[dict[str, Any]] = messages[-1]["proposals"]
    assert proposals
    return proposals[0]
