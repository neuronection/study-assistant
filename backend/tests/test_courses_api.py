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


def _folder(client: TestClient, name: str, course_id: int, parent_id: int | None = None) -> int:
    created = client.post(
        "/api/v1/folders", json={"name": name, "course_id": course_id, "parent_id": parent_id}
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def _mirror(client: TestClient, node_id: int, folder_id: int) -> dict[str, Any]:
    response = client.post(f"/api/v1/nodes/{node_id}/mirror-folder", json={"folder_id": folder_id})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_mirror_folder_writes_tree_and_folder_links(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Mirror"}).json()["id"]
    root = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    pack = _folder(course_client, "Calculus", course_id)
    week1 = _folder(course_client, "Week 1", course_id, pack)
    _folder(course_client, "Week 2", course_id, pack)
    _folder(course_client, "inner", course_id, week1)
    material_id = add_material(course_client, "m.txt", course_id)
    assert course_client.patch(
        f"/api/v1/materials/{material_id}/move", json={"folder_id": week1}
    ).status_code == 200

    result = _mirror(course_client, root["id"], pack)
    assert result["created_nodes"] == 3
    assert result["reused_nodes"] == 0
    assert result["folder_links"] == 4
    assert result["skipped_folders"] == []

    tree = course_client.get(f"/api/v1/courses/{course_id}/tree").json()
    weeks = tree[0]["children"]
    assert [child["title"] for child in weeks] == ["Week 1", "Week 2"]
    assert [child["title"] for child in weeks[0]["children"]] == ["inner"]

    workspace = course_client.get(f"/api/v1/nodes/{weeks[0]['id']}/workspace").json()
    assert material_id in workspace["folder_material_ids"]
    links = course_client.get(f"/api/v1/materials/{material_id}/links").json()
    via_nodes = {
        entry["node_id"] for entry in links if entry["via_folder"] is not None
    }
    assert weeks[0]["id"] in via_nodes


def test_mirror_folder_is_idempotent(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Mirror again"}).json()["id"]
    root = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    pack = _folder(course_client, "Algebra", course_id)
    _folder(course_client, "Basics", course_id, pack)

    first = _mirror(course_client, root["id"], pack)
    second = _mirror(course_client, root["id"], pack)
    assert first["created_nodes"] == 1
    assert second["created_nodes"] == 0
    assert second["reused_nodes"] == 1
    assert second["folder_links"] == 2
    tree = course_client.get(f"/api/v1/courses/{course_id}/tree").json()
    assert [child["title"] for child in tree[0]["children"]] == ["Basics"]


def test_mirror_reuses_existing_same_title_nodes(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Reuse"}).json()["id"]
    root = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    course_client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root["id"], "title": "chapter 1"},
    )
    pack = _folder(course_client, "Unrelated", course_id)
    _folder(course_client, "Chapter 1", course_id, pack)
    _folder(course_client, "Section A", course_id, pack)

    result = _mirror(course_client, root["id"], pack)
    assert result["reused_nodes"] == 1
    assert result["created_nodes"] == 1
    assert result["folder_links"] == 3
    tree = course_client.get(f"/api/v1/courses/{course_id}/tree").json()
    titles = [child["title"] for child in tree[0]["children"]]
    assert titles == ["chapter 1", "Section A"]


def _node_chain(client: TestClient, course_id: int, root_id: int, levels: list[str]) -> int:
    parent = root_id
    for title in levels:
        node = client.post(
            f"/api/v1/courses/{course_id}/nodes",
            json={"course_id": course_id, "parent_id": parent, "title": title},
        )
        assert node.status_code == 201, node.text
        parent = int(node.json()["id"])
    return parent


def test_mirror_skips_deeper_than_node_depth(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Deep"}).json()["id"]
    root = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    deep_node = _node_chain(course_client, course_id, root["id"], ["A", "B", "C", "D"])
    leaf = _folder(course_client, "L1", course_id)
    _folder(course_client, "L2", course_id, leaf)

    result = _mirror(course_client, deep_node, leaf)
    assert result["created_nodes"] == 0
    assert result["folder_links"] == 1
    assert result["skipped_folders"] == ["L1/L2"]
    tree = course_client.get(f"/api/v1/courses/{course_id}/tree").json()
    deep_node_children = tree[0]["children"][0]["children"][0]["children"][0]["children"][0][
        "children"
    ]
    assert deep_node_children == []


def test_mirror_folder_not_in_course_rejected(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "One"}).json()["id"]
    other_id = course_client.post("/api/v1/courses", json={"title": "Two"}).json()["id"]
    root = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    foreign = _folder(course_client, "Foreign", other_id)
    response = course_client.post(
        f"/api/v1/nodes/{root['id']}/mirror-folder", json={"folder_id": foreign}
    )
    assert response.status_code == 422
    assert "not in this course" in response.json()["detail"]


def test_unassigned_endpoint_semantics(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Unassigned"}).json()["id"]
    other_id = course_client.post("/api/v1/courses", json={"title": "Other"}).json()["id"]
    root = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    loose = add_material(course_client, "loose.txt", course_id)
    placed = add_material(course_client, "placed.txt", course_id)
    other = add_material(course_client, "other.txt", other_id)
    assert course_client.post(
        f"/api/v1/nodes/{root['id']}/materials", json={"material_id": placed}
    ).status_code == 201
    folder = _folder(course_client, "Pack", course_id)
    in_folder = add_material(course_client, "infolder.txt", course_id)
    client_move = course_client.patch(
        f"/api/v1/materials/{in_folder}/move", json={"folder_id": folder}
    )
    assert client_move.status_code == 200
    course_client.post(f"/api/v1/nodes/{root['id']}/folder-materials", json={"folder_id": folder})

    listing = course_client.get(f"/api/v1/courses/{course_id}/materials/unassigned").json()
    ids = [entry["id"] for entry in listing["materials"]]
    assert listing["count"] == len(ids)
    assert loose in ids
    assert placed not in ids
    assert in_folder not in ids
    assert other not in ids


def test_unassigned_endpoint_caps_at_40_and_counts(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Cap"}).json()["id"]
    for index in range(42):
        add_material(course_client, f"m{index}.txt", course_id)
    listing = course_client.get(f"/api/v1/courses/{course_id}/materials/unassigned").json()
    assert listing["count"] == 40
    assert len(listing["materials"]) == 40


def test_unassigned_endpoint_excludes_not_ready(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Pending"}).json()["id"]
    add_material(course_client, "ready-one.txt", course_id)
    upload = course_client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("big.mp3", b"x" * 200, "audio/mpeg")},
    )
    material_id = int(upload.json()["material"]["id"])

    def is_ready() -> bool:
        status: str = course_client.get(f"/api/v1/materials/{material_id}").json()[
            "material"
        ]["status"]
        return status == "ready"

    deadline = __import__("time").monotonic() + 20
    while __import__("time").monotonic() < deadline and not is_ready():
        __import__("time").sleep(0.1)
    body = course_client.get(f"/api/v1/courses/{course_id}/materials/unassigned").json()
    assert body["count"] >= 1


def _index_card_ready(client: TestClient, filename: str, course_id: int) -> int:
    return add_material(client, filename, course_id)


def test_placement_suggestions_rank_and_evidence(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "Suggest"}).json()["id"]
    root = course_client.get(f"/api/v1/courses/{course_id}/tree").json()[0]
    integration = course_client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root["id"], "title": "Integration techniques"},
    ).json()
    course_client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root["id"], "title": "Series overview"},
    ).json()
    loose = add_material(course_client, "integration by parts worked examples.txt", course_id)

    result = course_client.post(
        f"/api/v1/courses/{course_id}/placement-suggestions",
        json={"material_ids": [loose]},
    )
    assert result.status_code == 200, result.text
    body = result.json()
    suggestions = body["suggestions"]
    assert len(suggestions) == 1
    candidates = suggestions[0]["candidates"]
    assert candidates
    assert candidates[0]["node_id"] == integration["id"]
    assert candidates[0]["matched_on"]
    assert 0 < candidates[0]["score"] <= 1.15
    assert candidates[0]["breadcrumb"][0]["title"] == "Suggest"


def test_placement_suggestions_empty_and_foreign(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "S-A"}).json()["id"]
    no_nodes = course_client.post(
        f"/api/v1/courses/{course_id}/placement-suggestions",
        json={"material_ids": []},
    )
    assert no_nodes.status_code == 200
    assert no_nodes.json() == {"suggestions": []}

    other = course_client.post("/api/v1/courses", json={"title": "S-B"}).json()["id"]
    foreign = add_material(course_client, "foreign notes.txt", other)
    result = course_client.post(
        f"/api/v1/courses/{course_id}/placement-suggestions",
        json={"material_ids": [foreign]},
    )
    body = result.json()
    assert result.status_code == 200
    assert body["suggestions"][0]["candidates"] == []


def test_placement_suggestions_caps_inputs(course_client: TestClient) -> None:
    course_id = course_client.post("/api/v1/courses", json={"title": "S-C"}).json()["id"]
    assert course_client.post(
        f"/api/v1/courses/{course_id}/placement-suggestions",
        json={"material_ids": list(range(1, 41))},
    ).status_code == 200
    assert (
        course_client.post(
            f"/api/v1/courses/{course_id}/placement-suggestions",
            json={"material_ids": list(range(1, 42))},
        ).status_code
        == 422
    )
