import time
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.models import (
    Activity,
    Answer,
    Attempt,
    ChatSession,
    Concept,
    Exercise,
    NodeConcept,
    Note,
    Question,
)


def wait_until(predicate: Callable[[], bool], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition never met before timeout")


def make_course(client: TestClient, title: str = "Regular") -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def get_scratch(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/v1/courses/scratchpad")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def make_node(client: TestClient, course_id: int, parent_id: int, title: str) -> int:
    response = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": parent_id, "title": title},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def root_node(client: TestClient, course_id: int) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    return int(tree[0]["id"])


def upload_text(
    client: TestClient, course_id: int, filename: str, content: str
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/materials/text",
        json={"course_id": course_id, "filename": filename, "content": content},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    material_id = int(body["material"]["id"])
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"][
            "status"
        ]
        == "ready"
    )
    return body


def test_scratchpad_is_created_once_and_hidden(client: TestClient) -> None:
    first = get_scratch(client)
    second = get_scratch(client)
    assert first["course"]["id"] == second["course"]["id"]
    assert first["course"]["origin"] == "scratch"
    assert first["course"]["hidden"] is True
    assert first["content_count"] == 0

    visible = client.get("/api/v1/courses").json()
    assert all(course["id"] != first["course"]["id"] for course in visible)
    everything = client.get("/api/v1/courses", params={"include_hidden": "true"}).json()
    assert any(course["id"] == first["course"]["id"] for course in everything)


def test_promote_moves_subtree_placements_and_content(client: TestClient) -> None:
    scratch = get_scratch(client)["course"]
    scratch_id = int(scratch["id"])
    scratch_root = root_node(client, scratch_id)
    topic = make_node(client, scratch_id, scratch_root, "Group theory")
    make_node(client, scratch_id, topic, "Cyclic groups")

    note = client.post(
        "/api/v1/notes",
        json={
            "course_id": scratch_id,
            "node_id": topic,
            "title": "Lecture",
            "body_md": "abc",
        },
    )
    assert note.status_code == 201, note.text

    material = upload_text(client, scratch_id, "groups.md", "# groups")
    material_id = int(material["material"]["id"])
    assigned = client.post(
        f"/api/v1/nodes/{topic}/materials", json={"material_id": material_id}
    )
    assert assigned.status_code in (200, 201), assigned.text

    chat = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": scratch_id, "node_id": topic, "title": "scratch chat"},
    )
    assert chat.status_code in (200, 201), chat.text
    chat_id = int(chat.json()["id"])

    db_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    db = db_factory()
    try:
        concept = Concept(course_id=scratch_id, name="groups")
        db.add(concept)
        db.flush()
        db.add(NodeConcept(concept_id=concept.id, node_id=topic))
        db.commit()
    finally:
        db.close()

    promoted = client.post(
        f"/api/v1/courses/{scratch_id}/nodes/{topic}/promote",
        json={"title": "Abstract Algebra", "subject": "Mathematics"},
    )
    assert promoted.status_code == 200, promoted.text
    new_course = promoted.json()
    assert new_course["origin"] == "manual"
    assert new_course["hidden"] is False
    new_id = int(new_course["id"])

    visible = client.get("/api/v1/courses").json()
    assert any(course["id"] == new_id for course in visible)
    assert all(course["id"] != scratch_id for course in visible)

    new_root = root_node(client, new_id)
    tree = client.get(f"/api/v1/courses/{new_id}/tree").json()
    root_entry = next(entry for entry in tree if int(entry["id"]) == new_root)
    moved_titles = {
        node["title"]: node for entry in tree for node in _flatten(entry)
    }
    assert set(moved_titles) >= {"Group theory", "Cyclic groups"}
    moved_topic = moved_titles["Group theory"]
    assert any(
        int(child["id"]) == int(moved_topic["id"]) for child in root_entry["children"]
    )
    child_titles = {
        child["title"] for child in moved_titles["Group theory"]["children"]
    }
    assert "Cyclic groups" in child_titles

    detail = client.get(f"/api/v1/materials/{material_id}").json()
    assert detail["material"]["course_id"] == new_id
    links = client.get(f"/api/v1/materials/{material_id}/links").json()
    assert all(link["course_id"] == new_id for link in links)

    db = db_factory()
    try:
        assert db.get(Note, int(note.json()["id"])).course_id == new_id
        chat_row = db.get(ChatSession, chat_id)
        assert chat_row is not None
        assert chat_row.course_id == new_id
        assert db.scalars(
            select(NodeConcept.id).where(NodeConcept.node_id == topic)
        ).first() is None
        scratch_notes = db.scalars(
            select(Note.id).where(Note.course_id == scratch_id)
        ).all()
        assert scratch_notes == []
    finally:
        db.close()

    scratch_after = get_scratch(client)
    assert scratch_after["course"]["id"] == scratch_id


def _flatten(entry: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [entry]
    for child in entry.get("children", []):
        nodes.extend(_flatten(child))
    return nodes


def test_promote_rejects_nodes_outside_the_scratchpad(client: TestClient) -> None:
    course_id = make_course(client, "Real course")
    node_id = make_node(client, course_id, root_node(client, course_id), "Chapter")
    response = client.post(
        f"/api/v1/courses/{course_id}/nodes/{node_id}/promote",
        json={"title": "Sneaky"},
    )
    assert response.status_code == 409


def test_shared_material_stays_owned_by_the_scratchpad(client: TestClient) -> None:
    scratch = get_scratch(client)["course"]
    scratch_id = int(scratch["id"])
    scratch_root = root_node(client, scratch_id)
    moved_node = make_node(client, scratch_id, scratch_root, "Moved topic")
    kept_node = make_node(client, scratch_id, scratch_root, "Kept topic")

    material = upload_text(client, scratch_id, "shared.md", "# shared")
    material_id = int(material["material"]["id"])
    for node_id in (moved_node, kept_node):
        assigned = client.post(
            f"/api/v1/nodes/{node_id}/materials", json={"material_id": material_id}
        )
        assert assigned.status_code in (200, 201), assigned.text

    promoted = client.post(
        f"/api/v1/courses/{scratch_id}/nodes/{moved_node}/promote",
        json={"title": "Promoted"},
    )
    assert promoted.status_code == 200, promoted.text

    detail = client.get(f"/api/v1/materials/{material_id}").json()
    assert detail["material"]["course_id"] == scratch_id
    links = client.get(f"/api/v1/materials/{material_id}/links").json()
    link_courses = {int(link["course_id"]) for link in links}
    assert link_courses == {scratch_id, int(promoted.json()["id"])}


def test_analytics_exclude_scratch_courses(client: TestClient) -> None:
    scratch = get_scratch(client)["course"]
    scratch_id = int(scratch["id"])
    normal_id = make_course(client, "Normal course")

    db_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    db = db_factory()
    try:
        for course_id, title in ((scratch_id, "scratch activity"), (normal_id, "normal activity")):
            activity = Activity(
                profile_id=1, course_id=course_id, type="quiz", title=title
            )
            db.add(activity)
            db.flush()
            question = Question(
                activity_id=activity.id,
                type="choice",
                stem=[{"type": "text", "md": "1+1?"}],
                options=[{"type": "text", "md": "2"}, {"type": "text", "md": "3"}],
                answer={"index": 0},
            )
            db.add(question)
            db.flush()
            attempt = Attempt(activity_id=activity.id, mode="practice")
            db.add(attempt)
            db.flush()
            db.add(Answer(attempt_id=attempt.id, question_id=question.id, correct=True))
            db.add(
                Exercise(
                    profile_id=1,
                    course_id=course_id,
                    title=f"card {course_id}",
                    kind="card_basic",
                )
            )
        db.commit()
        from app.services.platform.metrics import answer_rows, due_cards_count

        profile_rows = answer_rows(db, 1)
        assert {row.concept for row in profile_rows} == {"untagged"}
        rows = db.scalars(select(Activity.id).where(Activity.course_id == normal_id)).all()
        assert len(rows) == 1
        assert len(profile_rows) == 1
        assert due_cards_count(db, 1) == 1
        assert due_cards_count(db, 1, course_id=scratch_id) == 1
    finally:
        db.close()
