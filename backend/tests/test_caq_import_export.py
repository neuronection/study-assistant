from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel, TaskUnassigned
from app.core.config import Settings
from app.main import create_app


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


CAQ_DOC: dict[str, Any] = {
    "$schema": "caq/v1",
    "title": "Chain Rule — Practice Set",
    "questions": [
        {
            "id": "q1",
            "type": "single",
            "stem_md": "Differentiate $f(x) = x^2\\sin x$",
            "options_md": ["$2x\\sin x$", "$2x\\cos x$", "$x^2\\cos x + 2x\\sin x$"],
            "answer": 2,
            "explanation_md": "Product rule: $2x\\sin x + x^2\\cos x$.",
            "concepts": ["chain rule", "product rule"],
            "skill": "procedural",
            "bloom": "apply",
            "difficulty": 3,
            "expected_time_sec": 120,
            "misconceptions": {"0": "forgot_product_rule", "1": "confused_sin_cos"},
            "sympy_check": {"expected": "2*x*sin(x) + x**2*cos(x)"},
        },
        {
            "id": "q2",
            "type": "truefalse",
            "stem_md": "The derivative of $e^x$ is $e^x$.",
            "answer": True,
            "explanation_md": "Exponential is its own derivative.",
            "concepts": ["exponentials"],
            "skill": "conceptual",
            "bloom": "remember",
            "difficulty": 1,
            "expected_time_sec": 30,
        },
        {
            "id": "q3",
            "type": "equation",
            "stem_md": "Compute $\\int 2x\\,dx$.",
            "answer": "x^2 + C",
            "explanation_md": "Reverse power rule.",
            "concepts": ["integration"],
            "skill": "procedural",
            "bloom": "apply",
            "difficulty": 2,
            "expected_time_sec": 90,
            "sympy_check": {"expected": "x**2"},
        },
    ],
}


@pytest.fixture
def caq_client() -> Iterator[TestClient]:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-caq-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=UnassignedGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


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


def import_caq(
    client: TestClient, course_id: int, dry_run: str, document: dict[str, Any]
) -> Any:
    return client.post(
        "/api/v1/quiz/import",
        params={"dry_run": dry_run, "course_id": course_id},
        json=document,
    )


def test_import_dry_run_validates_all_questions(caq_client: TestClient) -> None:
    response = import_caq(caq_client, make_course(caq_client), "true", CAQ_DOC)
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["valid"] == 3
    assert all(result["ok"] for result in body["results"])
    listing = caq_client.get("/api/v1/quiz/activities")
    assert listing.json() == []


def test_import_dry_run_flags_missing_metadata(caq_client: TestClient) -> None:
    broken = {
        "title": "Broken",
        "questions": [
            {
                "type": "single",
                "stem_md": "Pick one",
                "options_md": ["a", "b"],
                "answer": 0,
            }
        ],
    }
    body = import_caq(caq_client, make_course(caq_client), "true", broken).json()
    assert body["valid"] == 0
    problems = body["results"][0]["problems"]
    assert any("explanation" in problem for problem in problems)
    assert any("concepts" in problem for problem in problems)


def test_import_commit_creates_gradable_quiz(caq_client: TestClient) -> None:
    body = import_caq(caq_client, make_course(caq_client), "false", CAQ_DOC).json()
    assert body["dry_run"] is False
    activity = body["activity"]
    assert activity["question_count"] == 3

    questions = caq_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()
    assert all(question["flag"] == "ok" for question in questions)

    attempt = caq_client.post(
        f"/api/v1/quiz/activities/{activity['id']}/attempts"
    ).json()
    answer = caq_client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[2]["id"], "response": "x*x"},
    ).json()
    assert answer["correct"] is True
    assert answer["graded_by"] == "symPy"


def test_export_roundtrips_caq(caq_client: TestClient) -> None:
    import_caq(caq_client, make_course(caq_client), "false", CAQ_DOC)
    listing = caq_client.get("/api/v1/quiz/activities").json()
    activity_id = listing[0]["id"]

    exported = caq_client.get(f"/api/v1/quiz/activities/{activity_id}/export")
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    document = exported.json()
    assert document["$schema"] == "caq/v1"
    assert len(document["questions"]) == 3
    first = document["questions"][0]
    assert first["type"] == "single"
    assert first["answer"] == 2
    assert first["misconceptions"]["0"] == "forgot_product_rule"
    assert first["sympy_check"]["expected"] == "2*x*sin(x) + x**2*cos(x)"

    reimport = import_caq(caq_client, make_course(caq_client), "true", document).json()
    assert reimport["valid"] == 3


def test_attempts_and_mistakes_listing(caq_client: TestClient) -> None:
    created = import_caq(caq_client, make_course(caq_client), "false", CAQ_DOC).json()
    activity_id = created["activity"]["id"]
    questions = caq_client.get(f"/api/v1/quiz/activities/{activity_id}/questions").json()
    attempt = caq_client.post(f"/api/v1/quiz/activities/{activity_id}/attempts").json()

    caq_client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[0]["id"], "response": 0},
    )
    caq_client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[1]["id"], "response": True},
    )
    caq_client.post(f"/api/v1/quiz/attempts/{attempt['id']}/finish")

    attempts = caq_client.get("/api/v1/quiz/attempts").json()
    assert len(attempts) == 1
    assert attempts[0]["title"] == "Chain Rule — Practice Set"
    assert attempts[0]["score"] == pytest.approx(1 / 3, abs=1e-3)

    mistakes = caq_client.get("/api/v1/quiz/mistakes").json()
    assert len(mistakes) == 1
    assert mistakes[0]["error_tags"] == ["forgot_product_rule"]
    assert "Differentiate" in mistakes[0]["stem_excerpt"]
