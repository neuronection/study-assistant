from fastapi.testclient import TestClient


def make_course(client: TestClient, title: str) -> str:
    return str(client.post("/api/v1/courses", json={"title": title}).json()["id"])


def make_card(
    client: TestClient,
    course_id: str,
    front: str,
    node_id: str | None = None,
) -> str:
    response = client.post(
        "/api/v1/flashcards",
        json={
            "kind": "card_basic",
            "front_md": front,
            "back_md": f"back of {front}",
            "course_id": course_id,
            "node_id": node_id,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


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

        reviewed = client.post(f"/api/v1/flashcards/{card_id}/review", json={"rating": 3})
        assert reviewed.status_code == 200
        assert reviewed.json()["interval_days"] > 0

        body = client.get("/api/v1/review/due").json()
        assert body["total_due"] == 0
        assert body["groups"] == []


def test_review_honors_an_offline_reviewed_at(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    with client:
        course = make_course(client, "Offline")
        card = make_card(client, course, "offline review")
        two_days_ago = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        accepted = client.post(
            f"/api/v1/flashcards/{card}/review",
            json={"rating": 3, "reviewed_at": two_days_ago},
        )
        assert accepted.status_code == 200, accepted.text

        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        rejected = client.post(
            f"/api/v1/flashcards/{card}/review",
            json={"rating": 3, "reviewed_at": future},
        )
        assert rejected.status_code == 422

        too_old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
        stale = client.post(
            f"/api/v1/flashcards/{card}/review",
            json={"rating": 3, "reviewed_at": too_old},
        )
        assert stale.status_code == 422


def test_review_filters_and_preview(client: TestClient) -> None:
    with client:
        course = make_course(client, "Filtered")
        first = make_card(client, course, "first filter card")
        make_card(client, course, "second filter card")

        no_filter = client.get("/api/v1/review/due").json()
        assert no_filter["total_due"] == 2
        assert no_filter["preview"] is False

        saved = client.post(
            "/api/v1/review/filters",
            json={
                "name": "Ahead",
                "course_id": course,
                "include_not_due": True,
                "due_window_days": 7,
                "limit": 1,
            },
        )
        assert saved.status_code == 201, saved.text
        filter_id = saved.json()["id"]
        listed = client.get("/api/v1/review/filters").json()
        assert [row["id"] for row in listed] == [filter_id]

        ahead = client.get(
            "/api/v1/review/due", params={"filter_id": filter_id}
        ).json()
        assert ahead["preview"] is True
        assert len(ahead["groups"][0]["cards"]) == 1

        previewed = client.post(
            f"/api/v1/review/preview/{first}", json={"rating": 3}
        )
        assert previewed.status_code == 200
        unchanged = client.get("/api/v1/review/due").json()
        assert unchanged["total_due"] == 2

        removed = client.delete(f"/api/v1/review/filters/{filter_id}")
        assert removed.status_code == 204
        assert client.get("/api/v1/review/filters").json() == []


def test_review_cap_reports_capped(client: TestClient) -> None:
    with client:
        course = make_course(client, "Capped")
        make_card(client, course, "cap one")
        second = make_card(client, course, "cap two")
        client.put("/api/v1/study/fsrs", json={"reviews_per_day": 1})
        client.post(f"/api/v1/flashcards/{second}/review", json={"rating": 3})
        body = client.get("/api/v1/review/due").json()
        assert body["capped"] is True
        assert body["remaining_today"] == 0
        assert body["total_due"] == 0
