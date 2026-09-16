import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.ai.mcp_client as mcp_client
from app.ai.mcp_client import McpToolError
from app.domain.models import AiInteraction, MaterialSuggestion, Profile
from app.parsers.base import ParserError, build_registry, resolve_parser
from app.parsers.mcp_parse import McpParseParser
from app.search.discovery import resolve_providers


def make_config(command: str, args: list[str]) -> mcp_client.McpServerConfig:
    return mcp_client.McpServerConfig(
        id="abc123def456",
        name="coursehub",
        command=command,
        args=args,
        enabled=True,
        timeout_sec=30,
        tools=[],
        last_error=None,
        refreshed_at=None,
    )


SERVER: dict[str, Any] = {
    "id": "abc123def456",
    "name": "coursehub",
    "command": "python",
    "args": ["-m", "coursehub_server"],
    "enabled": True,
    "timeout_sec": 30,
    "tools": [
        {
            "name": "search_courses",
            "description": "Search external courses",
            "enabled": True,
            "contract": "discovery",
            "url_pattern": None,
        },
        {
            "name": "fetch_course",
            "description": "Fetch a course page",
            "enabled": True,
            "contract": "parse",
            "url_pattern": "coursehub.example/learn/*",
        },
    ],
    "last_error": None,
    "refreshed_at": "2026-09-16T00:00:00+00:00",
}

DISCOVERY_ROWS = [
    {"title": "Intro course", "url": "https://coursehub.example/learn/1",
     "kind": "course", "description": "Learn things"},
    {"title": ""},
    {"url": "https://coursehub.example/2"},
    "not-a-dict",
]


def seed_servers(db_session: Session, *servers: dict[str, Any]) -> int:
    from app.services.platform.profiles import ensure_default_profile

    profile = ensure_default_profile(db_session)
    prefs = dict(profile.preferences or {})
    prefs["mcp"] = {"servers": list(servers)}
    profile.preferences = prefs
    db_session.commit()
    return int(profile.id)


def test_mcp_server_crud_and_validation(client: TestClient) -> None:
    with client:
        created = client.post(
            "/api/v1/mcp/servers",
            json={"name": "coursehub", "command": "python", "args": ["-m", "srv"]},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["enabled"] is False
        assert body["tools"] == []

        listed = client.get("/api/v1/mcp/servers").json()
        assert [row["name"] for row in listed] == ["coursehub"]

        bad_timeout = client.post(
            "/api/v1/mcp/servers",
            json={"name": "x", "command": "y", "timeout_sec": 1},
        )
        assert bad_timeout.status_code == 422

        empty_command = client.post(
            "/api/v1/mcp/servers", json={"name": "x", "command": "  "}
        )
        assert empty_command.status_code == 422

        unknown_tool = client.patch(
            f"/api/v1/mcp/servers/{body['id']}",
            json={"tools": [{"name": "nope", "enabled": True}]},
        )
        assert unknown_tool.status_code == 422

        bad_contract = client.patch(
            f"/api/v1/mcp/servers/{body['id']}",
            json={
                "tools": [{"name": "t", "enabled": True, "contract": "magic"}]
            },
        )
        assert bad_contract.status_code == 422

        assert (
            client.delete(f"/api/v1/mcp/servers/{body['id']}").status_code == 204
        )
        assert client.get("/api/v1/mcp/servers").json() == []
        assert (
            client.delete(f"/api/v1/mcp/servers/{body['id']}").status_code == 404
        )


def test_refresh_lists_tools_and_preserves_tool_settings(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_list_tools(config: object) -> list[dict[str, str]]:
        assert getattr(config, "command", "") == "python"
        return [
            {"name": "search_courses", "description": "Search external courses"},
            {"name": "fetch_course", "description": "Fetch a course page"},
        ]

    monkeypatch.setattr(mcp_client, "list_tools_sync", fake_list_tools)
    with client:
        created = client.post(
            "/api/v1/mcp/servers",
            json={"name": "coursehub", "command": "python"},
        ).json()
        patched = client.patch(
            f"/api/v1/mcp/servers/{created['id']}",
            json={"enabled": True},
        )
        assert patched.status_code == 200

        refreshed = client.post(f"/api/v1/mcp/servers/{created['id']}/refresh")
        assert refreshed.status_code == 200, refreshed.text
        tools = refreshed.json()["tools"]
        assert [tool["name"] for tool in tools] == [
            "search_courses",
            "fetch_course",
        ]
        assert all(tool["enabled"] is False for tool in tools)

        enabled = client.patch(
            f"/api/v1/mcp/servers/{created['id']}",
            json={
                "tools": [
                    {
                        "name": "search_courses",
                        "enabled": True,
                        "contract": "discovery",
                    }
                ]
            },
        )
        assert enabled.status_code == 200

        refreshed_again = client.post(
            f"/api/v1/mcp/servers/{created['id']}/refresh"
        ).json()
        by_name = {tool["name"]: tool for tool in refreshed_again["tools"]}
        assert by_name["search_courses"]["enabled"] is True
        assert by_name["search_courses"]["contract"] == "discovery"


def test_refresh_failure_is_recorded(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(config: object) -> list[dict[str, str]]:
        raise McpToolError("server failed to launch")

    monkeypatch.setattr(mcp_client, "list_tools_sync", failing)
    with client:
        created = client.post(
            "/api/v1/mcp/servers",
            json={"name": "broken", "command": "python"},
        ).json()
        refreshed = client.post(f"/api/v1/mcp/servers/{created['id']}/refresh")
        assert refreshed.status_code == 502
        assert "server failed to launch" in refreshed.json()["detail"]

        listed = client.get("/api/v1/mcp/servers").json()
        assert "server failed to launch" in (listed[0]["last_error"] or "")


def test_mcp_discovery_provider_normalizes_and_dedupes(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_id = seed_servers(db_session, SERVER)

    def fake_call(
        config: object,
        tool_name: str,
        arguments: dict[str, object],
        timeout_sec: int | None = None,
    ) -> str:
        assert arguments["query"] == "calculus"
        return json.dumps({"results": DISCOVERY_ROWS})

    del profile_id

    monkeypatch.setattr("app.search.discovery.call_tool_sync", fake_call)

    profile = db_session.scalars(select(Profile)).first()
    assert profile is not None
    providers = resolve_providers(db_session, int(profile.id))
    provider = next(p for p in providers if p.id == "mcp.coursehub.search_courses")
    results = provider.search("calculus", cap=5)
    assert [row.title for row in results] == ["Intro course"]
    assert results[0].kind == "course"
    assert results[0].url == "https://coursehub.example/learn/1"
    assert results[0].meta["mcp"] is True


def test_discovery_search_with_mcp_provider_audits(
    db_session: Session,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_servers(db_session, SERVER)

    def fake_call(
        config: object,
        tool_name: str,
        arguments: dict[str, object],
        timeout_sec: int | None = None,
    ) -> str:
        return json.dumps(
            {"results": [DISCOVERY_ROWS[0]]}
        )

    monkeypatch.setattr("app.search.discovery.call_tool_sync", fake_call)
    with client:
        response = client.post(
            "/api/v1/discovery/search",
            json={"query": "calculus", "providers": ["mcp.coursehub.search_courses"]},
        )
        assert response.status_code == 200, response.text
        rows = response.json()["results"]
        assert len(rows) == 1
        assert rows[0]["provider"] == "mcp.coursehub.search_courses"
        assert rows[0]["kind"] == "course"

    audit_rows = list(
        db_session.scalars(
            select(AiInteraction).where(AiInteraction.task == "mcp_tool_call")
        )
    )
    assert len(audit_rows) == 1
    assert audit_rows[0].model == "mcp.coursehub.search_courses"


def test_mcp_parse_parser_matches_and_validates_contract(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    del db_session
    parser = McpParseParser(SERVER, SERVER["tools"][1])
    assert parser.matches("https://coursehub.example/learn/42") is True
    assert parser.matches("https://other.example/learn/42") is False
    assert parser.matches("ftp://coursehub.example/learn/42") is False

    parser._config = make_config(
        str(SERVER["command"]), [str(arg) for arg in SERVER["args"]]
    )

    def fake_call(
        config: object,
        tool_name: str,
        arguments: dict[str, object],
        timeout_sec: int | None = None,
    ) -> str:
        assert arguments["url"] == "https://coursehub.example/learn/42"
        return json.dumps(
            {
                "title": "Course 42",
                "markdown": "# Course 42\n\nAll about it.",
                "metadata": {"level": "intro"},
            }
        )

    monkeypatch.setattr("app.parsers.mcp_parse.call_tool_sync", fake_call)
    parsed = parser.fetch("https://coursehub.example/learn/42")
    assert parsed.title == "Course 42"
    assert (parsed.markdown or "").startswith("# Course 42")
    assert parsed.metadata["mcp_tool"] == "mcp.coursehub.fetch_course"
    assert parsed.metadata["level"] == "intro"


def test_mcp_parse_parser_rejects_contract_violations(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    parser = McpParseParser(SERVER, SERVER["tools"][1])

    parser._config = make_config("python", [])

    monkeypatch.setattr(
        "app.parsers.mcp_parse.call_tool_sync", lambda *a, **k: "not json at all"
    )
    with pytest.raises(ParserError, match="non-JSON"):
        parser.fetch("https://coursehub.example/learn/1")

    monkeypatch.setattr(
        "app.parsers.mcp_parse.call_tool_sync",
        lambda *a, **k: json.dumps({"title": "no markdown"}),
    )
    with pytest.raises(ParserError, match="no markdown"):
        parser.fetch("https://coursehub.example/learn/1")


def test_build_registry_includes_mcp_parsers_first(
    db_session: Session,
) -> None:
    profile_id = seed_servers(db_session, SERVER)
    registry = build_registry(session=db_session, profile_id=profile_id)
    assert isinstance(registry[0], McpParseParser)
    hit = resolve_parser(registry, "https://coursehub.example/learn/9")
    assert isinstance(hit, McpParseParser)
    assert resolve_parser(registry, "https://example.com/page") is not None
    assert not isinstance(resolve_parser(registry, "https://example.com/page"), McpParseParser)


def test_parse_contract_lands_in_url_import(
    db_session: Session,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The url_import job runs the MCP parse tool like a built-in parser."""
    import time as time_module

    seed_servers(db_session, SERVER)
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        linked = client.post(
            "/api/v1/materials/link",
            json={
                "course_id": course_id,
                "url": "https://coursehub.example/learn/42?ref=x",
            },
        )
        assert linked.status_code == 200, linked.text
        material_id = int(linked.json()["material"]["id"])

        def fake_call(
            config: object,
            tool_name: str,
            arguments: dict[str, object],
            timeout_sec: int | None = None,
        ) -> str:
            return json.dumps(
                {
                    "title": "Imported course",
                    "markdown": "# Imported course\n\nContent body.",
                }
            )

        monkeypatch.setattr("app.parsers.mcp_parse.call_tool_sync", fake_call)

        queued = client.post(f"/api/v1/materials/{material_id}/parse")
        assert queued.status_code == 200, queued.text
        job_id = int(queued.json()["job_id"])

        deadline = time_module.monotonic() + 30
        while time_module.monotonic() < deadline:
            job = client.get(f"/api/v1/jobs/{job_id}").json()
            if job["status"] in ("done", "failed"):
                break
            time_module.sleep(0.1)
        assert job["status"] == "done", job

        detail = client.get(f"/api/v1/materials/{material_id}").json()
        assert detail["extraction"] is not None
        assert "Imported course" in detail["extraction"]["markdown"]

    audit_rows = list(
        db_session.scalars(
            select(AiInteraction).where(AiInteraction.task == "mcp_tool_call")
        )
    )
    assert audit_rows
    suggestions = list(db_session.scalars(select(MaterialSuggestion)))
    assert suggestions == []
