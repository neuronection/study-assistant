from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient
from pytest import fixture

from app.core.config import Settings
from app.main import create_app

CAQ: dict[str, Any] = {
    "$schema": "caq/v1",
    "title": "Scoped quiz",
    "questions": [
        {
            "id": "q1",
            "type": "truefalse",
            "stem_md": "Scoped?",
            "answer": True,
            "explanation_md": "Yes.",
            "concepts": ["scoping"],
            "skill": "conceptual",
            "bloom": "remember",
            "difficulty": 1,
            "expected_time_sec": 30,
        }
    ],
}


@fixture
def client() -> Iterator[TestClient]:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-p9-"))
    app = create_app(Settings(data_dir=tmp, log_level="WARNING"))
    with TestClient(app) as test_client:
        yield test_client


def make_node(client: TestClient, course_id: int, parent_id: int, title: str) -> int:
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": parent_id, "title": title},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def root_node(client: TestClient, course_id: int) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    return int(tree[0]["id"])


def make_course(client: TestClient, title: str) -> int:
    return int(client.post("/api/v1/courses", json={"title": title}).json()["id"])


def test_scoped_lists_roll_up_children(client: TestClient) -> None:
    course_id = make_course(client, "Scoped")
    root = root_node(client, course_id)
    chapter = make_node(client, course_id, root, "Ch")
    section = make_node(client, course_id, chapter, "Sec")

    quiz = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": course_id},
        json=CAQ,
    )
    assert quiz.status_code == 200, quiz.text
    section_quiz_id = int(quiz.json()["activity"]["id"])

    exercise = client.post(
        "/api/v1/exercises",
        json={
            "title": "Scoped exercise",
            "course_id": course_id,
            "node_id": section,
            "steps": [{"prompt_md": "Compute", "expected": {"kind": "math", "value": "x"}}],
        },
    )
    assert exercise.status_code == 201, exercise.text

    card = client.post(
        "/api/v1/flashcards",
        json={"front_md": "f", "back_md": "b", "course_id": course_id, "node_id": chapter},
    )
    assert card.status_code == 201, card.text

    note = client.post(
        "/api/v1/notes",
        json={"title": "n", "course_id": course_id, "node_id": section},
    )
    assert note.status_code == 201, note.text

    other_course = make_course(client, "Elsewhere")
    other_note = client.post(
        "/api/v1/notes", json={"title": "outside", "course_id": other_course}
    )
    assert other_note.status_code == 201

    quizzes_at_root = client.get("/api/v1/quiz/activities", params={"node_id": root}).json()
    assert [entry["id"] for entry in quizzes_at_root] == [section_quiz_id]
    assert quizzes_at_root[0]["node_id"] == root

    quizzes_at_chapter = client.get(
        "/api/v1/quiz/activities", params={"node_id": chapter}
    ).json()
    assert quizzes_at_chapter == []
    quizzes_own_only = client.get(
        "/api/v1/quiz/activities", params={"node_id": root, "include_children": "false"}
    ).json()
    assert [entry["id"] for entry in quizzes_own_only] == [section_quiz_id]

    exercises_at_root = client.get(
        "/api/v1/exercises", params={"node_id": root}
    ).json()
    assert [entry["id"] for entry in exercises_at_root] == [exercise.json()["id"]]
    exercises_at_chapter = client.get(
        "/api/v1/exercises", params={"node_id": chapter}
    ).json()
    assert [entry["id"] for entry in exercises_at_chapter] == [exercise.json()["id"]]
    exercises_own_only = client.get(
        "/api/v1/exercises", params={"node_id": chapter, "include_children": "false"}
    ).json()
    assert exercises_own_only == []

    cards_at_chapter = client.get(
        "/api/v1/flashcards", params={"node_id": chapter}
    ).json()
    assert [entry["id"] for entry in cards_at_chapter] == [card.json()["id"]]

    notes_at_chapter = client.get(
        "/api/v1/notes", params={"node_id": chapter}
    ).json()
    assert [entry["id"] for entry in notes_at_chapter["items"]] == [note.json()["id"]]

    notes_root_only = client.get(
        "/api/v1/notes", params={"node_id": chapter, "include_children": "false"}
    ).json()
    assert notes_root_only["items"] == []


def test_cross_course_placement_refused(client: TestClient) -> None:
    course_id = make_course(client, "A")
    other_id = make_course(client, "B")
    other_root = root_node(client, other_id)

    exercise = client.post(
        "/api/v1/exercises",
        json={
            "title": "Bad scope",
            "course_id": course_id,
            "node_id": other_root,
            "steps": [{"prompt_md": "x"}],
        },
    )
    assert exercise.status_code == 422

    note = client.post(
        "/api/v1/notes",
        json={"title": "Bad note", "course_id": course_id, "node_id": other_root},
    )
    assert note.status_code == 422

    root = root_node(client, course_id)
    deep_parent = root
    for _ in range(4):
        deep_parent = make_node(client, course_id, deep_parent, "L")
    too_deep = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": deep_parent, "title": "L5"},
    )
    assert too_deep.status_code == 422


def test_delete_node_merges_placements(client: TestClient) -> None:
    course_id = make_course(client, "Merge")
    root = root_node(client, course_id)
    chapter = make_node(client, course_id, root, "Ch")
    section = make_node(client, course_id, chapter, "Sec")

    quiz = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": course_id},
        json=CAQ,
    )
    quiz_id = int(quiz.json()["activity"]["id"])
    note = client.post(
        "/api/v1/notes", json={"title": "n", "course_id": course_id, "node_id": section}
    ).json()

    moved = client.delete(f"/api/v1/nodes/{chapter}")
    assert moved.status_code == 200
    assert moved.json()["undo_token"]

    quizzes = client.get("/api/v1/quiz/activities", params={"node_id": root}).json()
    assert [entry["id"] for entry in quizzes] == [quiz_id]
    assert quizzes[0]["node_id"] == root
    notes = client.get("/api/v1/notes", params={"node_id": root}).json()
    assert [entry["id"] for entry in notes["items"]] == [note["id"]]
    assert notes["items"][0]["node_id"] == section


def test_chat_session_binds_node(client: TestClient) -> None:
    course_id = make_course(client, "Chat")
    root = root_node(client, course_id)
    chapter = make_node(client, course_id, root, "Ch")
    created = client.post(
        "/api/v1/chat/sessions", json={"course_id": course_id, "node_id": chapter}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["node_id"] == chapter
    assert body["course_id"] == course_id


def test_root_is_undeletable_and_uneditable(client: TestClient) -> None:
    course_id = make_course(client, "Root")
    root = root_node(client, course_id)
    deleted = client.delete(f"/api/v1/nodes/{root}")
    assert deleted.status_code == 422
    moved = client.patch(
        f"/api/v1/nodes/{root}/move", json={"parent_id": root, "position": 0}
    )
    assert moved.status_code == 422


def test_tree_carries_direct_counts(client: TestClient) -> None:
    course_id = make_course(client, "Counts")
    root = root_node(client, course_id)
    child = make_node(client, course_id, root, "C1")
    grandchild = make_node(client, course_id, child, "C2")

    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("counts.txt", b"counting", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    material_id = int(upload.json()["material"]["id"])
    linked = client.post(
        f"/api/v1/nodes/{child}/materials", json={"material_id": material_id}
    )
    assert linked.status_code == 201, linked.text

    quiz = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": course_id},
        json=CAQ,
    )
    assert quiz.status_code == 200, quiz.text
    exercise = client.post(
        "/api/v1/exercises",
        json={
            "title": "E",
            "course_id": course_id,
            "node_id": root,
            "steps": [{"prompt_md": "Compute", "expected": {"kind": "math", "value": "x"}}],
        },
    )
    assert exercise.status_code == 201, exercise.text
    card = client.post(
        "/api/v1/flashcards",
        json={
            "front_md": "f",
            "back_md": "b",
            "course_id": course_id,
            "node_id": child,
        },
    )
    assert card.status_code == 201, card.text
    note = client.post(
        "/api/v1/notes",
        json={"title": "n", "course_id": course_id, "node_id": root},
    )
    assert note.status_code == 201, note.text
    studied = client.put(
        f"/api/v1/materials/{material_id}/study-state",
        json={"status": "studied"},
    )
    assert studied.status_code == 200, studied.text

    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    assert tree[0]["counts"] == {
        "materials": 0,
        "notes": 1,
        "quizzes": 1,
        "exercises": 1,
        "flashcards": 0,
        "studied": 0,
        "cards_due": 0,
    }
    child_entry = next(c for c in tree[0]["children"] if c["id"] == child)
    assert child_entry["counts"] == {
        "materials": 1,
        "notes": 0,
        "quizzes": 0,
        "exercises": 0,
        "flashcards": 1,
        "studied": 1,
        "cards_due": 1,
    }
    grandchild_entry = next(c for c in child_entry["children"] if c["id"] == grandchild)
    assert grandchild_entry["counts"] == {
        "materials": 0,
        "notes": 0,
        "quizzes": 0,
        "exercises": 0,
        "flashcards": 0,
        "studied": 0,
        "cards_due": 0,
    }


def test_delete_restore_round_trip(client: TestClient) -> None:
    from app.services.knowledge.tree import _SNAPSHOTS

    _SNAPSHOTS.clear()
    course_id = make_course(client, "Undo")
    root = root_node(client, course_id)
    parent = make_node(client, course_id, root, "P")
    child_a = make_node(client, course_id, parent, "A")
    make_node(client, course_id, parent, "B")
    make_node(client, course_id, child_a, "Deep")

    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("undo.txt", b"undo me", "text/plain")},
    )
    material_id = int(upload.json()["material"]["id"])
    assert (
        client.post(
            f"/api/v1/nodes/{child_a}/materials", json={"material_id": material_id}
        ).status_code
        == 201
    )
    note = client.post(
        "/api/v1/notes", json={"title": "n", "course_id": course_id, "node_id": child_a}
    )
    assert note.status_code == 201
    note_id = int(note.json()["id"])

    deleted = client.delete(f"/api/v1/nodes/{child_a}")
    assert deleted.status_code == 200, deleted.text
    token = deleted.json()["undo_token"]
    assert token

    assert client.get(f"/api/v1/nodes/{child_a}").status_code == 404
    assert client.get(f"/api/v1/notes/{note_id}").json()["node_id"] == parent

    restored = client.post("/api/v1/nodes/restore", json={"undo_token": token})
    assert restored.status_code == 200, restored.text
    new_id = int(restored.json()["id"])
    assert new_id != child_a

    node = client.get(f"/api/v1/nodes/{new_id}").json()
    assert node["title"] == "A"
    assert node["parent_id"] == parent
    children = client.get(f"/api/v1/nodes/{parent}/workspace").json()["children"]
    assert [c["title"] for c in children] == ["A", "B"]

    subtree = client.get(f"/api/v1/nodes/{new_id}/workspace").json()
    assert [m["material_id"] for m in subtree["materials"]] == [material_id]
    assert [n["id"] for n in subtree["notes"]] == [note_id]
    assert client.get(f"/api/v1/notes/{note_id}").json()["node_id"] == new_id
    assert "Deep" in [c["title"] for c in subtree["children"]]

    again = client.post("/api/v1/nodes/restore", json={"undo_token": token})
    assert again.status_code == 422


def test_restore_refuses_unknown_token(client: TestClient) -> None:
    make_course(client, "Foreign")
    restored = client.post("/api/v1/nodes/restore", json={"undo_token": "nope"})
    assert restored.status_code == 422
