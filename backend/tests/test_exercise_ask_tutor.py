import contextlib
import json
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, make_course

from app.core.config import Settings
from app.domain.models import Exercise, ExerciseSession, ExerciseStep, Profile
from app.main import create_app


@contextlib.contextmanager
def make_client(responses: list[str]) -> Iterator[tuple[TestClient, FastAPI, ScriptedGateway]]:
    gateway = ScriptedGateway(responses)
    app = create_app(
        Settings(data_dir=Path(tempfile.mkdtemp()), log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client, app, gateway


def wait_for_assistant(
    client: TestClient, session_id: int, timeout: float = 5.0
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages: list[dict[str, Any]] = client.get(
            f"/api/v1/chat/sessions/{session_id}/messages"
        ).json()
        if messages and messages[-1]["role"] == "assistant":
            return messages
        time.sleep(0.05)
    raise AssertionError("assistant never replied")


def make_exercise(app: FastAPI, course_id: int) -> int:
    db = app.state.session_factory()
    profile_id = db.query(Profile).first().id
    exercise = Exercise(
        profile_id=profile_id,
        course_id=course_id,
        title="Derivative drill",
        kind="multi_step",
    )
    db.add(exercise)
    db.flush()
    db.add(
        ExerciseStep(
            exercise_id=exercise.id,
            order_idx=0,
            prompt=[{"type": "text", "md": "Differentiate $x^2$."}],
            expected={"kind": "math", "value": "2x"},
        )
    )
    db.commit()
    exercise_id = exercise.id
    db.close()
    return exercise_id


def start_session(client: TestClient, exercise_id: int) -> int:
    return int(
        client.post(f"/api/v1/exercises/{exercise_id}/sessions").json()["id"]
    )


def test_ask_creates_bound_chat_with_pending_answer_and_guard() -> None:
    with make_client(["Let me look at your attempt [1]."]) as (client, app, gateway):
        course_id = make_course(client)
        exercise_id = make_exercise(app, course_id)
        session_id = start_session(client, exercise_id)
        asked = client.post(
            f"/api/v1/exercises/sessions/{session_id}/ask",
            json={"pending_answer": "2*x^2"},
        )
        assert asked.status_code == 201, asked.text
        chat_id = asked.json()["chat_session_id"]
        messages = client.get(f"/api/v1/chat/sessions/{chat_id}/messages").json()
        assert messages[0]["role"] == "user"
        assert "Differentiate $x^2$." in messages[0]["markdown"]
        assert "$$2*x^2$$" in messages[0]["markdown"]
        client.post(
            f"/api/v1/chat/sessions/{chat_id}/messages", json={"content": "am I close?"}
        )
        wait_for_assistant(client, chat_id)
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert "step 1 of 1" in prompt
        assert "The student's current (not yet submitted) answer:\n$$2*x^2$$" in prompt
        assert "Submitted attempts on this step: none yet" in prompt
        assert "Do NOT reveal" in prompt


def test_ask_again_updates_pending_answer_same_chat() -> None:
    with make_client(["First reply [1].", "Second reply [1]."]) as (client, app, _gateway):
        course_id = make_course(client)
        exercise_id = make_exercise(app, course_id)
        session_id = start_session(client, exercise_id)
        first = client.post(
            f"/api/v1/exercises/sessions/{session_id}/ask",
            json={"pending_answer": "x^3"},
        ).json()
        second = client.post(
            f"/api/v1/exercises/sessions/{session_id}/ask",
            json={"pending_answer": "3x^2 oops"},
        )
        assert second.status_code == 201
        assert second.json()["chat_session_id"] == first["chat_session_id"]
        db = app.state.session_factory()
        rows = db.query(ExerciseSession).count()
        assert rows == 1
        db.close()


def test_guard_lifted_after_correct_submission() -> None:
    with make_client(["Check the sign [1].", "Solved, nice work."]) as (
        client,
        app,
        gateway,
    ):
        course_id = make_course(client)
        exercise_id = make_exercise(app, course_id)
        session_id = start_session(client, exercise_id)
        asked = client.post(
            f"/api/v1/exercises/sessions/{session_id}/ask",
            json={"pending_answer": None},
        ).json()
        chat_id = asked["chat_session_id"]
        client.post(
            f"/api/v1/chat/sessions/{chat_id}/messages", json={"content": "help"}
        )
        wait_for_assistant(client, chat_id)
        first_prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert "Do NOT reveal" in first_prompt
        submitted = client.post(
            f"/api/v1/exercises/sessions/{session_id}/answer", json={"response": "2x"}
        )
        assert submitted.status_code == 200
        assert submitted.json()["correct"] is True
        client.post(
            f"/api/v1/chat/sessions/{chat_id}/messages",
            json={"content": "what was the answer?"},
        )
        wait_for_assistant(client, chat_id)
        second_prompt = "\n".join(str(message.content) for message in gateway.calls[-1])
        assert "Do NOT reveal" not in second_prompt


def test_answer_attempts_visible_in_context() -> None:
    with make_client(["Try again [1]."]) as (client, app, gateway):
        course_id = make_course(client)
        exercise_id = make_exercise(app, course_id)
        session_id = start_session(client, exercise_id)
        client.post(
            f"/api/v1/exercises/sessions/{session_id}/answer", json={"response": "x^3"}
        )
        asked = client.post(
            f"/api/v1/exercises/sessions/{session_id}/ask",
            json={"pending_answer": ""},
        ).json()
        chat_id = asked["chat_session_id"]
        client.post(
            f"/api/v1/chat/sessions/{chat_id}/messages", json={"content": "help me"}
        )
        wait_for_assistant(client, chat_id)
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert "Submitted attempts on this step: 1" in prompt
        assert "not yet correct" in prompt


def test_ask_refuses_completed_session() -> None:
    with make_client([]) as (client, app, _gateway):
        course_id = make_course(client)
        exercise_id = make_exercise(app, course_id)
        session_id = start_session(client, exercise_id)
        db = app.state.session_factory()
        row = db.get(ExerciseSession, session_id)
        row.status = "completed"
        db.commit()
        db.close()
        asked = client.post(
            f"/api/v1/exercises/sessions/{session_id}/ask",
            json={"pending_answer": None},
        )
        assert asked.status_code == 422
        assert json.loads(asked.text) is not None
