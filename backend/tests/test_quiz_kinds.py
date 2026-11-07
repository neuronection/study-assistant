import json
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

MIXED_QUIZ = json.dumps(
    {
        "questions": [
            {
                "type": "cloze",
                "stem_md": "Complete the derivative rules.",
                "answer": {
                    "prompt_md": "The derivative of $x^2$ is {{1}} and of $\\sin x$ is {{2}}.",
                    "answers": [["2x", "2*x"], ["cos x", "cos(x)"]],
                },
                "explanation_md": "Power rule and the sine derivative.",
                "concepts": ["derivatives"],
                "skill": "procedural",
                "bloom": "remember",
                "difficulty": 2,
                "expected_time_sec": 60,
            },
            {
                "type": "matching",
                "stem_md": "Match each function with its derivative.",
                "answer": {
                    "pairs": [
                        {"left": "$x^2$", "right": "$2x$"},
                        {"left": "$\\sin x$", "right": "$\\cos x$"},
                    ]
                },
                "explanation_md": "Power rule and the sine derivative.",
                "concepts": ["derivatives"],
                "skill": "procedural",
                "bloom": "understand",
                "difficulty": 2,
                "expected_time_sec": 90,
            },
            {
                "type": "essay",
                "stem_md": "Explain why the chain rule is needed.",
                "answer": {
                    "prompt_md": "Explain why the chain rule is needed.",
                    "rubric": [
                        {"id": "r1", "text": "Mentions composite functions"},
                        {"id": "r2", "text": "Explains the inner derivative factor"},
                    ],
                },
                "explanation_md": "Composite functions need the inner derivative.",
                "concepts": ["chain rule"],
                "skill": "conceptual",
                "bloom": "understand",
                "difficulty": 3,
                "expected_time_sec": 180,
            },
        ]
    }
)

RUBRIC_RESULT = json.dumps(
    {
        "verdict": "correct",
        "score": 1.0,
        "rationale": [
            {"rubric_id": "r1", "reason": "Names composite functions."},
            {"rubric_id": "r2", "reason": "Explains the inner factor."},
        ],
    }
)


class KindsGateway(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)
        self.prompts: list[str] = []

    def resolve(self, task: str, course_id: str | None = None) -> ResolvedModel:
        return ResolvedModel(
            provider_id="1",
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="kinds-model",
            label="kinds-model",
            caps=["text"],
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: str | None = None,
    ) -> str:
        self.prompts.append(str(messages[-1].content))
        return self.responses.pop(0)


class NoAI:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None

    def describe(
        self,
        title: str,
        markdown: str,
        course_id: str | None = None,
    ) -> dict[str, Any] | None:
        return None


@pytest.fixture
def kinds_client() -> Iterator[tuple[TestClient, KindsGateway]]:
    import tempfile
    from pathlib import Path

    gateway = KindsGateway([MIXED_QUIZ, RUBRIC_RESULT])
    app = create_app(
        Settings(data_dir=Path(tempfile.mkdtemp(prefix="sa-kinds-")), log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client, gateway


def make_course(client: TestClient) -> str:
    return str(client.post("/api/v1/courses", json={"title": "Kinds"}).json()["id"])


def generate_mixed(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/quiz/generate",
        json={
            "count": 3,
            "course_id": make_course(client),
            "question_types": ["cloze", "matching", "essay"],
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_mixed_quiz_generates_runnable_widgets(
    kinds_client: tuple[TestClient, KindsGateway],
) -> None:
    client, _gateway = kinds_client
    activity = generate_mixed(client)
    questions = client.get(f"/api/v1/quiz/activities/{activity['id']}/questions").json()
    assert {question["type"] for question in questions} == {"cloze", "matching", "essay"}
    by_type = {question["type"]: question for question in questions}
    assert by_type["cloze"]["input"]["widget"] == "fill_blank"
    assert by_type["cloze"]["input"]["blank_count"] == 2
    assert by_type["matching"]["input"]["widget"] == "matching"
    assert by_type["matching"]["input"]["lefts"] == ["$x^2$", "$\\sin x$"]
    assert by_type["essay"]["input"] == {
        "widget": "essay",
        "kind": "explain",
        "prompt_md": "Explain why the chain rule is needed.",
    }


def test_mixed_quiz_grades_each_kind(
    kinds_client: tuple[TestClient, KindsGateway],
) -> None:
    client, gateway = kinds_client
    activity = generate_mixed(client)
    questions = client.get(f"/api/v1/quiz/activities/{activity['id']}/questions").json()
    by_type = {question["type"]: question for question in questions}
    attempt = client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()

    cloze = client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={
            "question_id": by_type["cloze"]["id"],
            "response": ["2*x", "cos(x)"],
        },
    )
    assert cloze.status_code == 200, cloze.text
    assert cloze.json()["correct"] is True
    assert cloze.json()["graded_by"] == "deterministic"

    matching = client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": by_type["matching"]["id"], "response": [0, 1]},
    )
    assert matching.status_code == 200, matching.text
    assert matching.json()["correct"] is True

    essay = client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={
            "question_id": by_type["essay"]["id"],
            "response": "Composite functions need the inner derivative.",
        },
    )
    assert essay.status_code == 200, essay.text
    body = essay.json()
    assert body["correct"] is True
    assert body["graded_by"] == "rubric"
    assert body["feedback"][0]["md"] == "essay: correct (AI-graded)"
    assert "Names composite functions" in body["feedback"][1]["md"]
    assert gateway.prompts[-1].startswith("Grade the student's answer against the rubric.")


def test_caq_export_round_trips_new_kinds(
    kinds_client: tuple[TestClient, KindsGateway],
) -> None:
    client, _gateway = kinds_client
    activity = generate_mixed(client)
    exported = client.get(f"/api/v1/quiz/activities/{activity['id']}/export")
    assert exported.status_code == 200, exported.text
    document = exported.json()
    assert {question["type"] for question in document["questions"]} == {
        "cloze",
        "matching",
        "essay",
    }
    matching = next(
        question for question in document["questions"] if question["type"] == "matching"
    )
    assert matching["answer"]["pairs"][0]["left"] == "$x^2$"

    imported = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": make_course(client)},
        json=document,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["valid"] == 3
    imported_questions = client.get(
        f"/api/v1/quiz/activities/{imported.json()['activity']['id']}/questions"
    ).json()
    assert {question["type"] for question in imported_questions} == {
        "cloze",
        "matching",
        "essay",
    }


def test_validators_reject_malformed_structural_and_rubric_payloads(
    kinds_client: tuple[TestClient, KindsGateway],
) -> None:
    client, _gateway = kinds_client
    course_id = make_course(client)
    base = {
        "stem_md": "stem",
        "explanation_md": "why",
        "concepts": ["c"],
        "skill": "conceptual",
        "bloom": "understand",
        "difficulty": 2,
        "expected_time_sec": 30,
    }
    bad_matching = {
        "questions": [
            {**base, "type": "matching", "answer": {"pairs": [{"left": "a", "right": "b"}]}}
        ]
    }
    bad_cloze = {
        "questions": [
            {**base, "type": "cloze", "answer": {"prompt_md": "no blanks", "answers": []}}
        ]
    }
    bad_essay = {
        "questions": [{**base, "type": "essay", "answer": {"prompt_md": "x", "rubric": []}}]
    }
    for document in (bad_matching, bad_cloze, bad_essay):
        response = client.post(
            "/api/v1/quiz/import",
            params={"dry_run": "true", "course_id": course_id},
            json=document,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["valid"] == 0
        assert payload["results"][0]["problems"]


def test_unknown_question_type_still_rejected(
    kinds_client: tuple[TestClient, KindsGateway],
) -> None:
    client, _gateway = kinds_client
    response = client.post(
        "/api/v1/quiz/generate",
        json={
            "count": 1,
            "course_id": make_course(client),
            "question_types": ["not_a_kind"],
        },
    )
    assert response.status_code == 422
