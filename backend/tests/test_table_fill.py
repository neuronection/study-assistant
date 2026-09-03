import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

TABLE_ANSWER: dict[str, Any] = {
    "headers": ["p", "q", "p and q"],
    "rows": [
        {
            "label": "row 1",
            "cells": [
                {"kind": "locked", "value": "true"},
                {"kind": "locked", "value": "true"},
                {"kind": "text", "value": "true"},
            ],
        },
        {
            "label": "row 2",
            "cells": [
                {"kind": "locked", "value": "true"},
                {"kind": "locked", "value": "false"},
                {"kind": "text", "value": "false"},
            ],
        },
    ],
}

TABLE_QUESTION: dict[str, Any] = {
    "type": "table_fill",
    "stem_md": "Complete the truth table.",
    "answer": TABLE_ANSWER,
    "explanation_md": "Conjunction is true only when both operands are true.",
    "concepts": ["logic"],
    "skill": "conceptual",
    "bloom": "apply",
    "difficulty": 2,
    "expected_time_sec": 90,
}


class TableGateway(LLMGateway):
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
            external_id="table-model",
            label="table-model",
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
def table_client() -> Iterator[TestClient]:
    gateway = TableGateway([json.dumps({"questions": [TABLE_QUESTION]})])
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-table-fill-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Logic"}).json()["id"])


def generate_table_quiz(client: TestClient) -> Any:
    created = client.post(
        "/api/v1/quiz/generate",
        json={"count": 1, "course_id": make_course(client), "question_types": ["table_fill"]},
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


def test_generate_and_public_input(table_client: TestClient) -> None:
    activity = generate_table_quiz(table_client)
    question = table_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()[0]
    assert question["type"] == "table_fill"
    assert question["flag"] == "ok"
    grid = question["input"]
    assert grid["widget"] == "table_fill"
    assert grid["headers"] == ["p", "q", "p and q"]
    assert grid["cells"][0][0] == {"kind": "locked", "text": "true"}
    assert grid["cells"][0][2] == {"kind": "text"}
    assert "value" not in grid["cells"][0][2]


def test_per_cell_grading_flow(table_client: TestClient) -> None:
    activity = generate_table_quiz(table_client)
    question = table_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()[0]
    attempt_id = int(
        table_client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()[
            "id"
        ]
    )
    exact = submit(
        table_client, attempt_id, question["id"], [["", "", "true"], ["", "", "false"]]
    )
    assert exact["correct"] is True
    assert exact["partial_credit"] == 1.0

    attempt2 = int(
        table_client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()[
            "id"
        ]
    )
    partial = submit(
        table_client, attempt2, question["id"], [["", "", "true"], ["", "", ""]]
    )
    assert partial["correct"] is False
    assert partial["partial_credit"] == 0.5
    assert "wrong_cell" in partial["error_tags"]

    attempt3 = int(
        table_client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()[
            "id"
        ]
    )
    garbage = submit(table_client, attempt3, question["id"], "nope")
    assert garbage["correct"] is False
    assert garbage["partial_credit"] == 0.0


def test_report_carries_table_response(table_client: TestClient) -> None:
    activity = generate_table_quiz(table_client)
    question = table_client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()[0]
    attempt_id = int(
        table_client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()[
            "id"
        ]
    )
    payload = [["", "", "true"], ["", "", "false"]]
    submit(table_client, attempt_id, question["id"], payload)
    table_client.post(f"/api/v1/quiz/attempts/{attempt_id}/finish")
    report = table_client.get(f"/api/v1/quiz/attempts/{attempt_id}/report").json()
    assert report["answers"][0]["question_type"] == "table_fill"
    assert report["answers"][0]["response"] == payload


def test_caq_round_trip(table_client: TestClient) -> None:
    course_id = make_course(table_client)
    document = {
        "title": "Table import",
        "questions": [
            {
                "id": "q1",
                "type": "table_fill",
                "stem_md": "Complete the table.",
                "answer": TABLE_ANSWER,
                "explanation_md": "Conjunction.",
                "concepts": ["logic"],
                "skill": "conceptual",
                "bloom": "apply",
                "difficulty": 2,
                "expected_time_sec": 90,
            }
        ],
    }
    imported = table_client.post(
        "/api/v1/quiz/import",
        params={"course_id": course_id, "dry_run": False},
        json=document,
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["valid"] == 1
    exported = table_client.get(
        f"/api/v1/quiz/activities/{body['activity']['id']}/export"
    ).json()
    assert exported["questions"][0]["answer"]["rows"][0]["cells"][2]["value"] == "true"
