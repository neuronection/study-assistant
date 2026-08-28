import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.core.config import Settings
from app.domain.models import ChatMessage
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


def insert_assistant_message(
    app: FastAPI, session_id: int, state: dict[str, Any] | None
) -> int:
    db = app.state.session_factory()
    try:
        message = ChatMessage(
            session_id=session_id,
            role="assistant",
            blocks=[{"type": "text", "md": "hi"}],
            state=state,
        )
        db.add(message)
        db.commit()
        return message.id
    finally:
        db.close()


def test_patch_message_state_reduces_deltas(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        chat_session = test_client.post("/api/v1/chat/sessions", json={}).json()
        message_id = insert_assistant_message(app, chat_session["id"], None)
        first = test_client.patch(
            f"/api/v1/chat/messages/{message_id}/state",
            json={"delta": [{"op": "add", "path": "/w1", "value": {"checked": []}}]},
        )
        assert first.status_code == 200
        assert first.json()["state"] == {"w1": {"checked": []}}
        second = test_client.patch(
            f"/api/v1/chat/messages/{message_id}/state",
            json={"delta": [{"op": "replace", "path": "/w1/checked", "value": ["factor"]}]},
        )
        assert second.status_code == 200
        assert second.json()["state"] == {"w1": {"checked": ["factor"]}}
        db = app.state.session_factory()
        try:
            message = db.get(ChatMessage, message_id)
            assert message is not None
            assert message.state == {"w1": {"checked": ["factor"]}}
        finally:
            db.close()


def test_patch_message_state_404(client: tuple[TestClient, ScriptedGateway, FastAPI]) -> None:
    test_client, _gateway, _app = client
    with test_client:
        response = test_client.patch(
            "/api/v1/chat/messages/999999/state",
            json={"delta": [{"op": "add", "path": "/a", "value": 1}]},
        )
        assert response.status_code == 404


def test_patch_message_state_rejects_bad_patch(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        chat_session = test_client.post("/api/v1/chat/sessions", json={}).json()
        message_id = insert_assistant_message(app, chat_session["id"], None)
        response = test_client.patch(
            f"/api/v1/chat/messages/{message_id}/state",
            json={"delta": [{"op": "bogus", "path": "/a", "value": 1}]},
        )
        assert response.status_code == 422


def test_patch_message_state_size_guard(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        chat_session = test_client.post("/api/v1/chat/sessions", json={}).json()
        message_id = insert_assistant_message(app, chat_session["id"], None)
        response = test_client.patch(
            f"/api/v1/chat/messages/{message_id}/state",
            json={"delta": [{"op": "add", "path": "/w", "value": "x" * 100_001}]},
        )
        assert response.status_code == 422


def test_state_tool_reads_prior_widget_state(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        chat_session = test_client.post("/api/v1/chat/sessions", json={}).json()
        insert_assistant_message(app, chat_session["id"], {"w1": {"checked": ["factor"]}})
        gateway.responses.append("STATE w1")
        gateway.responses.append("You checked factor.")
        test_client.post(
            f"/api/v1/chat/sessions/{chat_session['id']}/messages",
            json={"content": "what did I check?"},
        )
        messages = wait_for_assistant(test_client, chat_session["id"])
        assistant = messages[-1]
        assert len(gateway.calls) == 2
        second_prompt = "\n".join(str(message.content) for message in gateway.calls[-1])
        assert '"checked"' in second_prompt
        assert "factor" in second_prompt
        assert "STATE" not in assistant["markdown"]


def test_state_tool_unknown_widget(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        chat_session = test_client.post("/api/v1/chat/sessions", json={}).json()
        gateway.responses.append("STATE w9")
        gateway.responses.append("No state found.")
        test_client.post(
            f"/api/v1/chat/sessions/{chat_session['id']}/messages",
            json={"content": "hello"},
        )
        messages = wait_for_assistant(test_client, chat_session["id"])
        assistant = messages[-1]
        second_prompt = "\n".join(str(message.content) for message in gateway.calls[-1])
        assert "no state recorded" in second_prompt
        assert "STATE" not in assistant["markdown"]
