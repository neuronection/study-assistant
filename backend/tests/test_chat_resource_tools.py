import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, make_course

from app.core.config import Settings
from app.main import create_app


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


@fixture
def client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, ScriptedGateway, FastAPI]]:
    gateway = ScriptedGateway([])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway, app


def make_node(client: TestClient, course_id: int, title: str) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = int(tree[0]["id"])
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": title},
    )
    return int(created.json()["id"])


def test_courses_tool_lists_courses(client: tuple[TestClient, ScriptedGateway, FastAPI]) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client, "Calculus")
        gateway.responses.append("COURSES")
        gateway.responses.append("Here are your courses.")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "list my courses"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        courses_call = next(
            tc for tc in assistant["tool_calls"] if tc["name"] == "COURSES"
        )
        assert "Calculus" in courses_call["result"]
        assert courses_call["status"] == "done"
        assert "COURSES" not in assistant["markdown"]


def test_node_tools_resolve_here_and_handle(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client, "Physics")
        node_id = make_node(test_client, course_id, "Kinematics")
        test_client.post(
            "/api/v1/notes",
            json={
                "title": "Velocity notes",
                "body_md": "v = dx/dt",
                "course_id": course_id,
                "node_id": node_id,
            },
        )
        gateway.responses.append(f"NODE_NOTES here\nNODE_OVERVIEW T{node_id}")
        gateway.responses.append("Summarized.")
        session = test_client.post(
            "/api/v1/chat/sessions",
            json={"course_id": course_id, "node_id": node_id},
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "what notes do I have here"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        names = {tc["name"] for tc in assistant["tool_calls"]}
        assert "NODE_NOTES" in names
        assert "NODE_OVERVIEW" in names
        notes_call = next(tc for tc in assistant["tool_calls"] if tc["name"] == "NODE_NOTES")
        assert "Velocity notes" in notes_call["result"]


def test_unknown_node_handle_reports_error(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client, "Biology")
        gateway.responses.append("NODE_OVERVIEW T999")
        gateway.responses.append("I could not look that up.")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "overview of node T999"},
        )
        wait_for_assistant(test_client, session["id"])
        second_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "error: need a node handle" in second_prompt


def test_resource_tool_budget_is_capped(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client, "Chemistry")
        gateway.responses.append("\n".join(["COURSES"] * 7))
        gateway.responses.append("Done.")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "list courses many times"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        courses_calls = [tc for tc in assistant["tool_calls"] if tc["name"] == "COURSES"]
        assert len(courses_calls) == 5
        last_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "resource tool budget for this turn is spent" in last_prompt
