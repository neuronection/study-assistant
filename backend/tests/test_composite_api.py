import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

COMPOSITE_ANSWER: dict[str, Any] = {
    "parts": [
        {"type": "numeric", "value": "3", "tolerance": 0.01},
        {
            "type": "equation",
            "value": "9",
            "follow_through": "a**2",
        },
    ],
}

COMPOSITE_QUESTION: dict[str, Any] = {
    "type": "composite",
    "stem_md": "(a) Find $x$ where $3x = 9$. (b) Compute $x^2$ using (a).",
    "answer": COMPOSITE_ANSWER,
    "explanation_md": "x = 3, so x^2 = 9.",
    "concepts": ["algebra"],
    "skill": "procedural",
    "bloom": "apply",
    "difficulty": 3,
    "expected_time_sec": 120,
}


class CompositeGateway(LLMGateway):
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
            external_id="composite-model",
            label="composite-model",
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
def composite_client() -> Iterator[TestClient]:
    gateway = CompositeGateway([json.dumps({"questions": [COMPOSITE_QUESTION]})])
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-composite-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Algebra"}).json()["id"])


def generate_composite_quiz(client: TestClient) -> Any:
    created = client.post(
        "/api/v1/quiz/generate",
        json={
            "count": 1,
            "course_id": make_course(client),
            "question_types": ["composite"],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def submit(client: TestClient, attempt_id: int, question_id: int, response: Any) -> Any:
    result = client.post(
        f"/api/v1/quiz/attempts/{attempt_id}/answers",
        json={"question_id": question_id, "response": response},
    )
    assert result.status_code == 200, result.text
    return result.json()


def attempt_id_for(client: TestClient, activity_id: int) -> int:
    return int(
        client.post(f"/api/v1/quiz/activities/{activity_id}/attempts").json()["id"]
    )


def test_generate_and_public_input(composite_client: TestClient) -> None:
    activity = generate_composite_quiz(composite_client)
    question = composite_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()[0]
    assert question["type"] == "composite"
    assert question["flag"] == "ok"
    assert question["input"] == {
        "widget": "composite",
        "parts": [{"type": "numeric"}, {"type": "equation"}],
    }


def test_exact_and_follow_through_flows(composite_client: TestClient) -> None:
    activity = generate_composite_quiz(composite_client)
    question = composite_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()[0]

    exact = submit(
        composite_client,
        attempt_id_for(composite_client, activity["id"]),
        question["id"],
        ["3", "9"],
    )
    assert exact["correct"] is True
    assert exact["partial_credit"] == 1.0

    follow = submit(
        composite_client,
        attempt_id_for(composite_client, activity["id"]),
        question["id"],
        ["4", "16"],
    )
    assert follow["correct"] is False
    assert follow["partial_credit"] == 0.5
    assert "follow_through" in follow["error_tags"]
    assert any("follow-through" in block["md"] for block in follow["feedback"])


def test_report_carries_composite_response(composite_client: TestClient) -> None:
    activity = generate_composite_quiz(composite_client)
    question = composite_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()[0]
    attempt_id = attempt_id_for(composite_client, activity["id"])
    submit(composite_client, attempt_id, question["id"], ["3", "9"])
    composite_client.post(f"/api/v1/quiz/attempts/{attempt_id}/finish")
    report = composite_client.get(f"/api/v1/quiz/attempts/{attempt_id}/report").json()
    assert report["answers"][0]["question_type"] == "composite"
    assert report["answers"][0]["response"] == ["3", "9"]


def test_caq_round_trip(composite_client: TestClient) -> None:
    course_id = make_course(composite_client)
    document = {
        "title": "Composite import",
        "questions": [
            {
                "id": "q1",
                "type": "composite",
                "stem_md": "(a) x. (b) x^2.",
                "answer": COMPOSITE_ANSWER,
                "explanation_md": "Chain.",
                "concepts": ["algebra"],
                "skill": "procedural",
                "bloom": "apply",
                "difficulty": 3,
                "expected_time_sec": 120,
            }
        ],
    }
    imported = composite_client.post(
        "/api/v1/quiz/import",
        params={"course_id": course_id, "dry_run": False},
        json=document,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["valid"] == 1
