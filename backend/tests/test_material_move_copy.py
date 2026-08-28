import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.models import Chunk, Extraction, Job, Material, MaterialLink


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def make_course(client: TestClient, title: str = "Movers") -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def create_folder(
    client: TestClient, name: str, course_id: int, parent_id: int | None = None
) -> int:
    response = client.post(
        "/api/v1/folders",
        json={"name": name, "course_id": course_id, "parent_id": parent_id},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def upload_text(
    client: TestClient, content: str, filename: str, course_id: int
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/materials/text",
        json={
            "course_id": course_id,
            "filename": filename,
            "content": content,
        },
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    wait_until(
        lambda: client.get(
            f"/api/v1/materials/{body['material']['id']}"
        ).json()["material"]["status"]
        == "ready"
    )
    return body


def make_node(client: TestClient, course_id: int, title: str) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = int(tree[0]["id"])
    response = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": title},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def session_factory(client: TestClient) -> Any:
    return cast(Any, client.app).state.session_factory


def test_move_material_into_folder_and_back_to_root(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = upload_text(
        client, "moving content", "move-me.txt", course_id
    )["material"]["id"]
    folder_id = create_folder(client, "Target", course_id)

    moved = client.patch(
        f"/api/v1/materials/{material_id}/move", json={"folder_id": folder_id}
    )
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == folder_id
    listing = client.get(f"/api/v1/materials?folder_id={folder_id}").json()
    assert [entry["id"] for entry in listing] == [material_id]

    to_root = client.patch(
        f"/api/v1/materials/{material_id}/move", json={"folder_id": None}
    )
    assert to_root.status_code == 200
    assert to_root.json()["folder_id"] is None


def test_move_material_rejects_cross_course_folder(client: TestClient) -> None:
    first = make_course(client, "One")
    second = make_course(client, "Two")
    material_id = upload_text(client, "content", "a.txt", first)["material"]["id"]
    foreign_folder = create_folder(client, "Foreign", second)

    response = client.patch(
        f"/api/v1/materials/{material_id}/move",
        json={"folder_id": foreign_folder},
    )
    assert response.status_code == 422
    assert "different course" in response.json()["detail"]


def test_move_material_rejects_linked_folder(
    client: TestClient, tmp_path: Path
) -> None:
    course_id = make_course(client)
    material_id = upload_text(client, "content", "a.txt", course_id)["material"]["id"]
    target = tmp_path / "linked"
    target.mkdir()
    source = client.post(
        "/api/v1/sources",
        json={"label": "link", "path": str(target), "course_id": course_id},
    )
    assert source.status_code == 201
    folder_id = int(
        client.get("/api/v1/folders", params={"course_id": course_id}).json()[0]["id"]
    )

    response = client.patch(
        f"/api/v1/materials/{material_id}/move", json={"folder_id": folder_id}
    )
    assert response.status_code == 422
    assert "linked" in response.json()["detail"]


def test_move_material_rejects_unknown_folder(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = upload_text(client, "content", "a.txt", course_id)["material"]["id"]
    response = client.patch(
        f"/api/v1/materials/{material_id}/move", json={"folder_id": 99999}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "folder not found"


def test_copy_material_deep_copies_latest_extraction(
    client: TestClient,
) -> None:
    course_id = make_course(client)
    source = upload_text(
        client, "chain rule notes for copy", "source.txt", course_id
    )
    source_id = source["material"]["id"]
    node_id = make_node(client, course_id, "Chapter")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/materials", json={"material_id": source_id}
    )
    assert assigned.status_code == 201
    folder_id = create_folder(client, "Copies", course_id)

    copied = client.post(
        f"/api/v1/materials/{source_id}/copy", json={"folder_id": folder_id}
    )
    assert copied.status_code == 201, copied.text
    copy = copied.json()
    copy_id = copy["id"]
    assert copy_id != source_id
    assert copy["title"] == "source (copy)"
    assert copy["folder_id"] == folder_id
    assert copy["blob_sha"] == source["material"]["blob_sha"]

    factory = session_factory(client)
    with factory() as session:
        source_row = session.get(Material, source_id)
        copy_row = session.get(Material, copy_id)
        assert copy_row is not None and source_row is not None
        assert copy_row.content_hash == source_row.content_hash
        source_extraction = session.scalar(
            select(Extraction).where(Extraction.material_id == source_id)
        )
        copy_extraction = session.scalar(
            select(Extraction).where(Extraction.material_id == copy_id)
        )
        assert source_extraction is not None and copy_extraction is not None
        assert copy_extraction.version == 1
        assert copy_extraction.markdown == source_extraction.markdown
        assert copy_extraction.id != source_extraction.id
        source_chunks = session.scalars(
            select(Chunk).where(Chunk.extraction_id == source_extraction.id)
        ).all()
        copy_chunks = session.scalars(
            select(Chunk).where(Chunk.extraction_id == copy_extraction.id)
        ).all()
        assert [c.text for c in copy_chunks] == [c.text for c in source_chunks]
        assert {c.id for c in copy_chunks}.isdisjoint({c.id for c in source_chunks})
        assert (
            session.scalars(
                select(MaterialLink).where(MaterialLink.material_id == copy_id)
            ).first()
            is None
        )
        jobs = session.scalars(
            select(Job).where(
                Job.type == "postprocess",
                Job.payload["material_id"].as_integer() == copy_id,
            )
        ).all()
        assert len(jobs) == 1

    search = client.get("/api/v1/search", params={"q": "copy"}).json()
    assert sorted(hit["material_id"] for hit in search["hits"]) == sorted(
        [source_id, copy_id]
    )


def test_copy_material_uniques_title(client: TestClient) -> None:
    course_id = make_course(client)
    source = upload_text(client, "content", "notes.txt", course_id)
    source_id = source["material"]["id"]

    first = client.post(f"/api/v1/materials/{source_id}/copy", json={})
    assert first.status_code == 201
    assert first.json()["title"] == "notes (copy)"

    second = client.post(f"/api/v1/materials/{source_id}/copy", json={})
    assert second.status_code == 201
    assert second.json()["title"] == "notes (copy 2)"

    copy_of_copy = client.post(
        f"/api/v1/materials/{first.json()['id']}/copy", json={}
    )
    assert copy_of_copy.status_code == 201
    assert copy_of_copy.json()["title"] == "notes (copy) (copy)"


def test_move_note_between_nodes(client: TestClient) -> None:
    course_id = make_course(client)
    first_node = make_node(client, course_id, "One")
    second_node = make_node(client, course_id, "Two")
    created = client.post(
        "/api/v1/notes",
        json={"title": "Movable", "course_id": course_id, "node_id": first_node},
    )
    assert created.status_code == 201
    note_id = int(created.json()["id"])

    moved = client.patch(
        f"/api/v1/notes/{note_id}/move", json={"node_id": second_node}
    )
    assert moved.status_code == 200
    assert moved.json()["node_id"] == second_node

    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = int(tree[0]["id"])
    to_root = client.patch(f"/api/v1/notes/{note_id}/move", json={"node_id": None})
    assert to_root.status_code == 200
    assert to_root.json()["node_id"] == root_id


def test_move_note_rejects_foreign_node(client: TestClient) -> None:
    first = make_course(client, "One")
    second = make_course(client, "Two")
    foreign_node = make_node(client, second, "Foreign")
    created = client.post(
        "/api/v1/notes", json={"title": "Note", "course_id": first}
    )
    note_id = int(created.json()["id"])

    response = client.patch(
        f"/api/v1/notes/{note_id}/move", json={"node_id": foreign_node}
    )
    assert response.status_code == 422
    assert "different course" in response.json()["detail"]


def _make_activity(client: TestClient, course_id: int, title: str) -> int:
    from app.domain.models import Activity, Profile

    factory = session_factory(client)
    with factory() as session:
        profile = session.scalars(select(Profile)).first()
        assert profile is not None
        activity = Activity(
            profile_id=profile.id,
            course_id=course_id,
            title=title,
            type="quiz",
        )
        session.add(activity)
        session.commit()
        return int(activity.id)


def test_move_quiz_between_nodes(client: TestClient) -> None:
    course_id = make_course(client)
    node = make_node(client, course_id, "Quiz node")
    activity_id = _make_activity(client, course_id, "Movable quiz")

    moved = client.patch(
        f"/api/v1/quiz/activities/{activity_id}/move", json={"node_id": node}
    )
    assert moved.status_code == 200
    assert moved.json()["node_id"] == node

    other_course = make_course(client, "Other")
    other_node = make_node(client, other_course, "Other node")
    rejected = client.patch(
        f"/api/v1/quiz/activities/{activity_id}/move",
        json={"node_id": other_node},
    )
    assert rejected.status_code == 422


def test_move_exercise_between_nodes(client: TestClient) -> None:
    course_id = make_course(client)
    node = make_node(client, course_id, "Exercise node")
    created = client.post(
        "/api/v1/exercises",
        json={
            "title": "Movable exercise",
            "course_id": course_id,
            "steps": [
                {
                    "prompt_md": "Differentiate x^2",
                    "expected": {"answer": "2x"},
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    exercise_id = int(created.json()["id"])

    moved = client.patch(
        f"/api/v1/exercises/{exercise_id}/move", json={"node_id": node}
    )
    assert moved.status_code == 200
    assert moved.json()["node_id"] == node

    other_course = make_course(client, "Other")
    other_node = make_node(client, other_course, "Other node")
    rejected = client.patch(
        f"/api/v1/exercises/{exercise_id}/move", json={"node_id": other_node}
    )
    assert rejected.status_code == 422
