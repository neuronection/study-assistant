from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_course_bundle import make_client, seed_course


def _workspace_course(client: TestClient, course_id: str) -> list[dict[str, Any]]:
    roots = client.get(f"/api/v1/courses/{course_id}/tree").json()

    def flatten(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for entry in entries:
            result.append(entry)
            result.extend(flatten(entry.get("children", [])))
        return result

    return sorted(flatten(roots), key=lambda entry: entry["title"])


def _add_task_assignment(client: TestClient, course_id: str) -> None:
    import conftest

    app = client.app
    assert isinstance(app, FastAPI)
    _, _, profile_id = conftest.mint_session(app)
    with app.state.session_factory() as db:
        from app.domain.models import CourseDefaultTaskAssignment, CourseTaskAssignment

        db.add(CourseTaskAssignment(course_id=course_id, task="quizgen", model_id=None))
        db.add(CourseDefaultTaskAssignment(course_id=course_id, requires="text", model_id=None))
        db.commit()
    assert profile_id


def test_duplicate_copies_the_tree_content_and_task_assignments(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        course_id = seed_course(client)
        _add_task_assignment(client, course_id)
        original_tree = _workspace_course(client, course_id)
        original_materials = client.get("/api/v1/materials", params={"course_id": course_id}).json()

        response = client.post(f"/api/v1/courses/{course_id}/duplicate", json={})
        assert response.status_code == 201, response.text
        payload = response.json()
        clone_id = payload["course"]["id"]
        assert clone_id != course_id
        assert payload["course"]["title"] == "Calculus I (copy)"
        assert payload["copy_materials"] is True
        assert payload["materials_copied"] == len(original_materials)
        assert payload["nodes_copied"] == len(original_tree)
        assert payload["task_assignments_copied"] == 2

        clone_tree = _workspace_course(client, clone_id)
        assert [entry["title"] for entry in clone_tree if not entry["is_root"]] == [
            entry["title"] for entry in original_tree if not entry["is_root"]
        ]
        assert next(entry for entry in clone_tree if entry["is_root"])["title"] == (
            "Calculus I (copy)"
        )
        original_ids = {entry["id"] for entry in original_tree}
        assert all(entry["id"] not in original_ids for entry in clone_tree)

        clone_materials = client.get("/api/v1/materials", params={"course_id": clone_id}).json()
        assert [entry["title"] for entry in clone_materials] == [
            entry["title"] for entry in original_materials
        ]
        assert {entry["id"] for entry in clone_materials}.isdisjoint(
            {entry["id"] for entry in original_materials}
        )
        assert clone_materials[0]["blob_sha"] == original_materials[0]["blob_sha"]

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import select

            from app.domain.models import (
                CourseDefaultTaskAssignment,
                CourseTaskAssignment,
            )

            tasks = list(
                db.scalars(
                    select(CourseTaskAssignment).where(CourseTaskAssignment.course_id == clone_id)
                )
            )
            defaults = list(
                db.scalars(
                    select(CourseDefaultTaskAssignment).where(
                        CourseDefaultTaskAssignment.course_id == clone_id
                    )
                )
            )
        assert [row.task for row in tasks] == ["quizgen"]
        assert [row.requires for row in defaults] == ["text"]


def test_clone_is_independent_of_the_original(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        course_id = seed_course(client)
        original_tree = _workspace_course(client, course_id)
        original_materials = client.get("/api/v1/materials", params={"course_id": course_id}).json()
        clone_id = client.post(f"/api/v1/courses/{course_id}/duplicate", json={}).json()["course"][
            "id"
        ]

        renamed = client.patch(f"/api/v1/courses/{clone_id}", json={"title": "Calculus II"})
        assert renamed.status_code == 200, renamed.text

        clone_tree = _workspace_course(client, clone_id)
        node = next(entry for entry in clone_tree if not entry["is_root"])
        edited = client.patch(f"/api/v1/nodes/{node['id']}", json={"title": "Limits"})
        assert edited.status_code == 200, edited.text

        deleted = client.delete(f"/api/v1/materials/{clone_materials_id(client, clone_id)}")
        assert deleted.status_code in (200, 204), deleted.text

        originals = _workspace_course(client, course_id)
        assert [entry["title"] for entry in originals] == [
            entry["title"] for entry in original_tree
        ]
        assert client.get(f"/api/v1/courses/{course_id}").json()["title"] == "Calculus I"
        remaining = client.get("/api/v1/materials", params={"course_id": course_id}).json()
        assert [entry["id"] for entry in remaining] == [entry["id"] for entry in original_materials]


def clone_materials_id(client: TestClient, course_id: str) -> str:
    entry = client.get("/api/v1/materials", params={"course_id": course_id}).json()[0]
    return str(entry["id"])


def test_copy_materials_false_keeps_structure_only(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        course_id = seed_course(client)
        response = client.post(
            f"/api/v1/courses/{course_id}/duplicate",
            json={"copy_materials": False, "title": "Next semester"},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        clone_id = payload["course"]["id"]
        assert payload["course"]["title"] == "Next semester"
        assert payload["copy_materials"] is False
        assert payload["materials_copied"] == 0
        assert payload["nodes_copied"] >= 2
        assert payload["notes_copied"] >= 1
        assert payload["quizzes_copied"] >= 1
        assert payload["exercises_copied"] >= 1
        assert client.get("/api/v1/materials", params={"course_id": clone_id}).json() == []
        assert len(_workspace_course(client, clone_id)) == len(_workspace_course(client, course_id))


def test_duplicate_allocates_fresh_ids_and_uniques_titles(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        course_id = seed_course(client)
        first = client.post(f"/api/v1/courses/{course_id}/duplicate", json={}).json()
        second = client.post(f"/api/v1/courses/{course_id}/duplicate", json={}).json()
        assert first["course"]["title"] == "Calculus I (copy)"
        assert second["course"]["title"] == "Calculus I (copy) (2)"
        assert first["course"]["id"] != second["course"]["id"]

        original_nodes = {entry["id"] for entry in _workspace_course(client, course_id)}
        for clone_id in (first["course"]["id"], second["course"]["id"]):
            clone_nodes = {entry["id"] for entry in _workspace_course(client, clone_id)}
            assert clone_nodes.isdisjoint(original_nodes)


def test_duplicate_unknown_course_is_404(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        assert client.post("/api/v1/courses/nope/duplicate", json={}).status_code == 404
