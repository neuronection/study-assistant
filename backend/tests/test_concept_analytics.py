import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
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
                "type": "truefalse",
                "stem_md": "The chain rule differentiates composites.",
                "answer": {"value": True},
                "explanation_md": "Product of derivatives.",
                "concepts": ["chain rule"],
                "skill": "conceptual",
                "bloom": "remember",
                "difficulty": 2,
                "expected_time_sec": 30,
            }
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
        raise TaskUnassigned(task)

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
def quiz_client() -> Iterator[TestClient]:
    gateway = QuizGateway([QUIZ_JSON])
    tmp = Path(tempfile.mkdtemp(prefix="ca-concept-quiz-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client


def make_course(client: TestClient, title: str) -> int:
    return int(client.post("/api/v1/courses", json={"title": title}).json()["id"])


def commit_concepts(client: TestClient, course_id: int) -> int:
    committed = client.post(
        f"/api/v1/courses/{course_id}/concepts/commit",
        json={
            "concepts": [{"name": "chain rule", "description": None, "aliases": []}],
            "links": [],
            "nodes": [],
        },
    )
    assert committed.status_code == 200, committed.text
    graph = client.get(f"/api/v1/courses/{course_id}/concepts").json()
    concept_row = graph["concepts"][0]
    return int(concept_row["id"])


def test_materialize_writes_concept_id(client: TestClient) -> None:
    course_id = make_course(client, "Stats")
    concept_id = commit_concepts(client, course_id)
    imported = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": course_id},
        json={
            "$schema": "caq/v1",
            "title": "Concept quiz",
            "questions": [
                {
                    "id": "q1",
                    "type": "truefalse",
                    "stem_md": "Chain rule applies to composites.",
                    "answer": True,
                    "explanation_md": "Yes.",
                    "concepts": ["chain rule"],
                    "skill": "conceptual",
                    "bloom": "remember",
                    "difficulty": 1,
                    "expected_time_sec": 30,
                },
                {
                    "id": "q2",
                    "type": "truefalse",
                    "stem_md": "Unrelated.",
                    "answer": False,
                    "explanation_md": "No.",
                    "concepts": ["other"],
                    "skill": "procedural",
                    "bloom": "remember",
                    "difficulty": 1,
                    "expected_time_sec": 30,
                },
            ],
        },
    )
    assert imported.status_code == 200, imported.text
    activity_id = imported.json()["activity"]["id"]

    attempt = client.post(
        f"/api/v1/quiz/activities/{activity_id}/attempts?mode=practice"
    ).json()
    for question in client.get(
        f"/api/v1/quiz/activities/{activity_id}/questions"
    ).json():
        client.post(
            f"/api/v1/quiz/attempts/{attempt['id']}/answers",
            json={"question_id": question["id"], "response": True},
        )
    client.post(f"/api/v1/quiz/attempts/{attempt['id']}/finish")

    materialized = client.post("/api/v1/analytics/materialize")
    assert materialized.status_code == 200

    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as db:
        from sqlalchemy import select

        from app.domain.models import ConceptSkillStat

        chain_rows = db.scalars(
            select(ConceptSkillStat).where(ConceptSkillStat.concept == "chain rule")
        ).all()
        assert chain_rows
        assert any(row.concept_id == concept_id for row in chain_rows)
        other_rows = db.scalars(
            select(ConceptSkillStat).where(ConceptSkillStat.concept == "other")
        ).all()
        assert other_rows
        assert all(row.concept_id is None for row in other_rows)


def test_quiz_generate_by_concept(quiz_client: TestClient) -> None:
    course_id = make_course(quiz_client, "Scoped")
    concept_id = commit_concepts(quiz_client, course_id)

    missing = quiz_client.post(
        "/api/v1/quiz/generate",
        json={"course_id": course_id, "concept_id": 99999, "count": 1},
    )
    assert missing.status_code == 404

    mismatch = quiz_client.post(
        "/api/v1/quiz/generate",
        json={"course_id": course_id + 100, "concept_id": concept_id, "count": 1},
    )
    assert mismatch.status_code in (404, 422)

    generated = quiz_client.post(
        "/api/v1/quiz/generate",
        json={"course_id": course_id, "concept_id": concept_id, "count": 1},
    )
    assert generated.status_code == 201, generated.text
    assert "chain rule" in generated.json()["title"].lower()
