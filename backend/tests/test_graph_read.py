import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

GRAPH_ANSWER: dict[str, Any] = {
    "expression": "sin(x)",
    "x_min": -6.5,
    "x_max": 6.5,
    "mode": "value",
    "point_x": 2.0,
}

GRAPH_QUESTION: dict[str, Any] = {
    "type": "graph_read",
    "stem_md": "The graph shows $f(x) = \\sin(x)$. What is $f(2)$? Round to one decimal.",
    "answer": GRAPH_ANSWER,
    "explanation_md": "f(2) = sin(2) ≈ 0.91.",
    "concepts": ["trig"],
    "skill": "conceptual",
    "bloom": "apply",
    "difficulty": 2,
    "expected_time_sec": 60,
}


class GraphGateway(LLMGateway):
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
            external_id="graph-model",
            label="graph-model",
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
def graph_client() -> Iterator[TestClient]:
    gateway = GraphGateway([json.dumps({"questions": [GRAPH_QUESTION]})])
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-graph-read-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Trig"}).json()["id"])


def generate_graph_quiz(client: TestClient) -> Any:
    created = client.post(
        "/api/v1/quiz/generate",
        json={
            "count": 1,
            "course_id": make_course(client),
            "question_types": ["graph_read"],
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


def test_generate_materializes_chart_and_answer(graph_client: TestClient) -> None:
    activity = generate_graph_quiz(graph_client)
    question = graph_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()[0]
    assert question["type"] == "graph_read"
    assert question["flag"] == "ok"
    assert question["input"] == {"widget": "graph_read", "mode": "value"}
    chart_blocks = [block for block in question["stem"] if block.get("type") == "chart"]
    assert len(chart_blocks) == 1
    series = chart_blocks[0]["plotly"]["data"][0]
    assert len(series["x"]) == 96
    assert len(series["y"]) == 96
    assert "answer" not in question


def test_value_grading_flow(graph_client: TestClient) -> None:
    activity = generate_graph_quiz(graph_client)
    question = graph_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()[0]

    good = submit(
        graph_client, attempt_id_for(graph_client, activity["id"]), question["id"], {"value": 0.9}
    )
    assert good["correct"] is True

    bad = submit(
        graph_client, attempt_id_for(graph_client, activity["id"]), question["id"], {"value": 2.0}
    )
    assert bad["correct"] is False
    assert "wrong_value" in bad["error_tags"]

    garbage = submit(
        graph_client, attempt_id_for(graph_client, activity["id"]), question["id"], "nope"
    )
    assert garbage["correct"] is False
    assert garbage["partial_credit"] == 0.0


def test_model_authored_value_is_ignored(graph_client: TestClient) -> None:
    activity = generate_graph_quiz(graph_client)
    exported = graph_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/export"
    ).json()
    stored = exported["questions"][0]["answer"]
    import math

    assert abs(stored["value"] - math.sin(2.0)) < 1e-5
