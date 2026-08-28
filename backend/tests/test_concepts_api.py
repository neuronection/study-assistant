import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel, TaskUnassigned
from app.core.config import Settings
from app.main import create_app

EXTRACTION_JSON = json.dumps(
    {
        "concepts": [
            {
                "name": "Chain Rule",
                "description": "Derivative of composites",
                "aliases": ["chain-rule"],
            },
            {"name": "limits", "description": None, "aliases": []},
            {"name": "  Limits  ", "description": "duplicate gets dropped", "aliases": []},
            {"name": "Bogus Concept That Will Not Be Linked", "description": None, "aliases": []},
        ],
        "links": [
            {"from": "limits", "to": "Chain Rule", "relation": "prereq-of"},
            {"from": "limits", "to": "Chain Rule", "relation": "prereq-of"},
            {"from": "unknown", "to": "limits", "relation": "related-to"},
            {"from": "limits", "to": "limits", "relation": "part-of"},
            {"from": "limits", "to": "Chain Rule", "relation": "nonsense"},
        ],
        "nodes": [
            {"node_title": "Chain rule", "concepts": ["Chain Rule", "limits", "ghost"]},
            {"node_title": "Does Not Exist", "concepts": ["limits"]},
        ],
    }
)


class FakeConceptsGateway(LLMGateway):
    def __init__(self, response: str) -> None:
        super().__init__(session_factory=None)
        self.response = response
        self.calls: list[Message] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        raise TaskUnassigned(task)

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.calls.extend(messages)
        return self.response


@pytest.fixture
def concepts_client() -> Iterator[tuple[TestClient, list[Message]]]:
    gateway = FakeConceptsGateway(EXTRACTION_JSON)
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-concepts-"))
    app = create_app(Settings(data_dir=tmp, log_level="WARNING"), gateway=gateway)
    with TestClient(app) as client:
        yield client, gateway.calls


def test_concepts_extract_validate_commit_and_graph(
    concepts_client: tuple[TestClient, list[Message]],
) -> None:
    client, _calls = concepts_client
    course = client.post("/api/v1/courses", json={"title": "Calc"}).json()

    draft = client.post(f"/api/v1/courses/{course['id']}/concepts/extract")
    assert draft.status_code == 422
    assert "no ready materials" in draft.json()["detail"]

    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course["id"]},
        files={"file": ("m.txt", b"chain rule and limits content", "text/plain")},
    ).json()
    import time

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/materials/{upload['material']['id']}").json()[
            "material"
        ]["status"]
        if status == "ready":
            break
        time.sleep(0.05)

    root = client.get(f"/api/v1/courses/{course['id']}/tree").json()[0]
    chapter = client.post(
        f"/api/v1/courses/{course['id']}/nodes",
        json={"course_id": course["id"], "parent_id": root["id"], "title": "Ch"},
    ).json()
    section = client.post(
        f"/api/v1/courses/{course['id']}/nodes",
        json={"course_id": course["id"], "parent_id": chapter["id"], "title": "Chain rule"},
    ).json()

    draft = client.post(f"/api/v1/courses/{course['id']}/concepts/extract").json()
    names = [entry["name"] for entry in draft["concepts"]]
    assert names == ["chain rule", "limits", "bogus concept that will not be linked"]
    assert draft["links"] == [
        {"from": "limits", "to": "chain rule", "relation": "prereq-of"}
    ]
    assert draft["nodes"] == [
        {"node_title": "Chain rule", "concepts": ["chain rule", "limits"]}
    ]

    committed = client.post(
        f"/api/v1/courses/{course['id']}/concepts/commit",
        json={
            "concepts": draft["concepts"],
            "links": draft["links"],
            "nodes": draft["nodes"],
        },
    )
    assert committed.status_code == 200
    assert committed.json()["created"] == 3

    again = client.post(
        f"/api/v1/courses/{course['id']}/concepts/commit",
        json={
            "concepts": draft["concepts"],
            "links": draft["links"],
            "nodes": draft["nodes"],
        },
    ).json()
    assert again["created"] == 0

    graph = client.get(f"/api/v1/courses/{course['id']}/concepts").json()
    by_name = {entry["name"]: entry for entry in graph["concepts"]}
    assert set(by_name) == {
        "chain rule",
        "limits",
        "bogus concept that will not be linked",
    }
    assert by_name["chain rule"]["nodes"] == [
        {"node_id": section["id"], "node_title": "Chain rule"}
    ]
    assert graph["links"] == [
        {"from": "limits", "to": "chain rule", "relation": "prereq-of"}
    ]

    missing = client.get("/api/v1/courses/99999/concepts")
    assert missing.status_code == 404
