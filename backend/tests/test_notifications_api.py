from datetime import timedelta

from fastapi.testclient import TestClient

from app.domain.models import utcnow


def make_course(client: TestClient, title: str, exam_date: str | None = None) -> int:
    course_id = int(client.post("/api/v1/courses", json={"title": title}).json()["id"])
    if exam_date is not None:
        patched = client.patch(
            f"/api/v1/courses/{course_id}", json={"exam_date": exam_date}
        )
        assert patched.status_code == 200, patched.text
    return course_id


def make_card(client: TestClient, course_id: int, front: str) -> int:
    response = client.post(
        "/api/v1/flashcards",
        json={
            "kind": "basic",
            "front_md": front,
            "back_md": f"back {front}",
            "course_id": course_id,
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def make_plan_item(
    client: TestClient, course_id: int, title: str, due_date: str
) -> int:
    created = client.post(
        f"/api/v1/courses/{course_id}/plan",
        json={"title": title, "due_date": due_date},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def test_notifications_aggregate_shape_and_content(client: TestClient) -> None:
    with client:
        exam_day = (utcnow().date() + timedelta(days=5)).isoformat()
        calc = make_course(client, "Calculus", exam_date=exam_day)
        algebra = make_course(client, "Linear Algebra")
        make_card(client, calc, "card one")
        make_card(client, calc, "card two")
        make_card(client, algebra, "card three")
        today = utcnow().date().isoformat()
        yesterday = (utcnow().date() - timedelta(days=1)).isoformat()
        make_plan_item(client, calc, "overdue task", yesterday)
        make_plan_item(client, calc, "today task", today)

        body = client.get("/api/v1/notifications").json()
        assert body["due_cards"] == 3
        assert len(body["due_reviews"]) == 3
        assert {entry["course_title"] for entry in body["due_reviews"]} == {
            "Calculus",
            "Linear Algebra",
        }
        assert {entry["kind"] for entry in body["due_reviews"]} == {"card_basic"}

        assert body["plan_overdue_count"] == 1
        titles = {entry["title"]: entry for entry in body["plan_today"]}
        assert titles["overdue task"]["overdue"] is True
        assert titles["today task"]["overdue"] is False

        exams = body["exams"]
        assert len(exams) == 1
        assert exams[0]["course_title"] == "Calculus"
        assert exams[0]["days_left"] == 5
        assert exams[0]["exam_date"] == exam_day

        assert body["generated_at"]


def test_notifications_reviewed_cards_leave_the_queue(client: TestClient) -> None:
    with client:
        course = make_course(client, "Calculus")
        card_id = make_card(client, course, "only card")

        before = client.get("/api/v1/notifications").json()
        assert before["due_cards"] == 1

        reviewed = client.post(f"/api/v1/flashcards/{card_id}/review", json={"rating": 3})
        assert reviewed.status_code == 200

        after = client.get("/api/v1/notifications").json()
        assert after["due_cards"] == 0
        assert after["due_reviews"] == []


def test_notifications_done_plan_items_invisible(client: TestClient) -> None:
    with client:
        course = make_course(client, "Calculus")
        yesterday = (utcnow().date() - timedelta(days=1)).isoformat()
        item_id = make_plan_item(client, course, "done already", yesterday)

        before = client.get("/api/v1/notifications").json()
        assert before["plan_overdue_count"] == 1

        done = client.patch(
            f"/api/v1/courses/{course}/plan/{item_id}", json={"done": True}
        )
        assert done.status_code == 200, done.text

        after = client.get("/api/v1/notifications").json()
        assert after["plan_overdue_count"] == 0
        assert after["plan_today"] == []


def test_notifications_ignores_scratch_courses(client: TestClient) -> None:
    with client:
        scratch = int(client.get("/api/v1/courses/scratchpad").json()["course"]["id"])
        make_card(client, scratch, "scratch card")

        body = client.get("/api/v1/notifications").json()
        assert body["due_cards"] == 0
        assert body["due_reviews"] == []
