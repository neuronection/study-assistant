import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

NUMBERLINE_ANSWER: dict[str, Any] = {
    "domain": {"min": -5, "max": 9},
    "points": [],
    "intervals": [{"lo": -1, "hi": 5, "lo_closed": False, "hi_closed": False}],
}

NUMBERLINE_QUESTION: dict[str, Any] = {
    "type": "numberline",
    "stem_md": "Shade the solution set of $|x - 2| < 3$.",
    "answer": NUMBERLINE_ANSWER,
    "explanation_md": "The solution set is the open interval $(-1, 5)$.",
    "concepts": ["intervals"],
    "skill": "conceptual",
    "bloom": "understand",
    "difficulty": 2,
    "expected_time_sec": 60,
}


def quiz_json(question: dict[str, Any]) -> str:
    return json.dumps({"questions": [question]})


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
def numberline_client() -> Iterator[TestClient]:
    gateway = QuizGateway([quiz_json(NUMBERLINE_QUESTION)])
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-numberline-"))
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


def generate_numberline_quiz(client: TestClient) -> Any:
    created = client.post(
        "/api/v1/quiz/generate",
        json={
            "count": 1,
            "course_id": make_course(client),
            "question_types": ["numberline"],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def start_attempt(client: TestClient, activity_id: int) -> int:
    started = client.post(f"/api/v1/quiz/activities/{activity_id}/attempts")
    assert started.status_code == 201
    return int(started.json()["id"])


def submit(client: TestClient, attempt_id: int, question_id: int, response: Any) -> Any:
    result = client.post(
        f"/api/v1/quiz/attempts/{attempt_id}/answers",
        json={"question_id": question_id, "response": response},
    )
    assert result.status_code == 200, result.text
    return result.json()


class TestNumberlineQuiz:
    def test_generate_and_public_input(self, numberline_client: TestClient) -> None:
        activity = generate_numberline_quiz(numberline_client)
        questions = numberline_client.get(
            f"/api/v1/quiz/activities/{activity['id']}/questions"
        ).json()
        assert len(questions) == 1
        question = questions[0]
        assert question["type"] == "numberline"
        assert question["flag"] == "ok"
        assert question["input"] == {"widget": "numberline", "min": -5, "max": 9}
        assert "answer" not in question

    def test_exact_answer_correct(self, numberline_client: TestClient) -> None:
        activity = generate_numberline_quiz(numberline_client)
        question = numberline_client.get(
            f"/api/v1/quiz/activities/{activity['id']}/questions"
        ).json()[0]
        attempt_id = start_attempt(numberline_client, activity["id"])
        result = submit(
            numberline_client,
            attempt_id,
            question["id"],
            {
                "points": [],
                "intervals": [{"lo": -1, "hi": 5, "lo_closed": False, "hi_closed": False}],
            },
        )
        assert result["correct"] is True
        assert result["partial_credit"] == 1.0

    def test_partial_shading_earns_partial_credit(self, numberline_client: TestClient) -> None:
        activity = generate_numberline_quiz(numberline_client)
        question = numberline_client.get(
            f"/api/v1/quiz/activities/{activity['id']}/questions"
        ).json()[0]
        attempt_id = start_attempt(numberline_client, activity["id"])
        result = submit(
            numberline_client,
            attempt_id,
            question["id"],
            {
                "points": [],
                "intervals": [{"lo": -1, "hi": 2, "lo_closed": False, "hi_closed": False}],
            },
        )
        assert result["correct"] is False
        assert 0 < result["partial_credit"] < 1
        assert "missed_region" in result["error_tags"]

    def test_boundary_flip_flagged(self, numberline_client: TestClient) -> None:
        activity = generate_numberline_quiz(numberline_client)
        question = numberline_client.get(
            f"/api/v1/quiz/activities/{activity['id']}/questions"
        ).json()[0]
        attempt_id = start_attempt(numberline_client, activity["id"])
        result = submit(
            numberline_client,
            attempt_id,
            question["id"],
            {
                "points": [],
                "intervals": [{"lo": -1, "hi": 5, "lo_closed": True, "hi_closed": True}],
            },
        )
        assert result["correct"] is False
        assert "boundary_kind" in result["error_tags"]

    def test_garbage_response_fails(self, numberline_client: TestClient) -> None:
        activity = generate_numberline_quiz(numberline_client)
        question = numberline_client.get(
            f"/api/v1/quiz/activities/{activity['id']}/questions"
        ).json()[0]
        attempt_id = start_attempt(numberline_client, activity["id"])
        result = submit(numberline_client, attempt_id, question["id"], "hello")
        assert result["correct"] is False
        assert result["partial_credit"] == 0.0

    def test_report_carries_response_for_replay(self, numberline_client: TestClient) -> None:
        activity = generate_numberline_quiz(numberline_client)
        question = numberline_client.get(
            f"/api/v1/quiz/activities/{activity['id']}/questions"
        ).json()[0]
        attempt_id = start_attempt(numberline_client, activity["id"])
        payload = {
            "points": [],
            "intervals": [{"lo": -1, "hi": 5, "lo_closed": False, "hi_closed": False}],
        }
        submit(numberline_client, attempt_id, question["id"], payload)
        numberline_client.post(f"/api/v1/quiz/attempts/{attempt_id}/finish")
        report = numberline_client.get(f"/api/v1/quiz/attempts/{attempt_id}/report").json()
        assert report["answers"][0]["question_type"] == "numberline"
        assert report["answers"][0]["response"] == payload

    def test_invalid_draft_triggers_repair(self) -> None:
        invalid = json.dumps(
            {
                "questions": [
                    {
                        **NUMBERLINE_QUESTION,
                        "answer": {
                            "domain": {"min": -5, "max": 9},
                            "points": [],
                            "intervals": [
                                {"lo": 5, "hi": -1, "lo_closed": False, "hi_closed": False}
                            ],
                        },
                    }
                ]
            }
        )
        gateway = QuizGateway([invalid, quiz_json(NUMBERLINE_QUESTION)])
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.mkdtemp(prefix="ca-numberline-repair-"))
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
                    "count": 1,
                    "course_id": make_course(client),
                    "question_types": ["numberline"],
                },
            )
            assert created.status_code == 201, created.text
            questions = client.get(
                f"/api/v1/quiz/activities/{created.json()['id']}/questions"
            ).json()
            assert questions[0]["flag"] == "ok"
            assert gateway.responses == []


class TestNumberlineCaq:
    def test_import_export_round_trip(self, numberline_client: TestClient) -> None:
        course_id = make_course(numberline_client)
        document = {
            "title": "Numberline import",
            "questions": [
                {
                    "id": "q1",
                    "type": "numberline",
                    "stem_md": "Shade $x > 1$.",
                    "answer": {
                        "domain": {"min": 0, "max": 5},
                        "points": [],
                        "intervals": [{"lo": 1, "hi": 5, "lo_closed": False, "hi_closed": False}],
                    },
                    "explanation_md": "Open interval.",
                    "concepts": ["intervals"],
                    "skill": "conceptual",
                    "bloom": "understand",
                    "difficulty": 2,
                    "expected_time_sec": 60,
                }
            ],
        }
        imported = numberline_client.post(
            "/api/v1/quiz/import",
            params={"course_id": course_id, "dry_run": False},
            json=document,
        )
        assert imported.status_code == 200, imported.text
        body = imported.json()
        assert body["valid"] == 1
        assert body["activity"] is not None
        exported = numberline_client.get(
            f"/api/v1/quiz/activities/{body['activity']['id']}/export"
        ).json()
        assert exported["questions"][0]["answer"]["domain"] == {"min": 0, "max": 5}

    def test_dry_run_rejects_broken_answer(self, numberline_client: TestClient) -> None:
        course_id = make_course(numberline_client)
        document = {
            "title": "Broken",
            "questions": [
                {
                    "id": "q1",
                    "type": "numberline",
                    "stem_md": "Shade $x > 1$.",
                    "answer": {"domain": {"min": 5, "max": 0}},
                    "explanation_md": "Broken.",
                    "concepts": ["intervals"],
                    "skill": "conceptual",
                    "bloom": "understand",
                    "difficulty": 2,
                    "expected_time_sec": 60,
                }
            ],
        }
        imported = numberline_client.post(
            "/api/v1/quiz/import",
            params={"course_id": course_id, "dry_run": True},
            json=document,
        )
        assert imported.status_code == 200
        assert imported.json()["valid"] == 0


class TestNumberlineExerciseStep:
    def test_step_check_and_public_input(self, numberline_client: TestClient) -> None:
        course_id = make_course(numberline_client)
        created = numberline_client.post(
            "/api/v1/exercises",
            json={
                "title": "Shade the set",
                "course_id": course_id,
                "steps": [
                    {
                        "prompt_md": "Shade the solution set of $x > 1$.",
                        "expected": {
                            "kind": "numberline",
                            "value": {
                                "domain": {"min": 0, "max": 5},
                                "points": [],
                                "intervals": [
                                    {"lo": 1, "hi": 5, "lo_closed": False, "hi_closed": False}
                                ],
                            },
                        },
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        exercise_id = created.json()["id"]
        steps = numberline_client.get(f"/api/v1/exercises/{exercise_id}/steps").json()
        assert steps[0]["input"] == {"widget": "numberline", "min": 0, "max": 5}
        session = numberline_client.post(f"/api/v1/exercises/{exercise_id}/sessions")
        session_id = session.json()["id"]
        correct = numberline_client.post(
            f"/api/v1/exercises/sessions/{session_id}/answer",
            json={
                "response": {
                    "points": [],
                    "intervals": [{"lo": 1, "hi": 5, "lo_closed": False, "hi_closed": False}],
                }
            },
        )
        assert correct.status_code == 200, correct.text
        assert correct.json()["correct"] is True
        assert correct.json()["advanced"] is False

    def test_step_wrong_boundary_incorrect(self, numberline_client: TestClient) -> None:
        course_id = make_course(numberline_client)
        created = numberline_client.post(
            "/api/v1/exercises",
            json={
                "title": "Shade the set",
                "course_id": course_id,
                "steps": [
                    {
                        "prompt_md": "Shade the solution set of $x > 1$.",
                        "expected": {
                            "kind": "numberline",
                            "value": {
                                "domain": {"min": 0, "max": 5},
                                "points": [],
                                "intervals": [
                                    {"lo": 1, "hi": 5, "lo_closed": False, "hi_closed": False}
                                ],
                            },
                        },
                    }
                ],
            },
        )
        exercise_id = created.json()["id"]
        session = numberline_client.post(f"/api/v1/exercises/{exercise_id}/sessions")
        session_id = session.json()["id"]
        wrong = numberline_client.post(
            f"/api/v1/exercises/sessions/{session_id}/answer",
            json={
                "response": {
                    "points": [],
                    "intervals": [{"lo": 1, "hi": 5, "lo_closed": True, "hi_closed": True}],
                }
            },
        )
        assert wrong.json()["correct"] is False
        assert "boundary" in wrong.json()["stage"]
