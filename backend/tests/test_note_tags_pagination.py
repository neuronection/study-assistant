import time
from typing import Any

from fastapi.testclient import TestClient


def create_note(
    client: TestClient,
    title: str,
    *,
    tags: list[str] | None = None,
    course_id: int,
) -> dict[str, Any]:
    body: dict[str, Any] = {"title": title, "body_md": "body", "course_id": course_id}
    if tags is not None:
        body["tags"] = tags
    created = client.post("/api/v1/notes", json=body)
    assert created.status_code == 201, created.text
    detail: dict[str, Any] = created.json()
    return detail


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def test_tags_normalized_and_roundtrip(client: TestClient) -> None:
    course_id = make_course(client)
    created = create_note(
        client, "Tagged", tags=["  Calculus ", "calculus", "EXAM", ""], course_id=course_id
    )
    assert created["tags"] == ["calculus", "exam"]

    updated = client.patch(
        f"/api/v1/notes/{created['id']}", json={"tags": ["Limits"]}
    ).json()
    assert updated["tags"] == ["limits"]

    cleared = client.patch(f"/api/v1/notes/{created['id']}", json={"tags": []}).json()
    assert cleared["tags"] == []


def test_tag_filter_and_summary(client: TestClient) -> None:
    make_course = client.post("/api/v1/courses", json={"title": "Tags"})
    course_id = make_course.json()["id"]
    create_note(client, "One", tags=["calculus", "exam"], course_id=course_id)
    create_note(client, "Two", tags=["calculus"], course_id=course_id)
    create_note(client, "Three", tags=["limits"], course_id=course_id)
    create_note(client, "Untagged", course_id=course_id)

    filtered = client.get(
        "/api/v1/notes", params={"tag": "calculus", "course_id": course_id}
    ).json()
    assert sorted(note["title"] for note in filtered["items"]) == ["One", "Two"]

    exact = client.get(
        "/api/v1/notes", params={"tag": "calc", "course_id": course_id}
    ).json()
    assert exact["items"] == []

    summary = client.get("/api/v1/notes/tags/list", params={"course_id": course_id}).json()
    assert summary == [
        {"tag": "calculus", "count": 2},
        {"tag": "exam", "count": 1},
        {"tag": "limits", "count": 1},
    ]


def test_pagination_cursor(client: TestClient) -> None:
    make_course = client.post("/api/v1/courses", json={"title": "Pages"})
    course_id = make_course.json()["id"]
    for index in range(7):
        create_note(client, f"Note {index:02d}", course_id=course_id)
        time.sleep(0.01)

    first = client.get(
        "/api/v1/notes", params={"course_id": course_id, "limit": 3}
    ).json()
    assert len(first["items"]) == 3
    assert first["next_cursor"] is not None

    second = client.get(
        "/api/v1/notes",
        params={"course_id": course_id, "limit": 3, "cursor": first["next_cursor"]},
    ).json()
    assert len(second["items"]) == 3
    titles = [note["title"] for note in first["items"] + second["items"]]
    assert len(set(titles)) == 6

    third = client.get(
        "/api/v1/notes",
        params={"course_id": course_id, "limit": 3, "cursor": second["next_cursor"]},
    ).json()
    assert len(third["items"]) == 1
    assert third["next_cursor"] is None

    bad = client.get(
        "/api/v1/notes", params={"course_id": course_id, "cursor": "not-a-date"}
    )
    assert bad.status_code == 422
