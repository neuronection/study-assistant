import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, make_course
from test_chat_native_tools import NativeGateway

from app.core.config import Settings
from app.main import create_app
from app.services.platform.quizme import grade_answer, validate_quiz_args


def wait_for_assistant(
    client: TestClient, session_id: int, timeout: float = 5.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages: list[dict[str, Any]] = client.get(
            f"/api/v1/chat/sessions/{session_id}/messages"
        ).json()
        if messages and messages[-1]["role"] == "assistant":
            return messages[-1]
        time.sleep(0.05)
    raise AssertionError("assistant never replied")


@fixture
def gateway() -> ScriptedGateway:
    return ScriptedGateway([])


@fixture
def client(
    tmp_path: Path, gateway: ScriptedGateway
) -> Iterator[tuple[TestClient, ScriptedGateway, FastAPI]]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway, app


def test_grading_matrix_choices() -> None:
    pending = validate_quiz_args(
        {
            "question": "2+2?",
            "choices": ["3", "4", "5"],
            "expected_index": 1,
        }
    )
    assert grade_answer(pending, 1) == (True, "exact choice match")
    assert grade_answer(pending, 0)[0] is False
    assert grade_answer(pending, "nope")[0] is False


def test_grading_matrix_latex_equivalence_chain() -> None:
    pending = validate_quiz_args(
        {"question": "simplify x^2/x", "expected_latex": "x"}
    )
    correct, detail = grade_answer(pending, "x")
    assert correct is True
    assert "equivalence chain" in detail
    wrong, _wrong_detail = grade_answer(pending, "2x")
    assert wrong is False
    accepted, _accepted_detail = grade_answer(pending, "x^1")
    assert accepted is True


def test_grading_matrix_text_with_accept_variants() -> None:
    pending = validate_quiz_args(
        {
            "question": "Who wrote Principia?",
            "expected_text": "Newton",
            "accept": ["Isaac Newton"],
        }
    )
    assert grade_answer(pending, "newton")[0] is True
    assert grade_answer(pending, "  Isaac Newton ")[0] is True
    assert grade_answer(pending, "Leibniz")[0] is False


def test_validate_quiz_args_rejects_incomplete() -> None:
    import pytest

    with pytest.raises(ValueError):
        validate_quiz_args({"question": "no answer material"})
    with pytest.raises(ValueError):
        validate_quiz_args({"question": "q", "choices": ["a"], "expected_index": 0})
    with pytest.raises(ValueError):
        validate_quiz_args(
            {"question": "q", "choices": ["a", "b"], "expected_index": 5}
        )


def test_quizme_flag_on_session(client: tuple[TestClient, ScriptedGateway, FastAPI]) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        assert session["quizme"] is False
        patched = test_client.patch(
            f"/api/v1/chat/sessions/{session['id']}", json={"quizme": True}
        )
        assert patched.json()["quizme"] is True


QUIZ_ARGS = {
    "question": "Compute the limit of 1/x as x approaches infinity.",
    "expected_text": "0",
    "accept": ["zero"],
}


def test_quiz_tool_flow_non_leak_and_verdict(tmp_path: Path) -> None:
    gateway = NativeGateway([])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        test_client, gateway = test_client, gateway
        course_id = make_course(test_client)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        session_id = int(session["id"])
        test_client.patch(f"/api/v1/chat/sessions/{session_id}", json={"quizme": True})

        gateway.responses.append(
            [
                {
                    "name": "QUIZ",
                    "arguments": dict(
                        QUIZ_ARGS, choices=["0", "1"], expected_index=0
                    ),
                }
            ]
        )
        gateway.responses.append("Great — next question coming up.")
        sent = test_client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"content": "quiz me on limits"},
        )
        assert sent.status_code == 200
        assistant = wait_for_assistant(test_client, session_id)
        quiz_calls = [
            call for call in (assistant.get("tool_calls") or []) if call["name"] == "QUIZ"
        ]
        assert len(quiz_calls) == 1
        quiz_payload = quiz_calls[0].get("quiz") or {}
        assert quiz_payload["question"] == QUIZ_ARGS["question"]
        assert quiz_payload["choices"] == ["0", "1"]
        assert quiz_payload.get("answered") is None or quiz_payload.get("answered") is False

        for messages in gateway.calls:
            flat = json.dumps(
                [str(message.content) for message in messages], ensure_ascii=False
            )
            assert '"expected_' not in flat
            assert 'expected_index": 0' not in flat
            assert 'expected_index=0' not in flat


        answered = test_client.post(
            f"/api/v1/chat/sessions/{session_id}/quiz-answer",
            json={"answer": 0},
        )
        assert answered.status_code == 200, answered.text
        body = answered.json()
        assert body["correct"] is True
        assert body["expected_display"] == "0"

        detail = test_client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()
        user_answers = [
            message
            for message in detail
            if message["role"] == "user" and message["markdown"] == "0"
        ]
        assert user_answers, "the student's answer should be stored as a message"

        already = test_client.post(
            f"/api/v1/chat/sessions/{session_id}/quiz-answer", json={"answer": 1}
        )
        assert already.status_code == 409


def test_quiz_answer_without_pending_question_is_conflict(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        response = test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/quiz-answer",
            json={"answer": "x"},
        )
        assert response.status_code == 409


def test_quiz_prompt_block_present_when_quizme_on(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        session_id = int(session["id"])
        test_client.patch(f"/api/v1/chat/sessions/{session_id}", json={"quizme": True})
        gateway.responses.append("plain answer")
        test_client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"content": "hello"},
        )
        wait_for_assistant(test_client, session_id)
        flat = "\n".join(
            str(message.content) for message in gateway.calls[0]
        )
        assert "QUIZ-ME MODE" in flat
        assert "QUIZ" in flat


def test_quizme_answer_credits_daily_history(tmp_path: Path) -> None:
    gateway = NativeGateway([])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        course_id = make_course(test_client)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        session_id = int(session["id"])
        test_client.patch(f"/api/v1/chat/sessions/{session_id}", json={"quizme": True})

        gateway.responses.append(
            [
                {
                    "name": "QUIZ",
                    "arguments": dict(
                        QUIZ_ARGS, choices=["0", "1"], expected_index=0
                    ),
                }
            ]
        )
        gateway.responses.append("Next question coming up.")
        sent = test_client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"content": "quiz me on limits"},
        )
        assert sent.status_code == 200
        wait_for_assistant(test_client, session_id)

        before = test_client.get("/api/v1/analytics/overview").json()
        assert before["today"]["answers_n"] == 0

        answered = test_client.post(
            f"/api/v1/chat/sessions/{session_id}/quiz-answer",
            json={"answer": 0},
        )
        assert answered.status_code == 200, answered.text
        assert answered.json()["correct"] is True

        overview = test_client.get("/api/v1/analytics/overview").json()
        assert overview["today"]["answers_n"] == 1
        assert overview["today"]["correct_n"] == 1
        assert overview["history"][-1]["answers_n"] == 1
