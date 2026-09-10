import json
import time
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.contracts.contracts import Constraint, validate
from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


class QuizHelpGateway(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)
        self.calls: list[list[Message]] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="help-model",
            label="help-model",
            caps=["text"],
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.calls.append(messages)
        return self.responses.pop(0)

    def stream(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        text = self.generate(task, messages, model)
        for i in range(0, len(text), 8):
            yield text[i : i + 8]

    def stream_events(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        from app.ai.gateway import StreamChunk

        for delta in self.stream(task, messages, model):
            yield StreamChunk("text", delta)


class NoAI:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None

    def describe(
        self,
        title: str,
        markdown: str,
        course_id: int | None = None,
    ) -> dict[str, Any] | None:
        return None


CAQ_DOC = {
    "$schema": "caq/v1",
    "title": "Help quiz",
    "questions": [
        {
            "id": "q1",
            "type": "equation",
            "stem_md": "Compute $\\frac{d}{dx} x^2$.",
            "answer": {"value": "2x"},
            "explanation_md": "Power rule: $2x$.",
            "concepts": ["derivatives"],
            "skill": "procedural",
            "bloom": "apply",
            "difficulty": 2,
            "expected_time_sec": 60,
        },
        {
            "id": "q2",
            "type": "single",
            "stem_md": "Where does $f(x)=x^2-4$ cross the x-axis?",
            "options_md": ["At $x=\\pm 2$ only", "At $x=2$ only", "Never", "At $x=0$"],
            "answer": {"index": 0},
            "explanation_md": "Factor: $(x-2)(x+2)=0$.",
            "concepts": ["factoring"],
            "skill": "procedural",
            "bloom": "apply",
            "difficulty": 2,
            "expected_time_sec": 60,
            "misconceptions": {"1": "sign_slip"},
        },
    ],
}


def make_client(responses: list[str]) -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-quizhelp-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=QuizHelpGateway(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def import_quiz(client: TestClient) -> dict[str, Any]:
    created = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": make_course(client)},
        json=CAQ_DOC,
    )
    assert created.status_code == 200, created.text
    activity: dict[str, Any] = created.json()["activity"]
    return activity


def open_attempt(client: TestClient, activity_id: int, mode: str = "practice") -> int:
    started = client.post(
        f"/api/v1/quiz/activities/{activity_id}/attempts?mode={mode}"
    )
    assert started.status_code == 201, started.text
    return int(started.json()["id"])


def question_ids(client: TestClient, activity_id: int) -> list[int]:
    questions = client.get(f"/api/v1/quiz/activities/{activity_id}/questions").json()
    return [int(question["id"]) for question in questions]


def test_forbidden_texts_contract() -> None:
    context = {"expected": None, "forbidden_texts": ["At $x=\\pm 2$ only"]}
    leaking = validate(
        "The right choice is: At $x=\\pm 2$ only.", [Constraint("no_answer_reveal")], context
    )
    assert not leaking.ok
    clean = validate(
        "Look at where each factor vanishes.", [Constraint("no_answer_reveal")], context
    )
    assert clean.ok


def test_practice_hint_ladder_gating_and_audit() -> None:
    client = make_client(["Which rule governs powers of the input variable?"])
    with client:
        activity = import_quiz(client)
        attempt_id = open_attempt(client, activity["id"])
        q1, _q2 = question_ids(client, activity["id"])

        skip = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/hint", json={"level": 3}
        )
        assert skip.status_code == 422

        reveal = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/hint", json={"level": 5}
        )
        assert reveal.status_code == 422

        first = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/hint", json={"level": 1}
        )
        assert first.status_code == 200
        assert first.json()["level"] == 1
        assert first.json()["violations"] is None

        listing = client.get(f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/help")
        assert listing.status_code == 200
        assert [event["level"] for event in listing.json()] == [1]

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            rows = db.execute(
                text(
                    "SELECT context_type, direction FROM ai_interactions "
                    "WHERE context_type = 'quiz_help'"
                )
            ).all()
        assert rows == [("quiz_help", f"hint level 1 q{q1}")]


def test_hint_leak_repaired_for_quiz_question() -> None:
    client = make_client(
        [
            "Note that the derivative is $2x$ — just write that.",
            "Which differentiation rule applies to powers of the input variable?",
        ]
    )
    with client:
        activity = import_quiz(client)
        attempt_id = open_attempt(client, activity["id"])
        q1, _q2 = question_ids(client, activity["id"])
        hint = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/hint", json={"level": 1}
        )
        assert hint.status_code == 200
        assert "2x" not in hint.json()["markdown"]
        assert hint.json()["violations"] is None


def test_level5_unlocks_after_submit_and_help_events_land_on_answer() -> None:
    client = make_client(
        [
            "Consider the exponent.",
            "The full solution applies the power rule: derivative $2x$, evaluated next step.",
        ]
    )
    with client:
        activity = import_quiz(client)
        attempt_id = open_attempt(client, activity["id"])
        q1, _q2 = question_ids(client, activity["id"])
        client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/hint", json={"level": 1}
        )
        answered = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/answers",
            json={"question_id": q1, "response": "3x"},
        )
        assert answered.status_code == 200

        full = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/hint", json={"level": 5}
        )
        assert full.status_code == 200
        assert full.json()["level"] == 5

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            row = db.execute(
                text("SELECT help_events FROM answers WHERE attempt_id = :a"),
                {"a": attempt_id},
            ).one()
        events = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert events and events[0]["type"] == "hint" and events[0]["level"] == 1


def test_exam_mode_refuses_help() -> None:
    client = make_client([])
    with client:
        activity = import_quiz(client)
        attempt_id = open_attempt(client, activity["id"], mode="exam")
        q1, _q2 = question_ids(client, activity["id"])
        hint = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/hint", json={"level": 1}
        )
        assert hint.status_code == 422
        assert "exam" in hint.json()["detail"]
        ask = client.post(f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/ask")
        assert ask.status_code == 422


def test_ask_about_question_opens_guarded_chat() -> None:
    client = make_client(
        [
            "The derivative you want is $2x$.",
            "Which rule differentiates $x^n$? Write the general form first.",
        ]
    )
    with client:
        activity = import_quiz(client)
        attempt_id = open_attempt(client, activity["id"])
        q1, _q2 = question_ids(client, activity["id"])
        ask = client.post(f"/api/v1/quiz/attempts/{attempt_id}/questions/{q1}/ask")
        assert ask.status_code == 201, ask.text
        chat_session_id = ask.json()["chat_session_id"]

        seeded = client.get(f"/api/v1/chat/sessions/{chat_session_id}/messages").json()
        assert seeded and "quiz question" in seeded[0]["markdown"].lower()

        sent = client.post(
            f"/api/v1/chat/sessions/{chat_session_id}/messages",
            json={"content": "I keep getting 3x, what am I missing?"},
        )
        assert sent.status_code == 200

        deadline = time.monotonic() + 5.0
        messages: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            messages = client.get(
                f"/api/v1/chat/sessions/{chat_session_id}/messages"
            ).json()
            if messages and messages[-1]["role"] == "assistant":
                break
            time.sleep(0.05)
        assert messages and messages[-1]["role"] == "assistant"
        assert "2x" not in messages[-1]["markdown"]

        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, QuizHelpGateway)
        first_system = " ".join(
            message.content if isinstance(message.content, str) else ""
            for message in gateway.calls[-2]
        )
        assert "OPEN attempt" in first_system
