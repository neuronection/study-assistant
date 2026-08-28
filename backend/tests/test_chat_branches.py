import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.core.config import Settings
from app.main import create_app


class Harness:
    def __init__(
        self, client: TestClient, gateway: ScriptedGateway, session_id: int
    ) -> None:
        self.client = client
        self.gateway = gateway
        self.session_id = session_id


@contextmanager
def harness(tmp_path: Path, responses: list[str]) -> Iterator[Harness]:
    gateway = ScriptedGateway(list(responses))
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        session_id = int(client.post("/api/v1/chat/sessions", json={}).json()["id"])
        yield Harness(client, gateway, session_id)


def get_messages(harness: Harness) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = harness.client.get(
        f"/api/v1/chat/sessions/{harness.session_id}/messages"
    ).json()
    return messages


def wait_until(
    harness: Harness, predicate: Callable[[list[dict[str, Any]]], bool],
    timeout: float = 5.0,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages = get_messages(harness)
        if messages and predicate(messages):
            return messages
        time.sleep(0.05)
    raise AssertionError("condition never met")


def wait_for_assistant(harness: Harness, timeout: float = 5.0) -> list[dict[str, Any]]:
    return wait_until(harness, lambda messages: messages[-1]["role"] == "assistant")


def send(harness: Harness, content: str) -> None:
    response = harness.client.post(
        f"/api/v1/chat/sessions/{harness.session_id}/messages",
        json={"content": content},
    )
    assert response.status_code == 200


def first_user_id(messages: list[dict[str, Any]]) -> int:
    return int(next(m["id"] for m in messages if m["role"] == "user"))


def test_send_chains_messages_to_active_tip(tmp_path: Path) -> None:
    with harness(tmp_path, ["A1", "A2"]) as h:
        send(h, "q1")
        messages = wait_for_assistant(h)
        assert messages[0]["parent_id"] is None

        send(h, "q2")
        messages = wait_for_assistant(h)
        assert [m["role"] for m in messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert messages[2]["parent_id"] == messages[1]["id"]
        assert messages[3]["parent_id"] == messages[2]["id"]
        for message in messages:
            assert message["variant_count"] == 1


def test_edit_creates_sibling_branch_and_answers_it(tmp_path: Path) -> None:
    with harness(tmp_path, ["answer one", "answer two"]) as h:
        send(h, "q1")
        original = wait_for_assistant(h)
        original_user_id = first_user_id(original)

        response = h.client.post(
            f"/api/v1/chat/messages/{original_user_id}/edit",
            json={"content": "q1 edited"},
        )
        assert response.status_code == 200
        branched = wait_for_assistant(h)

        assert [m["markdown"] for m in branched] == ["q1 edited", "answer two"]
        assert branched[0]["variant_count"] == 2
        assert branched[0]["variant_index"] == 2
        assert branched[0]["parent_id"] is None

        last_call = h.gateway.calls[-1]
        assert len(last_call) == 2
        assert str(last_call[-1].content).startswith("Question: q1 edited")

        switch = h.client.post(f"/api/v1/chat/messages/{original_user_id}/select")
        assert switch.status_code == 200
        restored = get_messages(h)
        assert restored[0]["markdown"] == "q1"
        assert restored[0]["variant_index"] == 1
        assert restored[0]["variant_count"] == 2


def test_regenerate_adds_assistant_variant(tmp_path: Path) -> None:
    with harness(tmp_path, ["v1", "v2", "post-regen"]) as h:
        send(h, "q")
        messages = wait_for_assistant(h)
        user_id = first_user_id(messages)
        v1_id = messages[1]["id"]

        response = h.client.post(f"/api/v1/chat/messages/{user_id}/regenerate")
        assert response.status_code == 200
        regenerated = wait_until(
            h,
            lambda ms: ms[-1]["role"] == "assistant"
            and ms[-1]["variant_count"] == 2,
        )

        assert regenerated[-1]["markdown"] == "v2"
        assert regenerated[-1]["variant_count"] == 2
        assert regenerated[-1]["variant_index"] == 2
        assert regenerated[-1]["parent_id"] == user_id

        last_call = h.gateway.calls[-1]
        assert len(last_call) == 2
        assert str(last_call[-1].content).startswith("Question: q")

        follow_up = h.client.post(
            f"/api/v1/chat/sessions/{h.session_id}/messages",
            json={"content": "and more"},
        )
        assert follow_up.status_code == 200
        final = wait_until(h, lambda ms: len(ms) == 4)
        assert final[-2]["parent_id"] == regenerated[-1]["id"]

        h.client.post(f"/api/v1/chat/messages/{v1_id}/select")
        restored = get_messages(h)
        assert restored[-1]["id"] == v1_id
        assert restored[-1]["variant_index"] == 1


def test_select_hidden_subtree_restores_later_turns(tmp_path: Path) -> None:
    with harness(tmp_path, ["a1", "a2-edited", "deep"]) as h:
        send(h, "q")
        original = wait_for_assistant(h)
        original_user_id = first_user_id(original)

        response = h.client.post(
            f"/api/v1/chat/messages/{original_user_id}/edit",
            json={"content": "branch q"},
        )
        assert response.status_code == 200
        send(h, "under branch")
        under_branch = wait_until(h, lambda ms: len(ms) == 4)
        assert under_branch[3]["markdown"] == "deep"

        selection = h.client.post(
            f"/api/v1/chat/messages/{original_user_id}/select"
        )
        assert selection.status_code == 200
        restored = get_messages(h)
        assert len(restored) == 2
        assert restored[-1]["markdown"] == "a1"
        assert restored[-1]["variant_count"] == 1


def test_edit_rejects_assistant_message(tmp_path: Path) -> None:
    with harness(tmp_path, ["resp"]) as h:
        send(h, "q")
        messages = wait_for_assistant(h)
        assistant_id = messages[1]["id"]

        assert (
            h.client.post(
                f"/api/v1/chat/messages/{assistant_id}/edit",
                json={"content": "x"},
            ).status_code
            == 422
        )


def test_branch_tree_endpoint_exposes_full_tree(tmp_path: Path) -> None:
    with harness(tmp_path, ["answer one", "answer two"]) as h:
        send(h, "q1")
        original = wait_for_assistant(h)
        original_user_id = first_user_id(original)

        response = h.client.post(
            f"/api/v1/chat/messages/{original_user_id}/edit",
            json={"content": "q1 edited"},
        )
        assert response.status_code == 200
        wait_for_assistant(h)

        tree = h.client.get(f"/api/v1/chat/sessions/{h.session_id}/tree")
        assert tree.status_code == 200
        payload = tree.json()
        nodes = {node["id"]: node for node in payload["nodes"]}
        assert len(nodes) == 4

        assert payload["active_root_id"] != original_user_id
        branched_root_id = payload["active_root_id"]
        assert nodes[branched_root_id]["parent_id"] is None
        assert len(nodes[branched_root_id]["children"]) == 1

        assert nodes[original_user_id]["parent_id"] is None
        root_ids = sorted(
            node["id"] for node in payload["nodes"] if node["parent_id"] is None
        )
        assert root_ids == sorted([original_user_id, branched_root_id])

        original_answer = nodes[original[1]["id"]]
        assert original_answer["parent_id"] == original_user_id
        assert nodes[original_user_id]["children"] == [original[1]["id"]]
        assert all(node["excerpt"] for node in nodes.values())
