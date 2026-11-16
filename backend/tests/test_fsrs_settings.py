from fastapi.testclient import TestClient


def make_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Scheduler"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def make_card(client: TestClient, course_id: str) -> str:
    response = client.post(
        "/api/v1/flashcards",
        json={
            "kind": "card_basic",
            "front_md": "retention test",
            "back_md": "answer",
            "course_id": course_id,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_profile_fsrs_settings_round_trip(client: TestClient) -> None:
    defaults = client.get("/api/v1/study/fsrs")
    assert defaults.status_code == 200
    body = defaults.json()
    assert body["desired_retention"] == 0.9
    assert body["maximum_interval_days"] == 365
    assert body["new_per_day"] == 20

    updated = client.put(
        "/api/v1/study/fsrs",
        json={"desired_retention": 0.85, "maximum_interval_days": 90, "new_per_day": 5},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["desired_retention"] == 0.85
    assert client.get("/api/v1/study/fsrs").json()["maximum_interval_days"] == 90

    invalid = client.put("/api/v1/study/fsrs", json={"desired_retention": 0.99})
    assert invalid.status_code == 422


def test_course_override_inherits_and_clears(client: TestClient) -> None:
    course_id = make_course(client)
    inherited = client.get(f"/api/v1/study/courses/{course_id}/fsrs")
    assert inherited.status_code == 200
    assert inherited.json()["inherited"] is True

    updated = client.put(
        f"/api/v1/study/courses/{course_id}/fsrs",
        json={"desired_retention": 0.95, "leech_action": "suspend"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["inherited"] is False
    assert updated.json()["desired_retention"] == 0.95
    assert updated.json()["leech_action"] == "suspend"

    cleared = client.delete(f"/api/v1/study/courses/{course_id}/fsrs")
    assert cleared.status_code == 204
    assert client.get(f"/api/v1/study/courses/{course_id}/fsrs").json()["inherited"] is True


def test_lower_retention_schedules_further_out(client: TestClient) -> None:
    course_id = make_course(client)
    first = make_card(client, course_id)
    second = make_card(client, course_id)

    base = client.post(f"/api/v1/flashcards/{first}/review", json={"rating": 3}).json()
    client.put("/api/v1/study/fsrs", json={"desired_retention": 0.70})
    relaxed = client.post(f"/api/v1/flashcards/{second}/review", json={"rating": 3}).json()

    assert relaxed["interval_days"] >= base["interval_days"]
    assert relaxed["interval_days"] != base["interval_days"]
