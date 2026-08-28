import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


class CardsGateway(LLMGateway):
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
            external_id="cards-model",
            label="cards-model",
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


def make_client(responses: list[str]) -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-cards-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=CardsGateway(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def cards_json(cards: list[dict[str, str]]) -> str:
    return json.dumps({"cards": cards})


def test_manual_card_validation() -> None:
    client = make_client([])
    with client:
        course_id = make_course(client)
        created = client.post(
            "/api/v1/flashcards",
            json={
                "kind": "cloze",
                "front_md": "The derivative of $x^2$ is {{2x}}",
                "back_md": "$2x$",
                "course_id": course_id,
            },
        )
        assert created.status_code == 201

        bad = client.post(
            "/api/v1/flashcards",
            json={
                "kind": "cloze",
                "front_md": "no deletion here",
                "back_md": "x",
                "course_id": course_id,
            },
        )
        assert bad.status_code == 422
        assert "deletion" in bad.json()["detail"]


def test_due_queue_and_review_scheduling() -> None:
    client = make_client([])
    with client:
        card_id = int(
            client.post(
                "/api/v1/flashcards",
                json={
                    "kind": "basic",
                    "front_md": "What is $\\frac{d}{dx} x^2$?",
                    "back_md": "$2x$",
                    "course_id": make_course(client),
                },
            ).json()["id"]
        )
        due = client.get("/api/v1/flashcards/due").json()
        assert [card["id"] for card in due] == [card_id]
        assert due[0]["state"] is None

        reviewed = client.post(
            f"/api/v1/flashcards/{card_id}/review", json={"rating": 3}
        )
        assert reviewed.status_code == 200
        body = reviewed.json()
        assert body["interval_days"] >= 1
        assert body["state"] == "learning"

        due_after = client.get("/api/v1/flashcards/due").json()
        assert [card["id"] for card in due_after] == []

        listing = client.get("/api/v1/flashcards").json()
        assert listing[0]["state"] == "learning"
        assert listing[0]["due_at"] is not None


def test_again_review_schedules_tomorrow_and_logs() -> None:
    client = make_client([])
    with client:
        card_id = int(
            client.post(
                "/api/v1/flashcards",
                json={
                    "kind": "basic",
                    "front_md": "F",
                    "back_md": "B",
                    "course_id": make_course(client),
                },
            ).json()["id"]
        )
        client.post(f"/api/v1/flashcards/{card_id}/review", json={"rating": 3})
        again = client.post(f"/api/v1/flashcards/{card_id}/review", json={"rating": 1})
        assert again.status_code == 200
        assert again.json()["interval_days"] == 1
        assert again.json()["state"] == "relearning"

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            rows = db.execute(
                text("SELECT rating, interval_days FROM review_log ORDER BY id")
            ).all()
        assert [row[0] for row in rows] == [3, 1]


CAQ_DOC = {
    "$schema": "caq/v1",
    "title": "Cards quiz",
    "questions": [
        {
            "id": "q1",
            "type": "single",
            "stem_md": "Derivative of $x^2$?",
            "options_md": ["$2x$", "$x$", "$x^2$"],
            "answer": {"index": 0},
            "explanation_md": "Power rule gives $2x$.",
            "concepts": ["derivatives"],
            "skill": "procedural",
            "bloom": "apply",
            "difficulty": 1,
            "expected_time_sec": 30,
            "misconceptions": {"1": "wrong_power_rule"},
        }
    ],
}


def seed_mistake(client: TestClient) -> int:
    course_id = make_course(client)
    imported = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": course_id},
        json=CAQ_DOC,
    )
    assert imported.status_code == 200, imported.text
    activity_id = int(imported.json()["activity"]["id"])
    question_id = int(
        client.get(f"/api/v1/quiz/activities/{activity_id}/questions").json()[0]["id"]
    )
    attempt_id = int(
        client.post(f"/api/v1/quiz/activities/{activity_id}/attempts").json()["id"]
    )
    answered = client.post(
        f"/api/v1/quiz/attempts/{attempt_id}/answers",
        json={"question_id": question_id, "response": 1},
    )
    assert answered.status_code == 200
    return course_id


def test_generation_repair_and_duplicate_rejection() -> None:
    good = cards_json(
        [
            {"kind": "basic", "front_md": "Q1", "back_md": "A1"},
            {"kind": "cloze", "front_md": "power rule: {{d/dx x^n}}", "back_md": "nx^{n-1}"},
        ]
    )
    client = make_client(["not json at all"])
    with client:
        course_id = seed_mistake(client)
        generated = client.post(
            "/api/v1/flashcards/generate",
            json={"source": "mistakes", "count": 2, "course_id": course_id},
        )
        assert generated.status_code == 422

    duplicate_batch = cards_json([{"kind": "basic", "front_md": "Q1", "back_md": "A1"}])
    client2 = make_client([good, duplicate_batch, duplicate_batch, duplicate_batch])
    with client2:
        course_id = seed_mistake(client2)
        created = client2.post(
            "/api/v1/flashcards/generate",
            json={"source": "mistakes", "count": 2, "course_id": course_id},
        )
        assert created.status_code == 201, created.text

        duplicate = client2.post(
            "/api/v1/flashcards/generate",
            json={"source": "mistakes", "count": 1, "course_id": course_id},
        )
        assert duplicate.status_code == 422
        assert "duplicate" in duplicate.json()["detail"]


def test_source_requires_note_or_material() -> None:
    client = make_client([])
    with client:
        course_id = make_course(client)
        missing_note = client.post(
            "/api/v1/flashcards/generate",
            json={"source": "note", "course_id": course_id},
        )
        assert missing_note.status_code == 422
        bad_source = client.post(
            "/api/v1/flashcards/generate",
            json={"source": "dreams", "course_id": course_id},
        )
        assert bad_source.status_code == 422
