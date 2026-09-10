from typing import Any

from fastapi.testclient import TestClient

CAQ_DOC = {
    "$schema": "caq/v1",
    "title": "Scoped quiz",
    "questions": [
        {
            "id": "q1",
            "type": "single",
            "stem_md": "Derivative of $x^2$?",
            "options_md": ["$2x$", "$x$", "$x^2$"],
            "answer": {"index": 0},
            "explanation_md": "Power rule gives $2x$.",
            "concepts": ["derivatives"],
            "skill": "procedural",
            "bloom": "apply",
            "difficulty": 1,
            "expected_time_sec": 30,
            "misconceptions": {"1": "wrong_power_rule"},
        }
    ],
}


def make_course(client: TestClient, title: str) -> int:
    response = client.post("/api/v1/courses", json={"title": title})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def import_quiz(client: TestClient, course_id: int) -> dict[str, Any]:
    response = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": course_id},
        json=CAQ_DOC,
    )
    assert response.status_code == 200, response.text
    activity: dict[str, Any] = response.json()["activity"]
    return activity


def answer_wrong(client: TestClient, activity_id: int) -> None:
    questions = client.get(f"/api/v1/quiz/activities/{activity_id}/questions").json()
    attempt = client.post(f"/api/v1/quiz/activities/{activity_id}/attempts").json()
    response = client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[0]["id"], "response": 1},
    )
    assert response.status_code == 200


def test_quiz_lists_scope_by_course(client: TestClient) -> None:
    course_a = make_course(client, "Calculus")
    course_b = make_course(client, "Algebra")
    quiz_a = import_quiz(client, course_a)
    quiz_b = import_quiz(client, course_b)

    all_quizzes = client.get("/api/v1/quiz/activities").json()
    assert len(all_quizzes) == 2

    scoped = client.get("/api/v1/quiz/activities", params={"course_id": course_a}).json()
    assert [quiz["id"] for quiz in scoped] == [quiz_a["id"]]
    assert scoped[0]["course_id"] == course_a

    scoped_b = client.get("/api/v1/quiz/activities", params={"course_id": course_b}).json()
    assert [quiz["id"] for quiz in scoped_b] == [quiz_b["id"]]


def test_import_binds_course(client: TestClient) -> None:
    course = make_course(client, "Calculus")
    activity = import_quiz(client, course)
    assert activity["course_id"] == course

    missing = client.post("/api/v1/quiz/import", params={"dry_run": "false"}, json=CAQ_DOC)
    assert missing.status_code == 422


def test_attempts_and_mistakes_scope_by_course(client: TestClient) -> None:
    course_a = make_course(client, "Calculus")
    course_b = make_course(client, "Algebra")
    quiz_a = import_quiz(client, course_a)
    quiz_b = import_quiz(client, course_b)
    answer_wrong(client, quiz_a["id"])
    answer_wrong(client, quiz_b["id"])

    all_attempts = client.get("/api/v1/quiz/attempts").json()
    assert len(all_attempts) == 2

    attempts_a = client.get("/api/v1/quiz/attempts", params={"course_id": course_a}).json()
    assert len(attempts_a) == 1
    assert attempts_a[0]["activity_id"] == quiz_a["id"]

    mistakes = client.get("/api/v1/quiz/mistakes").json()
    assert len(mistakes) == 2
    mistakes_a = client.get("/api/v1/quiz/mistakes", params={"course_id": course_a}).json()
    assert len(mistakes_a) == 1
    assert mistakes_a[0]["activity_id"] == quiz_a["id"]


def test_exercises_and_flashcards_scope_by_course(client: TestClient) -> None:
    course_a = make_course(client, "Calculus")
    course_b = make_course(client, "Algebra")
    for course_id in (course_a, course_b):
        created = client.post(
            "/api/v1/exercises",
            json={
                "title": f"Exercise {course_id}",
                "course_id": course_id,
                "steps": [{"prompt_md": "Differentiate.", "expected": {"value": "2x"}}],
            },
        )
        assert created.status_code == 201, created.text
        card = client.post(
            "/api/v1/flashcards",
            json={
                "kind": "basic",
                "front_md": f"F {course_id}",
                "back_md": "B",
                "course_id": course_id,
            },
        )
        assert card.status_code == 201, card.text

    exercises_a = client.get("/api/v1/exercises", params={"course_id": course_a}).json()
    assert len(exercises_a) == 1
    assert exercises_a[0]["course_id"] == course_a

    cards_a = client.get("/api/v1/flashcards", params={"course_id": course_a}).json()
    assert len(cards_a) == 1

    due_a = client.get("/api/v1/flashcards/due", params={"course_id": course_a}).json()
    assert [card["id"] for card in due_a] == [cards_a[0]["id"]]

    due_all = client.get("/api/v1/flashcards/due").json()
    assert len(due_all) == 2


def test_notes_scope_by_course(client: TestClient) -> None:
    course_a = make_course(client, "Calculus")
    course_b = make_course(client, "Algebra")
    for course_id in (course_a, course_b):
        created = client.post(
            "/api/v1/notes", json={"title": f"Note {course_id}", "course_id": course_id}
        )
        assert created.status_code == 201, created.text

    notes_a = client.get("/api/v1/notes", params={"course_id": course_a}).json()
    assert len(notes_a["items"]) == 1
    assert notes_a["items"][0]["course_id"] == course_a
    assert len(client.get("/api/v1/notes").json()["items"]) == 2


def test_analytics_scope_by_course(client: TestClient) -> None:
    course_a = make_course(client, "Calculus")
    course_b = make_course(client, "Algebra")
    quiz_a = import_quiz(client, course_a)
    answer_wrong(client, quiz_a["id"])
    answer_wrong(client, quiz_a["id"])

    diagnostics_all = client.get("/api/v1/analytics/diagnostics").json()
    assert len(diagnostics_all["weakness_matrix"]) == 1
    assert len(diagnostics_all["error_profile"]) == 1

    diagnostics_a = client.get(
        "/api/v1/analytics/diagnostics", params={"course_id": course_a}
    ).json()
    assert len(diagnostics_a["weakness_matrix"]) == 1

    diagnostics_b = client.get(
        "/api/v1/analytics/diagnostics", params={"course_id": course_b}
    ).json()
    assert diagnostics_b["weakness_matrix"] == []
    assert diagnostics_b["error_profile"] == []

    recommendations_b = client.get(
        "/api/v1/analytics/recommendations", params={"course_id": course_b}
    ).json()
    assert recommendations_b == []

    card = client.post(
        "/api/v1/flashcards",
        json={"kind": "basic", "front_md": "F", "back_md": "B", "course_id": course_b},
    )
    assert card.status_code == 201
    recommendations_b = client.get(
        "/api/v1/analytics/recommendations", params={"course_id": course_b}
    ).json()
    assert [rec["kind"] for rec in recommendations_b] == ["review"]

    recommendations_a = client.get(
        "/api/v1/analytics/recommendations", params={"course_id": course_a}
    ).json()
    assert all(rec["kind"] != "review" for rec in recommendations_a)
