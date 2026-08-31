import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel, TaskUnassigned
from app.core.config import Settings
from app.main import create_app

OUTLINE_JSON = json.dumps(
    {
        "chapters": [
            {
                "title": "Limits",
                "summary": "Foundation of calculus",
                "sections": [
                    {
                        "title": "Limit intuition",
                        "objectives": ["Explain limits informally"],
                        "material_ids": [1, 2],
                        "rationale": "Both cover introductory limits",
                        "confidence": 0.9,
                    },
                    {
                        "title": "Continuity",
                        "objectives": [],
                        "material_ids": [3],
                        "rationale": "Continuity section",
                        "confidence": 0.7,
                    },
                ],
            },
            {
                "title": "Derivatives",
                "summary": None,
                "sections": [
                    {
                        "title": "The derivative",
                        "objectives": ["Compute derivatives"],
                        "material_ids": [999],
                        "rationale": "bogus id gets dropped",
                        "confidence": 2.0,
                    }
                ],
            },
        ]
    }
)


class FakeOutlineGateway(LLMGateway):
    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        super().__init__(session_factory=None)
        self.response = response
        self.error = error

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
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


@pytest.fixture
def course_client() -> Iterator[TestClient]:
    gateway = FakeOutlineGateway(response=OUTLINE_JSON)
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-courses-"))
    settings = Settings(data_dir=tmp, log_level="WARNING")
    app = create_app(settings, gateway=gateway)
    with TestClient(app) as client:
        yield client


def add_material(client: TestClient, filename: str, course_id: int) -> int:
    body = f"calculus notes {filename} about limits and continuity".encode()
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, body, "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    material_id: int = upload.json()["material"]["id"]
    import time

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        if status == "ready":
            return material_id
        assert status != "failed"
        time.sleep(0.05)
    raise AssertionError("material never became ready")


def test_course_crud(course_client: TestClient) -> None:
    created = course_client.post(
        "/api/v1/courses", json={"title": "Calculus I", "subject": "mathematics"}
    )
    assert created.status_code == 201
    course_id = created.json()["id"]

    listed = course_client.get("/api/v1/courses").json()
    assert [course["title"] for course in listed] == ["Calculus I"]
    assert listed[0]["material_count"] == 0

    renamed = course_client.patch(
        f"/api/v1/courses/{course_id}", json={"title": "Calculus II"}
    )
    assert renamed.json()["title"] == "Calculus II"

    empty_title = course_client.patch(f"/api/v1/courses/{course_id}", json={"title": "  "})
    assert empty_title.status_code == 422

    refused = course_client.delete(f"/api/v1/courses/{course_id}")
    assert refused.status_code == 409
    deleted = course_client.delete(
        f"/api/v1/courses/{course_id}", params={"confirmed_backup": True}
    )
    assert deleted.status_code == 200
    assert course_client.get("/api/v1/courses").json() == []


def test_course_update_syncs_root_node(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Calculus I"}).json()["id"]
    root_before = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    assert root_before["title"] == "Calculus I"
    assert root_before["summary"] is None

    updated = course_client.patch(
        f"/api/v1/courses/{course_id}",
        json={"title": "Calculus II", "description": "Single-variable calculus"},
    )
    assert updated.status_code == 200
    root_after = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    assert root_after["title"] == "Calculus II"
    assert root_after["summary"] == "Single-variable calculus"

    cleared = course_client.patch(f"/api/v1/courses/{course_id}", json={"description": ""})
    assert cleared.status_code == 200
    root_cleared = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    assert root_cleared["summary"] is None
    assert root_cleared["title"] == "Calculus II"


def test_outline_draft_validates_and_drops_unknown_ids(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Calculus"}).json()["id"]
    for i in range(3):
        add_material(course_client, f"m{i}.txt", course_id)

    draft = course_client.post(f"/api/v1/courses/{course_id}/outline/draft").json()
    chapters = draft["chapters"]
    assert [chapter["title"] for chapter in chapters] == ["Limits", "Derivatives"]
    section = chapters[0]["sections"][0]
    assert section["material_ids"] == [1, 2]
    bogus = chapters[1]["sections"][0]
    assert 999 not in bogus["material_ids"]
    assert bogus["confidence"] <= 1.0


def test_outline_draft_without_materials_fails(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Empty"}).json()["id"]
    response = course_client.post(f"/api/v1/courses/{course_id}/outline/draft")
    assert response.status_code == 422


def test_outline_commit_writes_tree_and_allocations(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Calculus"}).json()["id"]
    material_ids = [add_material(course_client, f"m{i}.txt", course_id) for i in range(3)]

    draft = course_client.post(f"/api/v1/courses/{course_id}/outline/draft").json()
    commit = course_client.post(
        f"/api/v1/courses/{course_id}/outline/commit", json={"chapters": draft["chapters"]}
    )
    assert commit.status_code == 200
    result = commit.json()
    assert result == {"chapters": 2, "sections": 3, "allocations": 3}

    tree = course_client.get(f"/api/v1/courses/{course_id}/tree").json()
    assert len(tree) == 1 and tree[0]["is_root"] is True
    chapters = tree[0]["children"]
    assert [chapter["title"] for chapter in chapters] == ["Limits", "Derivatives"]
    first_section = chapters[0]["children"][0]
    assert first_section["title"] == "Limit intuition"
    assert first_section["objectives"] == ["Explain limits informally"]
    allocated_ids = [material["material_id"] for material in first_section["materials"]]
    assert allocated_ids == material_ids[:2]
    assert first_section["materials"][0]["auto_assigned"] is True
    assert first_section["materials"][0]["rationale"] == "Both cover introductory limits"


def test_manual_structure_edits(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Manual"}).json()["id"]
    root = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]

    chapter = course_client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root["id"], "title": "Chapter 1"},
    ).json()
    second = course_client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root["id"], "title": "Chapter 2"},
    ).json()

    def children() -> list[dict[str, Any]]:
        tree: list[dict[str, Any]] = course_client.get(
            f"/api/v1/courses/{course_id}/tree"
        ).json()
        return list(tree[0]["children"])

    parent = root["id"]
    for depth in range(1, 5):
        nested = course_client.post(
            f"/api/v1/courses/{course_id}/nodes",
            json={"course_id": course_id, "parent_id": parent, "title": f"L{depth}"},
        )
        assert nested.status_code == 201, nested.text
        parent = nested.json()["id"]
    too_deep = course_client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": parent, "title": "L5"},
    )
    assert too_deep.status_code == 422

    course_client.patch(
        f"/api/v1/nodes/{second['id']}/move",
        json={"parent_id": root["id"], "position": 0},
    )
    assert [entry["title"] for entry in children()] == ["Chapter 2", "Chapter 1", "L1"]

    section = course_client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={
            "course_id": course_id,
            "parent_id": chapter["id"],
            "title": "Basics",
            "objectives": ["Learn basics"],
        },
    ).json()
    material_id = add_material(course_client, "note.txt", course_id)
    allocation = course_client.post(
        f"/api/v1/nodes/{section['id']}/materials",
        json={"material_id": material_id, "rationale": "manual pick"},
    )
    assert allocation.status_code == 201
    tree = course_client.get(f"/api/v1/courses/{course_id}/tree").json()
    chapter_one = next(c for c in tree[0]["children"] if c["id"] == chapter["id"])
    materials = chapter_one["children"][0]["materials"]
    assert materials[0]["material_id"] == material_id
    assert materials[0]["auto_assigned"] is False

    removed = course_client.delete(
        f"/api/v1/nodes/{section['id']}/materials/{material_id}"
    )
    assert removed.status_code == 204

    course_client.patch(f"/api/v1/nodes/{section['id']}", json={"title": "Basics (renamed)"})
    tree = course_client.get(f"/api/v1/courses/{course_id}/tree").json()
    chapter_one = next(c for c in tree[0]["children"] if c["id"] == chapter["id"])
    assert chapter_one["children"][0]["title"] == "Basics (renamed)"

    course_client.delete(f"/api/v1/nodes/{chapter["id"]}")
    assert [entry["title"] for entry in children()] == [
        "Chapter 2",
        "Basics (renamed)",
        "L1",
    ]


def test_study_state_roundtrip(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Study"}).json()["id"]
    material_id = add_material(course_client, "notes.txt", course_id)
    response = course_client.put(
        f"/api/v1/materials/{material_id}/study-state",
        json={"status": "reading", "progress": 0.4},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reading"
    assert body["progress"] == 0.4
    assert body["last_opened_at"] is not None

    states = course_client.get("/api/v1/study-states").json()
    assert states[str(material_id)]["status"] == "reading"

    invalid = course_client.put(
        f"/api/v1/materials/{material_id}/study-state", json={"status": "done"}
    )
    assert invalid.status_code == 422

    studied = course_client.put(
        f"/api/v1/materials/{material_id}/study-state", json={"status": "studied"}
    )
    assert studied.json()["progress"] == 1.0


def test_course_materials_and_workspace_response_shapes(
    course_client: TestClient,
) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Shapes"}).json()["id"]
    material_id = add_material(course_client, "shapes.txt", course_id)
    root = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    chapter = course_client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root["id"], "title": "Chapter"},
    ).json()
    assigned = course_client.post(
        f"/api/v1/nodes/{chapter['id']}/materials",
        json={"material_id": material_id, "rationale": "manual"},
    )
    assert assigned.status_code == 201
    assert assigned.json() == {"node_id": chapter["id"], "material_id": material_id}

    entries = course_client.get(f"/api/v1/courses/{course_id}/materials").json()
    assert len(entries) == 1
    assert set(entries[0]) == {
        "node_id",
        "node_title",
        "node_is_root",
        "material_id",
        "title",
        "rationale",
        "auto_assigned",
        "confidence",
        "via_folder",
    }
    assert entries[0]["via_folder"] is None
    assert entries[0]["node_id"] == chapter["id"]

    workspace = course_client.get(f"/api/v1/nodes/{chapter['id']}/workspace").json()
    assert set(workspace) == {
        "node",
        "children",
        "folders",
        "materials",
        "folder_material_ids",
        "child_materials",
        "notes",
        "counts",
        "concepts",
    }
    assert set(workspace["node"]) == {
        "id",
        "course_id",
        "course_title",
        "title",
        "summary",
        "objectives",
        "ai_hint",
        "depth",
        "is_root",
        "parent_id",
        "breadcrumb",
    }
    assert set(workspace["counts"]) == {
        "notes",
        "quizzes",
        "exercises",
        "flashcards",
        "child_nodes",
    }
    assert workspace["counts"]["child_nodes"] == 0
    assert workspace["materials"][0]["kind"] == "txt"
    assert workspace["materials"][0]["status"] == "ready"
    assert workspace["materials"][0]["read_status"] == "unread"
    assert workspace["materials"][0]["progress"] == 0.0
    assert workspace["materials"][0]["provenance"] is None
    assert workspace["child_materials"] == {}

    deleted = course_client.delete(
        f"/api/v1/courses/{course_id}", params={"confirmed_backup": True}
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted", "course_id": course_id}
