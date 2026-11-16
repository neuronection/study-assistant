from fastapi.testclient import TestClient


def make_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Retention"})
    assert response.status_code == 201
    return str(response.json()["id"])


def make_card(client: TestClient, course_id: str, front: str) -> str:
    response = client.post(
        "/api/v1/flashcards",
        json={
            "kind": "card_basic",
            "front_md": front,
            "back_md": "answer",
            "course_id": course_id,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_retention_and_workload_report_honest_numbers(client: TestClient) -> None:
    course = make_course(client)
    good = make_card(client, course, "good card")
    again = make_card(client, course, "again card")
    make_card(client, course, "new card")

    assert client.post(f"/api/v1/flashcards/{good}/review", json={"rating": 3}).status_code == 200
    assert client.post(f"/api/v1/flashcards/{again}/review", json={"rating": 1}).status_code == 200

    retention = client.get("/api/v1/analytics/retention")
    assert retention.status_code == 200
    body = retention.json()
    assert body["reviews"] == 2
    assert body["correct"] == 1
    assert body["retention"] == 0.5
    assert body["lapses"] == 1
    assert body["target"] == 0.9
    young = next(entry for entry in body["buckets"] if entry["key"] == "young")
    assert young["reviews"] == 2
    assert young["retention"] == 0.5

    workload = client.get("/api/v1/analytics/workload")
    assert workload.status_code == 200
    data = workload.json()
    assert data["new_available"] == 1
    assert len(data["days"]) == 30
    assert data["total"] >= 1
    assert data["peak_day"] is not None


def test_retention_is_empty_without_reviews(client: TestClient) -> None:
    body = client.get("/api/v1/analytics/retention").json()
    assert body["reviews"] == 0
    assert body["retention"] is None
