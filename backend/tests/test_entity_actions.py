import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, make_course

from app.core.config import Settings
from app.domain.models import (
    Activity,
    Answer,
    Attempt,
    ChatMessage,
    ChatProposal,
    Exercise,
    ExerciseStep,
    ItemStat,
    Mistake,
    Question,
    ReviewLog,
)
from app.main import create_app


@fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, FastAPI, ScriptedGateway]]:
    gateway = ScriptedGateway(["See [1]."])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, app, gateway


def wait_for_assistant(
    client: TestClient, session_id: int, timeout: float = 5.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages: list[dict[str, Any]] = client.get(
            f"/api/v1/chat/sessions/{session_id}/messages"
        ).json()
        if messages and messages[-1]["role"] == "assistant":
            return
        time.sleep(0.05)
    raise AssertionError("assistant never replied")


def make_chat_with_messages(
    client: TestClient, app: FastAPI, gateway: ScriptedGateway, course_id: int
) -> int:
    session = client.post(
        "/api/v1/chat/sessions", json={"course_id": course_id, "title": "Old title"}
    ).json()
    client.post(
        f"/api/v1/chat/sessions/{session['id']}/messages", json={"content": "hello"}
    )
    wait_for_assistant(client, session["id"])
    db = app.state.session_factory()
    message = db.query(ChatMessage).filter(ChatMessage.role == "assistant").first()
    db.add(
        ChatProposal(
            message_id=message.id, action="create_note", payload={}, status="dismissed"
        )
    )
    db.commit()
    db.close()
    return int(session["id"])


def make_quiz_with_history(app: FastAPI, course_id: int) -> int:
    db = app.state.session_factory()
    activity = Activity(
        profile_id=1, course_id=course_id, type="quiz", title="Old quiz title"
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
    db.add(Answer(attempt_id=attempt.id, question_id=question.id, correct=False))
    db.add(Mistake(profile_id=1, question_id=question.id))
    db.add(ItemStat(question_id=question.id, n_attempts=3, p_correct=0.5))
    db.commit()
    activity_id = activity.id
    db.close()
    return activity_id


def make_exercise_with_reviews(app: FastAPI, course_id: int) -> int:
    db = app.state.session_factory()
    exercise = Exercise(
        profile_id=1, course_id=course_id, title="Old exercise title", kind="multi_step"
    )
    db.add(exercise)
    db.flush()
    db.add(
        ExerciseStep(
            exercise_id=exercise.id,
            order_idx=0,
            prompt=[{"type": "text", "md": "step"}],
            expected={"answer": "1"},
        )
    )
    db.add(
        ReviewLog(card_id=exercise.id, rating=3, interval_days=1, elapsed_days=0)
    )
    db.commit()
    exercise_id = exercise.id
    db.close()
    return exercise_id


def table_count(app: FastAPI, model: type, **filters: Any) -> int:
    from sqlalchemy import Select, select

    db = app.state.session_factory()
    try:
        statement: Select[Any] = select(model)
        for column, value in filters.items():
            statement = statement.where(getattr(model, column) == value)
        return len(db.scalars(statement).all())
    finally:
        db.close()


def test_chat_session_rename_and_delete_cascades(
    client: tuple[TestClient, FastAPI, ScriptedGateway],
) -> None:
    test_client, app, gateway = client
    with test_client:
        course_id = make_course(test_client)
        session_id = make_chat_with_messages(test_client, app, gateway, course_id)
        renamed = test_client.patch(
            f"/api/v1/chat/sessions/{session_id}", json={"title": "Renamed chat"}
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["title"] == "Renamed chat"
        assert test_client.patch(
            "/api/v1/chat/sessions/999", json={"title": "x"}
        ).status_code == 404
        assert table_count(app, ChatMessage, session_id=session_id) == 2
        assert table_count(app, ChatProposal) == 1
        deleted = test_client.delete(f"/api/v1/chat/sessions/{session_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted_item_id"] > 0
        assert table_count(app, ChatMessage, session_id=session_id) == 0
        assert table_count(app, ChatProposal) == 0
        assert test_client.delete(f"/api/v1/chat/sessions/{session_id}").status_code == 404


def test_quiz_rename_and_delete_cleans_history(
    client: tuple[TestClient, FastAPI, ScriptedGateway],
) -> None:
    test_client, app, _gateway = client
    with test_client:
        course_id = make_course(test_client)
        activity_id = make_quiz_with_history(app, course_id)
        renamed = test_client.patch(
            f"/api/v1/quiz/activities/{activity_id}", json={"title": "Renamed quiz"}
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["title"] == "Renamed quiz"
        assert renamed.json()["question_count"] == 1
        assert test_client.patch(
            "/api/v1/quiz/activities/999", json={"title": "x"}
        ).status_code == 404
        assert table_count(app, Question, activity_id=activity_id) == 1
        assert table_count(app, Attempt, activity_id=activity_id) == 1
        assert table_count(app, Mistake) == 1
        assert table_count(app, ItemStat) == 1
        deleted = test_client.delete(f"/api/v1/quiz/activities/{activity_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted_item_id"] > 0
        assert table_count(app, Question, activity_id=activity_id) == 0
        assert table_count(app, Attempt, activity_id=activity_id) == 0
        assert table_count(app, Mistake) == 0
        assert table_count(app, ItemStat) == 0
        assert test_client.delete(f"/api/v1/quiz/activities/{activity_id}").status_code == 404


def test_exercise_rename_and_delete_cleans_reviews(
    client: tuple[TestClient, FastAPI, ScriptedGateway],
) -> None:
    test_client, app, _gateway = client
    with test_client:
        course_id = make_course(test_client)
        exercise_id = make_exercise_with_reviews(app, course_id)
        renamed = test_client.patch(
            f"/api/v1/exercises/{exercise_id}", json={"title": "Renamed exercise"}
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["title"] == "Renamed exercise"
        assert renamed.json()["step_count"] == 1
        assert test_client.patch(
            "/api/v1/exercises/999", json={"title": "x"}
        ).status_code == 404
        assert table_count(app, ExerciseStep, exercise_id=exercise_id) == 1
        assert table_count(app, ReviewLog, card_id=exercise_id) == 1
        deleted = test_client.delete(f"/api/v1/exercises/{exercise_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted_item_id"] > 0
        assert table_count(app, ExerciseStep, exercise_id=exercise_id) == 0
        assert table_count(app, ReviewLog, card_id=exercise_id) == 0
        assert test_client.delete(f"/api/v1/exercises/{exercise_id}").status_code == 404
