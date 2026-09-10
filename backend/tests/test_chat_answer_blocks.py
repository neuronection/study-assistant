import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

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
def client(tmp_path: Path) -> Iterator[tuple[TestClient, ScriptedGateway]]:
    gateway = ScriptedGateway([])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway


def test_chat_answer_chart_fence_becomes_chart_block(
    client: tuple[TestClient, ScriptedGateway],
) -> None:
    test_client, gateway = client
    with test_client:
        gateway.responses.append('The graph:\n\n```chart\n{"data": [{"y": [1, 2]}]}\n```')
        chat_session = test_client.post("/api/v1/chat/sessions", json={}).json()
        test_client.post(
            f"/api/v1/chat/sessions/{chat_session['id']}/messages",
            json={"content": "plot it"},
        )
        messages = wait_for_assistant(test_client, chat_session["id"])
        assistant = messages[-1]
        chart_blocks = [block for block in assistant["blocks"] if block["type"] == "chart"]
        assert len(chart_blocks) == 1
        assert chart_blocks[0]["plotly"] == {"data": [{"y": [1, 2]}]}
        assert assistant["markdown"].strip() == "The graph:"


def test_chat_answer_widget_fence_becomes_widget_block(
    client: tuple[TestClient, ScriptedGateway],
) -> None:
    test_client, gateway = client
    with test_client:
        gateway.responses.append(
            'Which rule?\n\n```widget\n{"widget": "checklist", "id": "w1", '
            '"props": {"prompt": "pick", "items": ["factor", "chain rule"]}}\n```'
        )
        chat_session = test_client.post("/api/v1/chat/sessions", json={}).json()
        test_client.post(
            f"/api/v1/chat/sessions/{chat_session['id']}/messages",
            json={"content": "what rule?"},
        )
        messages = wait_for_assistant(test_client, chat_session["id"])
        assistant = messages[-1]
        widget_blocks = [block for block in assistant["blocks"] if block["type"] == "widget"]
        assert len(widget_blocks) == 1
        assert widget_blocks[0]["widget"] == "checklist"
        assert widget_blocks[0]["id"] == "w1"


def test_follow_up_turn_after_widget_first_answer(
    client: tuple[TestClient, ScriptedGateway],
) -> None:
    test_client, gateway = client
    with test_client:
        gateway.responses.append(
            '```widget\n{"widget": "slider", "id": "w1", '
            '"props": {"prompt": "rate it", "max": 5}}\n```'
        )
        chat_session = test_client.post("/api/v1/chat/sessions", json={}).json()
        test_client.post(
            f"/api/v1/chat/sessions/{chat_session['id']}/messages",
            json={"content": "show me a component"},
        )
        first = wait_for_assistant(test_client, chat_session["id"])
        assert any(block["type"] == "widget" for block in first[-1]["blocks"])

        gateway.responses.append("You're welcome!")
        test_client.post(
            f"/api/v1/chat/sessions/{chat_session['id']}/messages",
            json={"content": "thanks"},
        )
        second = wait_for_assistant(test_client, chat_session["id"])
        assert second[-1]["markdown"].strip() == "You're welcome!"
