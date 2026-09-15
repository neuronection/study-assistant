from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.models import Attempt, utcnow


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Calculus"}).json()["id"])


def make_quiz(
    client: TestClient, course_id: int, title: str, limit_sec: int | None
) -> int:
    imported = client.post(
        "/api/v1/quiz/import",
        params={"course_id": course_id, "dry_run": False},
        json={
            "title": title,
            "questions": [
                {
                    "type": "text",
                    "stem_md": "Derivative of x^2?",
                    "answer": {"value": "2x"},
                    "explanation_md": "power rule",
                }
            ],
        },
    )
    assert imported.status_code == 200, imported.text
    activity_id = int(imported.json()["activity"]["id"])
    updated = client.patch(
        f"/api/v1/quiz/activities/{activity_id}/time-limit",
        json={"time_limit_sec": limit_sec},
    )
    assert updated.status_code == 200, updated.text
    return activity_id


def start_attempt(client: TestClient, activity_id: int) -> dict[str, Any]:
    started = client.post(f"/api/v1/quiz/activities/{activity_id}/attempts")
    assert started.status_code == 201
    result: dict[str, Any] = started.json()
    return result


def first_question_id(client: TestClient, activity_id: int) -> int:
    questions = client.get(f"/api/v1/quiz/activities/{activity_id}/questions").json()
    return int(questions[0]["id"])


def shift_deadline(
    client: TestClient, attempt_id: int, *, past_seconds: int
) -> None:
    settings = client.app.state.settings  # type: ignore[attr-defined]
    db_path = settings.db_path
    engine = create_engine(f"sqlite:///{db_path}")
    with sessionmaker(bind=engine)() as session:
        attempt = session.get(Attempt, attempt_id)
        assert attempt is not None
        attempt.deadline_at = utcnow() - timedelta(seconds=past_seconds)
        session.commit()
    engine.dispose()


def test_deadline_set_on_start_untimed_has_none(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        timed = make_quiz(client, course_id, "Timed", 600)
        untimed = make_quiz(client, course_id, "Untimed", None)

        started = start_attempt(client, timed)
        assert started["deadline_at"] is not None
        assert started["finished_at"] is None

        plain = start_attempt(client, untimed)
        assert plain["deadline_at"] is None


def test_answer_after_expiry_rejected_auto_submitted_and_swept(
    client: TestClient,
) -> None:
    with client:
        course_id = make_course(client)
        activity_id = make_quiz(client, course_id, "Timed", 600)
        question_id = first_question_id(client, activity_id)

        started = start_attempt(client, activity_id)
        attempt_id = int(started["id"])

        graded = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/answers",
            json={"question_id": question_id, "response": "2x"},
        )
        assert graded.status_code == 200

        shift_deadline(client, attempt_id, past_seconds=30)

        closed = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/answers",
            json={"question_id": question_id, "response": "2x"},
        )
        assert closed.status_code == 422
        assert closed.json()["detail"] == "attempt_closed"

        swept = client.get(f"/api/v1/quiz/attempts/{attempt_id}/report").json()
        assert swept["attempt"]["finished_at"] is not None
        assert swept["attempt"]["finished_at"] == swept["attempt"]["deadline_at"]

        still_locked = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/answers",
            json={"question_id": question_id, "response": "2x"},
        )
        assert still_locked.status_code == 422


def test_finish_after_expiry_keeps_deadline_as_finish_time(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        activity_id = make_quiz(client, course_id, "Timed", 60)
        started = start_attempt(client, activity_id)
        attempt_id = int(started["id"])

        shift_deadline(client, attempt_id, past_seconds=10)

        finished = client.post(f"/api/v1/quiz/attempts/{attempt_id}/finish").json()
        assert finished["finished_at"] == finished["deadline_at"]
        assert finished["score"] is not None


def test_hint_after_expiry_closes_attempt(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        activity_id = make_quiz(client, course_id, "Timed", 60)
        question_id = first_question_id(client, activity_id)

        started = start_attempt(client, activity_id)
        attempt_id = int(started["id"])

        shift_deadline(client, attempt_id, past_seconds=5)

        hint = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/questions/{question_id}/hint",
            json={"level": 1},
        )
        assert hint.status_code == 422
        assert hint.json()["detail"] == "attempt_closed"


def test_time_limit_endpoint_validation_and_clear(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        activity_id = make_quiz(client, course_id, "Timed", 600)

        invalid = client.patch(
            f"/api/v1/quiz/activities/{activity_id}/time-limit",
            json={"time_limit_sec": 10},
        )
        assert invalid.status_code == 422

        cleared = client.patch(
            f"/api/v1/quiz/activities/{activity_id}/time-limit",
            json={"time_limit_sec": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["time_limit_sec"] is None

        started = start_attempt(client, activity_id)
        assert started["deadline_at"] is None


def test_exam_mode_help_lock_regression(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        activity_id = make_quiz(client, course_id, "Exam", None)
        question_id = first_question_id(client, activity_id)

        started = client.post(
            f"/api/v1/quiz/activities/{activity_id}/attempts",
            params={"mode": "exam"},
        ).json()

        hint = client.post(
            f"/api/v1/quiz/attempts/{started['id']}/questions/{question_id}/hint",
            json={"level": 1},
        )
        assert hint.status_code == 422
        assert "exam" in hint.json()["detail"]
