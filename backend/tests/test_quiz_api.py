import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel, TaskUnassigned
from app.core.config import Settings
from app.main import create_app

QUIZ_JSON = json.dumps(
    {
        "questions": [
            {
                "type": "single",
                "stem_md": "What is $\\frac{d}{dx} x^2$?",
                "options_md": ["$2x$", "$x$", "$x^2$", "$2$"],
                "answer": {"index": 0},
                "explanation_md": "Power rule: $d/dx\\,x^n = nx^{n-1}$.",
                "concepts": ["power rule"],
                "skill": "procedural",
                "bloom": "apply",
                "difficulty": 2,
                "expected_time_sec": 60,
                "misconceptions": {"1": "confused_exponent"},
            },
            {
                "type": "truefalse",
                "stem_md": "The derivative of a constant is zero.",
                "answer": {"value": True},
                "explanation_md": "Constants have zero rate of change.",
                "concepts": ["derivatives"],
                "skill": "conceptual",
                "bloom": "remember",
                "difficulty": 1,
                "expected_time_sec": 30,
            },
            {
                "type": "equation",
                "stem_md": "Differentiate $f(x) = x^2 \\sin x$.",
                "answer": {"value": "2*x*sin(x) + x^2*cos(x)"},
                "explanation_md": "Product rule.",
                "concepts": ["product rule", "chain rule"],
                "skill": "procedural",
                "bloom": "apply",
                "difficulty": 3,
                "expected_time_sec": 120,
                "sympy_check": {"expected": "2*x*sin(x) + x**2*cos(x)"},
            },
        ]
    }
)


class QuizGateway(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="quiz-model",
            label="quiz-model",
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
        return self.responses.pop(0)

    def stream(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        text = self.generate(task, messages, model)
        yield text


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


@pytest.fixture
def quiz_client() -> Iterator[TestClient]:
    gateway = QuizGateway([QUIZ_JSON])
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-quiz-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def test_generate_quiz_with_valid_metadata(quiz_client: TestClient) -> None:
    created = quiz_client.post(
        "/api/v1/quiz/generate", json={"count": 3, "course_id": make_course(quiz_client)}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["question_count"] == 3

    questions = quiz_client.get(f"/api/v1/quiz/activities/{body['id']}/questions").json()
    types = {question["type"] for question in questions}
    assert types == {"single", "truefalse", "equation"}
    assert all(question["flag"] == "ok" for question in questions)
    assert questions[0]["skill"] == "procedural"
    assert questions[0]["expected_time_sec"] == 60


def test_quizgen_repair_round_fixes_invalid_metadata() -> None:
    import tempfile
    from pathlib import Path

    invalid = json.dumps(
        {
            "questions": [
                {
                    "type": "single",
                    "stem_md": "Broken question",
                    "options_md": ["a", "b"],
                    "answer": {"index": 5},
                    "explanation_md": "",
                    "concepts": [],
                    "skill": "unknown",
                    "bloom": "unknown",
                    "difficulty": 9,
                    "expected_time_sec": -1,
                }
            ]
        }
    )
    gateway = QuizGateway([invalid, QUIZ_JSON])
    tmp = Path(tempfile.mkdtemp(prefix="ca-quiz2-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/quiz/generate",
            json={"count": 3, "course_id": make_course(client)},
        )
        assert created.status_code == 201
        assert created.json()["question_count"] == 3
        assert len(gateway.responses) == 0


def test_full_quiz_attempt_flow_with_instant_feedback(quiz_client: TestClient) -> None:
    activity = quiz_client.post(
        "/api/v1/quiz/generate",
        json={"count": 3, "course_id": make_course(quiz_client)},
    ).json()
    questions = quiz_client.get(f"/api/v1/quiz/activities/{activity['id']}/questions").json()

    attempt = quiz_client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()
    assert attempt["mode"] == "practice"
    assert attempt["score"] is None

    right = quiz_client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[0]["id"], "response": 0, "time_ms": 12000},
    ).json()
    assert right["correct"] is True
    assert right["graded_by"] == "deterministic"
    assert right["explanation"]

    wrong = quiz_client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[1]["id"], "response": False},
    ).json()
    assert wrong["correct"] is False

    typed = quiz_client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={
            "question_id": questions[2]["id"],
            "response": "x^2 cos(x) + 2x sin(x)",
        },
    ).json()
    assert typed["correct"] is True
    assert typed["graded_by"] == "symPy"

    finished = quiz_client.post(f"/api/v1/quiz/attempts/{attempt['id']}/finish").json()
    assert finished["score"] == pytest.approx(2 / 3, abs=1e-3)

    report = quiz_client.get(f"/api/v1/quiz/attempts/{attempt['id']}/report").json()
    assert len(report["answers"]) == 3
    assert report["answers"][1]["correct"] is False

    after_finish = quiz_client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[0]["id"], "response": 0},
    )
    assert after_finish.status_code == 422


def test_mistakes_recorded_on_wrong_answers(quiz_client: TestClient) -> None:
    activity = quiz_client.post(
        "/api/v1/quiz/generate",
        json={"count": 3, "course_id": make_course(quiz_client)},
    ).json()
    questions = quiz_client.get(f"/api/v1/quiz/activities/{activity['id']}/questions").json()
    attempt = quiz_client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()
    quiz_client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[0]["id"], "response": 1},
    )
    app = quiz_client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as db:
        from sqlalchemy import text

        count = db.execute(text("SELECT count(*) FROM mistakes")).scalar_one()
    assert count == 1


def test_quiz_generation_requires_assigned_model() -> None:
    import tempfile
    from pathlib import Path

    class UnassignedGateway(LLMGateway):
        def __init__(self) -> None:
            super().__init__(session_factory=None)

        def resolve(
            self,
            task: str,
            course_id: int | None = None,
        ) -> ResolvedModel:
            raise TaskUnassigned(task)

        def generate(
            self,
            task: str,
            messages: list[Message],
            model: Any = None,
            course_id: int | None = None,
        ) -> str:
            raise TaskUnassigned(task)

    tmp = Path(tempfile.mkdtemp(prefix="ca-quiz3-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=UnassignedGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/quiz/generate",
            json={"count": 2, "course_id": make_course(client)},
        )
        assert response.status_code == 502
        listing = client.get("/api/v1/quiz/activities").json()
        assert listing == []


def test_quiz_activities_listing(quiz_client: TestClient) -> None:
    quiz_client.post(
        "/api/v1/quiz/generate",
        json={"count": 3, "course_id": make_course(quiz_client)},
    )
    listing = quiz_client.get("/api/v1/quiz/activities").json()
    assert len(listing) == 1
    assert listing[0]["question_count"] == 3


def test_get_single_quiz_activity(quiz_client: TestClient) -> None:
    course_id = make_course(quiz_client)
    quiz_client.post("/api/v1/quiz/generate", json={"count": 2, "course_id": course_id})
    activity_id = quiz_client.get("/api/v1/quiz/activities").json()[0]["id"]

    body = quiz_client.get(f"/api/v1/quiz/activities/{activity_id}")
    assert body.status_code == 200, body.text
    payload = body.json()
    assert payload["id"] == activity_id
    assert payload["course_id"] == course_id
    assert payload["node_id"] is not None
    assert payload["question_count"] == 2

    missing = quiz_client.get("/api/v1/quiz/activities/999999")
    assert missing.status_code == 404


def test_quizgen_question_types_allowlist() -> None:
    import tempfile
    from pathlib import Path

    payload = json.dumps(
        {
            "questions": [
                {
                    "type": "numeric",
                    "stem_md": "Evaluate $\\int_0^1 x dx$.",
                    "answer": {"value": 0.5},
                    "explanation_md": "Antiderivative is $x^2/2$.",
                    "concepts": ["definite integrals"],
                    "skill": "procedural",
                    "bloom": "apply",
                    "difficulty": 2,
                    "expected_time_sec": 60,
                },
                {
                    "type": "numeric",
                    "stem_md": "Evaluate $\\int_0^2 x dx$.",
                    "answer": {"value": 2},
                    "explanation_md": "Antiderivative is $x^2/2$.",
                    "concepts": ["definite integrals"],
                    "skill": "procedural",
                    "bloom": "apply",
                    "difficulty": 2,
                    "expected_time_sec": 60,
                },
                {
                    "type": "equation",
                    "stem_md": "Differentiate $f(x) = x^3$.",
                    "answer": {"value": "3*x^2"},
                    "explanation_md": "Power rule.",
                    "concepts": ["power rule"],
                    "skill": "procedural",
                    "bloom": "apply",
                    "difficulty": 3,
                    "expected_time_sec": 90,
                },
            ]
        }
    )
    gateway = QuizGateway([payload])
    tmp = Path(tempfile.mkdtemp(prefix="ca-quiz-types-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/quiz/generate",
            json={
                "count": 3,
                "course_id": make_course(client),
                "question_types": ["numeric", "equation"],
            },
        )
        assert created.status_code == 201, created.text
        questions = client.get(
            f"/api/v1/quiz/activities/{created.json()['id']}/questions"
        ).json()
        assert {q["type"] for q in questions} == {"numeric", "equation"}


def test_quizgen_question_types_rejected_when_unknown(
    quiz_client: TestClient,
) -> None:
    response = quiz_client.post(
        "/api/v1/quiz/generate",
        json={
            "count": 3,
            "course_id": make_course(quiz_client),
            "question_types": ["essay"],
        },
    )
    assert response.status_code == 422
    assert "essay" in response.text


def test_quizgen_off_type_draft_repairs() -> None:
    import tempfile
    from pathlib import Path

    wrong = json.dumps(
        {
            "questions": [
                {
                    "type": "single",
                    "stem_md": "Out-of-set type",
                    "options_md": ["a", "b"],
                    "answer": {"index": 0},
                    "explanation_md": "n/a",
                    "concepts": ["x"],
                    "skill": "procedural",
                    "bloom": "remember",
                    "difficulty": 2,
                    "expected_time_sec": 30,
                }
            ]
        }
    )
    gateway = QuizGateway([wrong, QUIZ_JSON])
    tmp = Path(tempfile.mkdtemp(prefix="ca-quiz-types2-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/quiz/generate",
            json={
                "count": 3,
                "course_id": make_course(client),
                "question_types": ["single", "truefalse", "equation"],
            },
        )
        assert created.status_code == 201, created.text
        assert len(gateway.responses) == 0


def test_quizgen_shuffle_remaps_options() -> None:
    import tempfile
    from pathlib import Path

    from app.domain.models import Question

    gateway = QuizGateway([QUIZ_JSON])
    tmp = Path(tempfile.mkdtemp(prefix="ca-quiz-shuffle-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/quiz/generate",
            json={
                "count": 3,
                "course_id": make_course(client),
                "shuffle": True,
            },
        )
        assert created.status_code == 201, created.text
        app2 = client.app
        assert isinstance(app2, FastAPI)
        with app2.state.session_factory() as db:
            questions = db.query(Question).all()
            assert len(questions) == 3
            single = next(q for q in questions if q.type == "single")
            assert single.answer["index"] in range(len(single.options))
            for key in single.distractor_misconceptions or {}:
                assert int(key) in range(len(single.options))


def test_quiz_response_shapes(quiz_client: TestClient) -> None:
    course_id = make_course(quiz_client)
    activity = quiz_client.post(
        "/api/v1/quiz/generate", json={"course_id": course_id, "count": 3}
    ).json()

    inbox = quiz_client.get("/api/v1/quiz/inbox/path").json()
    assert set(inbox) == {"path"}

    attempt = quiz_client.post(
        f"/api/v1/quiz/activities/{activity['id']}/attempts"
    ).json()
    attempts = quiz_client.get("/api/v1/quiz/attempts").json()
    assert len(attempts) == 1
    assert set(attempts[0]) == {
        "id",
        "activity_id",
        "title",
        "mode",
        "started_at",
        "finished_at",
        "score",
    }
    assert attempts[0]["mode"] == "practice"
    assert attempts[0]["score"] is None

    questions = quiz_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()
    quiz_client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[0]["id"], "response": {"index": 1}},
    )
    mistakes = quiz_client.get("/api/v1/quiz/mistakes").json()
    assert len(mistakes) == 1
    assert set(mistakes[0]) == {
        "id",
        "question_id",
        "activity_id",
        "activity_title",
        "stem_excerpt",
        "error_tags",
        "created_at",
    }

    report = quiz_client.get(
        f"/api/v1/quiz/attempts/{attempt['id']}/report"
    ).json()
    assert set(report) == {"attempt", "answers"}
    assert set(report["attempt"]) == {
        "id",
        "activity_id",
        "mode",
        "started_at",
        "finished_at",
        "score",
    }
    assert set(report["answers"][0]) == {
        "question_id",
        "correct",
        "partial_credit",
        "error_tags",
        "stem_excerpt",
        "question_type",
        "response",
    }

    dry = quiz_client.post(
        "/api/v1/quiz/import",
        params={"course_id": course_id, "dry_run": "true"},
        json={
            "title": "Imported",
            "questions": [
                {
                    "id": "q1",
                    "type": "truefalse",
                    "stem_md": "2 > 1?",
                    "answer": {"value": True},
                }
            ],
        },
    ).json()
    assert set(dry) == {"dry_run", "results", "valid", "total", "activity"}
    assert dry["dry_run"] is True
    assert dry["activity"] is None

    deleted = quiz_client.delete(f"/api/v1/quiz/activities/{activity['id']}")
    assert deleted.status_code == 200
    assert set(deleted.json()) == {"deleted_item_id"}
