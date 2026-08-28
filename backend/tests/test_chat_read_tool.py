import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, add_material, make_course

from app.ai.tools import CHAT_TOOL_CATALOG, CHAT_TOOL_DOC, build_tool_doc
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


def make_node(client: TestClient, course_id: int, title: str) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = int(tree[0]["id"])
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": title},
    )
    return int(created.json()["id"])


def link_material(client: TestClient, node_id: int, material_id: int) -> None:
    response = client.post(
        f"/api/v1/nodes/{node_id}/materials", json={"material_id": material_id}
    )
    assert response.status_code < 400, response.text


def test_tool_doc_generated_from_catalog_single_source() -> None:
    doc = build_tool_doc(CHAT_TOOL_CATALOG)
    assert doc == CHAT_TOOL_DOC
    for tool in CHAT_TOOL_CATALOG:
        assert tool["name"] in doc
        assert tool["example"] in doc
    assert "READ" in CHAT_TOOL_DOC
    assert "CALC" in CHAT_TOOL_DOC
    assert "SYMPY" in CHAT_TOOL_DOC


def test_tools_endpoint_lists_chat_tools(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        body = test_client.get("/api/v1/ai/tools").json()
        assert [tool["name"] for tool in body["tools"]] == [
            "CALC",
            "SYMPY",
            "READ",
            "STATE",
            "PLOT",
            "COURSES",
            "NODE_OVERVIEW",
            "NODE_QUIZZES",
            "NODE_EXERCISES",
            "NODE_NOTES",
        ]


def test_read_fetches_material_content_model_only(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client,
            "deep.txt",
            "The u-substitution recipe: pick u, rewrite the integral, adjust du.",
            course_id,
        )
        gateway.responses.append(f"READ M{material_id}")
        gateway.responses.append(f"Done — the recipe is in [M{material_id}] [1].")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "explain u-substitution"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert len(gateway.calls) == 2
        second_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "u-substitution recipe" in second_prompt
        assert "READ" in second_prompt
        assert assistant["reads"]
        assert assistant["reads"][0]["ref"] == f"M{material_id}"
        assert assistant["reads"][0]["chars"] > 0
        assert "u-substitution recipe" not in assistant["markdown"]
        assert "READ M" not in assistant["markdown"]
        system_prompt = str(gateway.calls[0][0].content)
        assert "READ" in system_prompt


def test_read_tool_call_persisted_without_content(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client,
            "deep.txt",
            "The u-substitution recipe: pick u, rewrite the integral, adjust du.",
            course_id,
        )
        gateway.responses.append(f"READ M{material_id}")
        gateway.responses.append("Done — the recipe is in [1].")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "explain u-substitution"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert len(assistant["tool_calls"]) == 1
        call = assistant["tool_calls"][0]
        assert call["name"] == "READ"
        assert call["argument"] == f"M{material_id}"
        assert call["phase"] == "read"
        assert "read " in call["result"] and "chars" in call["result"]
        assert "u-substitution recipe" not in call["result"]
        assert "u-substitution recipe" not in call.get("title", "")


def test_read_unknown_handle_returns_error_not_content(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "x.txt", "short body", course_id)
        gateway.responses.append("READ M999")
        gateway.responses.append("I only have what is offered [1].")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "hello"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        second_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "error: M999 is not offered" in second_prompt
        assert assistant["reads"] == []
        assert "error:" not in assistant["markdown"]


def test_read_budget_capped_at_three(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        ids = [
            add_material(test_client, f"m{i}.txt", f"body number {i}", course_id)
            for i in range(4)
        ]
        for i in range(4):
            gateway.responses.append(f"READ M{ids[i]}")
        gateway.responses.append("Enough — see [1].")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "go"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert len(assistant["reads"]) == 3
        last_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "budget for this turn is spent" in last_prompt


def test_manifest_respects_node_scope_and_context_endpoint(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        inside = add_material(test_client, "inside.txt", "integration by parts", course_id)
        outside = add_material(test_client, "outside.txt", "unrelated polar bears", course_id)
        node_id = make_node(test_client, course_id, "Techniques")
        link_material(test_client, node_id, inside)
        gateway.responses.append("See [1].")
        session = test_client.post(
            "/api/v1/chat/sessions",
            json={"course_id": course_id, "node_id": node_id},
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "integration by parts"},
        )
        wait_for_assistant(test_client, session["id"])
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert f"M{inside} = " in prompt
        assert f"M{outside}" not in prompt
        context = test_client.get(
            f"/api/v1/chat/sessions/{session['id']}/context"
        ).json()
        assert context["node"] == {"id": node_id, "title": "Techniques"}
        refs = {entry["ref"] for entry in context["registry"]}
        assert f"M{inside}" in refs
        assert f"M{outside}" not in refs
        assert context["course_id"] == course_id


def test_math_tools_share_turn_with_read(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "calc.txt", "basic calculus body", course_id)
        gateway.responses.append("CALC 2**10")
        gateway.responses.append(f"READ M{material_id}")
        gateway.responses.append("SYMPY diff x**2")
        gateway.responses.append("All verified [1].")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "compute things"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert len(gateway.calls) == 4
        assert assistant["reads"]
        final_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "CALC 2**10 -> 1024" in final_prompt
        assert "basic calculus body" in final_prompt
        assert "SYMPY diff x**2 -> 2*x" in final_prompt


def test_manifest_includes_summary_when_available(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "s.txt", "content words", course_id)
        stored = app.state.session_factory()
        from sqlalchemy import select

        from app.domain.models import MaterialIndexCard

        card = stored.scalars(
            select(MaterialIndexCard).where(MaterialIndexCard.material_id == material_id)
        ).first()
        if card is None:
            card = MaterialIndexCard(material_id=material_id)
            stored.add(card)
        card.summary = "Card summary of the material"
        card.topics = ["u-sub"]
        stored.commit()
        stored.close()
        gateway.responses.append("See [1].")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "hello"},
        )
        wait_for_assistant(test_client, session["id"])
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert "Card summary of the material" in prompt
