from fastapi.testclient import TestClient


def make_course(client: TestClient, title: str) -> int:
    return int(client.post("/api/v1/courses", json={"title": title}).json()["id"])


def make_card(
    client: TestClient,
    course_id: int,
    front: str,
    node_id: int | None = None,
) -> int:
    response = client.post(
        "/api/v1/flashcards",
        json={
            "kind": "basic",
            "front_md": front,
            "back_md": f"back of {front}",
            "course_id": course_id,
            "node_id": node_id,
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_review_due_groups_by_course(client: TestClient) -> None:
    with client:
        calc = make_course(client, "Calculus")
        algebra = make_course(client, "Linear Algebra")
        make_card(client, calc, "derivative of x^2")
        make_card(client, calc, "derivative of sin")
        make_card(client, algebra, "definition of eigenvalue")

        body = client.get("/api/v1/review/due").json()
        assert body["total_due"] == 3
        titles = {group["course_title"]: group for group in body["groups"]}
        assert set(titles) == {"Calculus", "Linear Algebra"}
        assert titles["Calculus"]["due_count"] == 2
        assert len(titles["Calculus"]["cards"]) == 2
        assert titles["Calculus"]["cards"][0]["front"][0]["md"] == "derivative of x^2"
        assert titles["Linear Algebra"]["due_count"] == 1


def test_review_due_groups_are_sorted_by_due_count(client: TestClient) -> None:
    with client:
        small = make_course(client, "Small")
        big = make_course(client, "Big")
        make_card(client, small, "small card")
        for index in range(3):
            make_card(client, big, f"big card {index}")

        body = client.get("/api/v1/review/due").json()
        assert [group["course_title"] for group in body["groups"]] == ["Big", "Small"]
        assert body["groups"][0]["due_count"] == 3


def test_review_due_per_course_limit_caps_first_batch(client: TestClient) -> None:
    with client:
        course = make_course(client, "Calculus")
        for index in range(4):
            make_card(client, course, f"card {index}")

        body = client.get("/api/v1/review/due", params={"per_course": 2}).json()
        assert body["total_due"] == 4
        assert body["groups"][0]["due_count"] == 4
        assert len(body["groups"][0]["cards"]) == 2


def test_review_due_excludes_scratch_and_reviewed_cards(client: TestClient) -> None:
    with client:
        course = make_course(client, "Calculus")
        card_id = make_card(client, course, "due card")

        empty = client.get("/api/v1/review/due").json()
        assert empty["total_due"] == 1

        reviewed = client.post(
            f"/api/v1/flashcards/{card_id}/review", json={"rating": 3}
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["interval_days"] > 0

        body = client.get("/api/v1/review/due").json()
        assert body["total_due"] == 0
        assert body["groups"] == []
