import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.ai.gateway import Message
from app.core.config import Settings
from app.main import create_app


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


@fixture
def client() -> Iterator[TestClient]:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-p9cd-"))
    app = create_app(Settings(data_dir=tmp, log_level="WARNING"))
    with TestClient(app) as test_client:
        yield test_client


def upload_txt(client: TestClient, filename: str, course_id: int, content: bytes) -> int:
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, content, "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    material_id = int(upload.json()["material"]["id"])
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )
    return material_id


def make_node(client: TestClient, course_id: int, parent_id: int, title: str) -> int:
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": parent_id, "title": title},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def root_node(client: TestClient, course_id: int) -> int:
    return int(client.get(f"/api/v1/courses/{course_id}/tree").json()[0]["id"])


def test_node_concept_coverage_management(client: TestClient) -> None:
    course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
    root = root_node(client, course_id)
    chapter = make_node(client, course_id, root, "Ch")

    committed = client.post(
        f"/api/v1/courses/{course_id}/concepts/commit",
        json={
            "concepts": [{"name": "chain rule", "description": None, "aliases": []}],
            "links": [],
            "nodes": [],
        },
    )
    assert committed.status_code == 200
    graph = client.get(f"/api/v1/courses/{course_id}/concepts").json()
    concept_id = int(graph["concepts"][0]["id"])

    added = client.post(f"/api/v1/nodes/{chapter}/concepts", json={"concept_id": concept_id})
    assert added.status_code == 201, added.text
    again = client.post(f"/api/v1/nodes/{chapter}/concepts", json={"concept_id": concept_id})
    assert again.status_code == 201

    workspace = client.get(f"/api/v1/nodes/{chapter}/workspace").json()
    assert workspace["concepts"] == [
        {"id": concept_id, "name": "chain rule", "direct": True, "node_ids": [chapter]}
    ]
    root_ws = client.get(f"/api/v1/nodes/{root}/workspace").json()
    assert root_ws["concepts"][0]["direct"] is False
    assert root_ws["concepts"][0]["node_ids"] == [chapter]

    foreign = int(client.post("/api/v1/courses", json={"title": "D"}).json()["id"])
    committed_foreign = client.post(
        f"/api/v1/courses/{foreign}/concepts/commit",
        json={
            "concepts": [{"name": "other", "description": None, "aliases": []}],
            "links": [],
            "nodes": [],
        },
    )
    assert committed_foreign.status_code == 200
    foreign_concept = int(
        client.get(f"/api/v1/courses/{foreign}/concepts").json()["concepts"][0]["id"]
    )
    cross = client.post(
        f"/api/v1/nodes/{chapter}/concepts", json={"concept_id": foreign_concept}
    )
    assert cross.status_code == 422

    removed = client.delete(f"/api/v1/nodes/{chapter}/concepts/{concept_id}")
    assert removed.status_code == 204
    workspace = client.get(f"/api/v1/nodes/{chapter}/workspace").json()
    assert workspace["concepts"] == []


def test_chat_session_list_filters_by_node(client: TestClient) -> None:
    course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
    root = root_node(client, course_id)
    chapter = make_node(client, course_id, root, "Ch")

    bound = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "node_id": chapter, "title": "bound"},
    ).json()
    loose = client.post(
        "/api/v1/chat/sessions", json={"course_id": course_id, "title": "loose"}
    ).json()
    client.post("/api/v1/chat/sessions", json={"title": "unbound"})

    at_chapter = client.get("/api/v1/chat/sessions", params={"node_id": chapter}).json()
    assert [entry["id"] for entry in at_chapter] == [bound["id"]]
    at_root = client.get("/api/v1/chat/sessions", params={"node_id": root}).json()
    assert [entry["id"] for entry in at_root] == [loose["id"]]


CAQ: dict[str, Any] = {
    "$schema": "caq/v1",
    "title": "probe",
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


def test_scoped_chat_retrieval_narrows_to_subtree(tmp_path: Path) -> None:
    gateway_calls: list[list[Any]] = []

    class ProbeGateway(ScriptedGateway):
        def generate(
            self,
            task: str,
            messages: list[Message],
            model: Any = None,
            course_id: int | None = None,
        ) -> str:
            gateway_calls.append(messages)
            return super().generate(task, messages, model)

    gateway = ProbeGateway(["The antiderivative is $x^3/3 + C$ — see [1]."])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
        root = root_node(client, course_id)
        chapter = make_node(client, course_id, root, "Integrals")

        integrals_id = upload_txt(
            client, "integrals.txt", course_id, b"antiderivative of x squared is x cubed over three"
        )
        upload_txt(
            client, "dice.txt", course_id, b"antiderivative antiderivative rolling a fair die"
        )
        client.post(f"/api/v1/nodes/{chapter}/materials", json={"material_id": integrals_id})

        session = client.post(
            "/api/v1/chat/sessions",
            json={"course_id": course_id, "node_id": chapter, "title": "scoped"},
        ).json()
        sent = client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "antiderivative"},
        )
        assert sent.status_code in (200, 202), sent.text
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            messages = client.get(
                f"/api/v1/chat/sessions/{session['id']}/messages"
            ).json()
            if messages and messages[-1]["role"] == "assistant":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("assistant never answered")

    prompt_text = " ".join(
        message.content
        for call in gateway_calls
        for message in call
        if isinstance(message.content, str)
    )
    assert "(integrals)" in prompt_text
    assert "(dice)" not in prompt_text
