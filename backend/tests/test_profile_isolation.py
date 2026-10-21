"""Cross-profile read isolation (plan 81 E, ADR-201).

Every user-data table is profile-scoped by FK or a documented derivation.
This is the request-boundary proof: a second profile sees none of the first
profile's courses, notes, materials, exercises, plan items, chat history or
trash — list endpoints are filtered and direct reads are 404.
"""

from fastapi.testclient import TestClient


def _second_profile(client: TestClient) -> dict[str, str]:
    created = client.post("/api/v1/profiles", json={"name": "Other learner"})
    assert created.status_code == 201, created.text
    return {"X-Profile-Id": str(created.json()["id"])}


def _ids(payload: object) -> set[str]:
    entries = payload.get("items", []) if isinstance(payload, dict) else payload
    assert isinstance(entries, list)
    return {str(entry["id"]) for entry in entries if isinstance(entry, dict) and "id" in entry}


def test_second_profile_cannot_read_first_profiles_data(client: TestClient) -> None:
    course = client.post("/api/v1/courses", json={"title": "Private calculus"})
    assert course.status_code == 201, course.text
    course_id = str(course.json()["id"])
    root_id = str(client.get(f"/api/v1/courses/{course_id}/tree").json()[0]["id"])

    note = client.post(
        "/api/v1/notes",
        json={"title": "Private note", "course_id": course_id, "node_id": root_id},
    )
    assert note.status_code == 201, note.text
    note_id = str(note.json()["id"])

    exercise = client.post(
        "/api/v1/exercises",
        json={
            "title": "Private exercise",
            "course_id": course_id,
            "steps": [{"prompt_md": "Differentiate $x^2$"}],
        },
    )
    assert exercise.status_code == 201, exercise.text
    exercise_id = str(exercise.json()["id"])

    plan = client.post(
        f"/api/v1/courses/{course_id}/plan",
        json={"title": "Private plan item", "due_date": "2026-12-01"},
    )
    assert plan.status_code == 201, plan.text

    material = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("private.txt", b"private material", "text/plain")},
    )
    assert material.status_code == 200, material.text
    material_id = str(material.json()["material"]["id"])

    chat = client.post("/api/v1/chat/sessions", json={"course_id": course_id})
    assert chat.status_code == 201, chat.text
    chat_id = str(chat.json()["id"])

    other = _second_profile(client)

    assert _ids(client.get("/api/v1/courses", headers=other).json()) == set()
    assert client.get(f"/api/v1/courses/{course_id}", headers=other).status_code == 404
    assert client.get(f"/api/v1/courses/{course_id}/tree", headers=other).status_code == 404
    assert client.get(f"/api/v1/courses/{course_id}/plan", headers=other).json() == []

    assert _ids(client.get("/api/v1/notes", headers=other).json()) == set()
    assert client.get(f"/api/v1/notes/{note_id}", headers=other).status_code == 404

    assert client.get(f"/api/v1/materials/{material_id}", headers=other).status_code == 404
    assert _ids(client.get("/api/v1/materials", headers=other).json()) == set()

    assert client.get(f"/api/v1/exercises/{exercise_id}", headers=other).status_code == 404
    assert _ids(client.get("/api/v1/exercises", headers=other).json()) == set()

    assert _ids(client.get("/api/v1/chat/sessions", headers=other).json()) == set()
    assert client.get(f"/api/v1/chat/sessions/{chat_id}/messages", headers=other).status_code == 404

    assert client.get("/api/v1/deleted-items", headers=other).json() == []
    assert _ids(client.get("/api/v1/plan/upcoming?days=400", headers=other).json()) == set()

    assert course_id in _ids(client.get("/api/v1/courses").json())
    assert note_id in _ids(client.get("/api/v1/notes").json())
