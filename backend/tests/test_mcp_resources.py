import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from sqlalchemy import select

from app.core.config import Settings
from app.domain.models import Note
from app.main import create_app
from app.storage.db import make_engine, make_session_factory

CAQ: dict[str, Any] = {
    "$schema": "caq/v1",
    "title": "MCP probe",
    "questions": [
        {
            "id": "q1",
            "type": "truefalse",
            "stem_md": "probe",
            "answer": True,
            "explanation_md": "ok",
            "concepts": ["probe"],
            "skill": "conceptual",
            "bloom": "remember",
            "difficulty": 1,
            "expected_time_sec": 30,
        }
    ],
}


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


@pytest.fixture
def seeded(tmp_path: Path) -> dict[str, Any]:
    app = create_app(Settings(data_dir=tmp_path, log_level="WARNING"))
    with TestClient(app) as client:
        course_id = int(client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"])
        root = int(client.get(f"/api/v1/courses/{course_id}/tree").json()[0]["id"])
        chapter = int(
            client.post(
                f"/api/v1/courses/{course_id}/nodes",
                json={"course_id": course_id, "parent_id": root, "title": "Limits"},
            ).json()["id"]
        )
        upload = client.post(
            "/api/v1/materials",
            params={"course_id": course_id},
            files={"file": ("m.txt", b"limit content", "text/plain")},
        )
        material_id = int(upload.json()["material"]["id"])
        wait_until(
            lambda: client.get(f"/api/v1/materials/{material_id}")
            .json()["material"]["status"]
            == "ready"
        )
        client.post(f"/api/v1/nodes/{chapter}/materials", json={"material_id": material_id})
        client.post(
            "/api/v1/quiz/import",
            params={"dry_run": "false", "course_id": course_id},
            json=CAQ,
        )
        client.post(
            "/api/v1/notes",
            json={"title": "Limits note", "course_id": course_id, "node_id": chapter},
        )
        client.post(
            f"/api/v1/courses/{course_id}/concepts/commit",
            json={
                "concepts": [{"name": "limits", "description": None, "aliases": []}],
                "links": [],
                "nodes": [],
            },
        )
        graph = client.get(f"/api/v1/courses/{course_id}/concepts").json()
        concept_id = int(graph["concepts"][0]["id"])
        client.post(f"/api/v1/nodes/{chapter}/concepts", json={"concept_id": concept_id})
    return {
        "tmp": tmp_path,
        "course_id": course_id,
        "root": root,
        "chapter": chapter,
        "material_id": material_id,
        "concept_id": concept_id,
    }


def _server_params(tmp: Path) -> StdioServerParameters:
    env = dict(os.environ)
    env["SA_DATA_DIR"] = str(tmp)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "studyassistant", "mcp"],
        cwd=str(Path(__file__).resolve().parent.parent),
        env=env,
    )


def _structured(result: Any) -> Any:
    content = result.content[0].text if result.content else ""
    return json.loads(content)


def test_mcp_server_lists_courses_and_scoped_resources(seeded: dict[str, Any]) -> None:
    async def scenario() -> None:
        async with (
            stdio_client(_server_params(seeded["tmp"])) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {
                "list_courses",
                "get_node_overview",
                "get_node_materials",
                "get_node_concepts",
                "get_node_exercises",
                "get_node_quizzes",
                "get_node_notes",
                "get_node_context",
            }

            courses = _structured(await session.call_tool("list_courses", {}))[
                "courses"
            ]
            assert [entry["title"] for entry in courses] == ["Calc"]
            assert courses[0]["root_node_id"] == seeded["root"]

            overview = _structured(
                await session.call_tool(
                    "get_node_overview", {"node_id": seeded["chapter"]}
                )
            )
            assert overview["node"]["title"] == "Limits"
            assert [entry["title"] for entry in overview["node"]["breadcrumb"]] == [
                "Calc",
                "Limits",
            ]
            assert overview["counts"]["notes"] == {"direct": 1, "with_children": 1}

            materials = _structured(
                await session.call_tool(
                    "get_node_materials", {"node_id": seeded["chapter"]}
                )
            )
            assert [m["material_id"] for m in materials["direct"]] == [
                seeded["material_id"]
            ]
            root_materials = _structured(
                await session.call_tool(
                    "get_node_materials",
                    {"node_id": seeded["root"], "include_children": False},
                )
            )
            assert root_materials["direct"] == []

            concepts = _structured(
                await session.call_tool("get_node_concepts", {"node_id": seeded["root"]})
            )["concepts"]
            assert [entry["name"] for entry in concepts] == ["limits"]
            assert concepts[0]["node_ids"] == [seeded["chapter"]]
            assert concepts[0]["direct"] is False

            quizzes = _structured(
                await session.call_tool("get_node_quizzes", {"node_id": seeded["root"]})
            )["quizzes"]
            assert len(quizzes) == 1
            assert quizzes[0]["question_count"] == 1
            assert quizzes[0]["node_id"] == seeded["root"]

            notes = _structured(
                await session.call_tool(
                    "get_node_notes", {"node_id": seeded["chapter"]}
                )
            )["notes"]
            assert [entry["title"] for entry in notes] == ["Limits note"]

            exercises = _structured(
                await session.call_tool(
                    "get_node_exercises", {"node_id": seeded["root"]}
                )
            )["exercises"]
            assert exercises == []

            missing = _structured(
                await session.call_tool("get_node_overview", {"node_id": 99999})
            )
            assert missing == {"error": "node not found"}

            context = _structured(
                await session.call_tool(
                    "get_node_context", {"node_id": seeded["chapter"], "query": "limits"}
                )
            )
            assert context["node_id"] == seeded["chapter"]
            assert context["course_id"] == seeded["course_id"]
            stats = context["stats"]
            assert [entry["id"] for entry in stats["materials"]] == [seeded["material_id"]]
            assert context["rendered"]
            assert "[M" in context["rendered"] or "No excerpts" in context["rendered"]

            bad_scope = _structured(
                await session.call_tool(
                    "get_node_context", {"node_id": seeded["chapter"], "scope": "galaxy"}
                )
            )
            assert "error" in bad_scope

    anyio.run(scenario)


def test_mcp_server_read_only_by_construction(seeded: dict[str, Any]) -> None:
    async def scenario() -> None:
        async with (
            stdio_client(_server_params(seeded["tmp"])) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                assert "write" not in tool.name
                assert not tool.name.startswith("create")
                assert not tool.name.startswith("delete")
                assert not tool.name.startswith("update")

    anyio.run(scenario)
    engine = make_engine(seeded["tmp"] / "app.db")
    factory = make_session_factory(engine)
    with factory() as session:
        assert len(list(session.scalars(select(Note)))) == 1
    engine.dispose()
