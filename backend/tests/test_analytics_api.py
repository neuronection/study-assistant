from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

CAQ_DOC = {
    "$schema": "caq/v1",
    "title": "Analytics quiz",
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
            "difficulty": 2,
            "expected_time_sec": 30,
            "misconceptions": {"1": "wrong_power_rule"},
        },
        {
            "id": "q2",
            "type": "truefalse",
            "stem_md": "A continuous function always has a limit at every point.",
            "answer": {"value": True},
            "explanation_md": "By definition.",
            "concepts": ["limits"],
            "skill": "conceptual",
            "bloom": "understand",
            "difficulty": 3,
            "expected_time_sec": 30,
        },
    ],
}


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


class StaticGateway(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="static",
            label="static",
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
        return "ok"


def make_client() -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-analytics-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=StaticGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def seed_answers(
    client: TestClient, course_id: int, plan: list[tuple[int, Any, int]]
) -> dict[str, Any]:
    imported = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": course_id},
        json=CAQ_DOC,
    )
    assert imported.status_code == 200, imported.text
    activity = imported.json()["activity"]
    questions = client.get(f"/api/v1/quiz/activities/{activity['id']}/questions").json()
    attempt_id = int(
        client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()["id"]
    )
    for question_index, response, time_ms in plan:
        answered = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/answers",
            json={
                "question_id": questions[question_index]["id"],
                "response": response,
                "time_ms": time_ms,
            },
        )
        assert answered.status_code == 200, answered.text
    client.post(f"/api/v1/quiz/attempts/{attempt_id}/finish")
    return {"activity": activity, "questions": questions}


def test_weakness_matrix_and_error_profile() -> None:
    client = make_client()
    with client:
        course_id = make_course(client)
        seed_answers(
            client,
            course_id,
            [
                (0, 0, 10000),
                (0, 1, 12000),
                (0, 1, 8000),
                (1, True, 20000),
            ],
        )
        diagnostics = client.get("/api/v1/analytics/diagnostics")
        assert diagnostics.status_code == 200
        body = diagnostics.json()
        matrix = body["weakness_matrix"]
        cells = {(c["concept"], c["skill"]): c for c in matrix}
        proc = cells[("derivatives", "procedural")]
        assert proc["n"] == 3
        assert proc["accuracy"] == round(1 / 3, 4)
        assert proc["enough_data"] is True
        assert proc["avg_time_ratio"] is not None
        concept = cells[("limits", "conceptual")]
        assert concept["n"] == 1
        assert concept["enough_data"] is False

        tags = {entry["tag"]: entry for entry in body["error_profile"]}
        assert tags["wrong_power_rule"]["total"] == 2

        speed = {entry["concept"]: entry for entry in body["speed_accuracy"]}
        assert speed["derivatives"]["quadrant"] == "rushing"


def test_overview_goal_and_streak() -> None:
    client = make_client()
    with client:
        course_id = make_course(client)
        seed_answers(client, course_id, [(0, 1, 15000), (1, True, 25000)])
        overview = client.get("/api/v1/analytics/overview")
        assert overview.status_code == 200
        body = overview.json()
        assert body["today"]["answers_n"] == 2
        assert body["today"]["correct_n"] == 1
        assert body["goal"] == 20
        assert body["streak"] == 1
        assert body["due_cards"] == 0
        assert body["total_xp"] == 12
        assert body["level"] >= 1

        set_goal = client.put("/api/v1/analytics/goal", json={"answers_per_day": 5})
        assert set_goal.status_code == 200
        assert set_goal.json()["answers_per_day"] == 5
        refreshed = client.get("/api/v1/analytics/overview").json()
        assert refreshed["goal"] == 5


def test_recommendations_read_drill_review() -> None:
    client = make_client()
    with client:
        course_id = make_course(client)
        seed_answers(
            client,
            course_id,
            [
                (0, 1, 9000),
                (0, 1, 9000),
                (0, 0, 9000),
                (1, False, 30000),
                (1, False, 30000),
                (1, True, 30000),
            ],
        )
        recs = client.get("/api/v1/analytics/recommendations")
        assert recs.status_code == 200
        entries = recs.json()
        kinds = {entry["kind"] for entry in entries}
        assert "read" in kinds
        assert "drill" in kinds
        drill = next(entry for entry in entries if entry["kind"] == "drill")
        assert drill["concept"] == "derivatives"
        assert drill["evidence"]["misses"] == 2

        due_cards = client.post(
            "/api/v1/flashcards",
            json={
                "kind": "basic",
                "front_md": "F",
                "back_md": "B",
                "course_id": course_id,
            },
        )
        assert due_cards.status_code == 201
        recs_with_cards = client.get("/api/v1/analytics/recommendations").json()
        review = next(
            (entry for entry in recs_with_cards if entry["kind"] == "review"), None
        )
        assert review is not None
        assert review["evidence"]["due_cards"] >= 1


def test_item_analysis_and_flags() -> None:
    client = make_client()
    with client:
        course_id = make_course(client)
        seed = seed_answers(client, course_id, [(0, 0, 10000), (1, True, 20000)])
        items = client.get("/api/v1/analytics/items")
        assert items.status_code == 200
        entries = items.json()
        assert len(entries) == 2
        by_id = {entry["question_id"]: entry for entry in entries}
        first = by_id[seed["questions"][0]["id"]]
        assert first["n_attempts"] == 1
        assert first["distractor_selection"] == {"0": 1}
        assert first["flag"] == "ok"

        materialize = client.post("/api/v1/analytics/materialize")
        assert materialize.status_code == 200
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            rows = db.execute(
                text("SELECT COUNT(*) FROM concept_skill_stats")
            ).one()
            rollups = db.execute(text("SELECT COUNT(*) FROM daily_rollups")).one()
            item_rows = db.execute(text("SELECT COUNT(*) FROM item_stats")).one()
        assert rows[0] >= 1
        assert rollups[0] >= 1
        assert item_rows[0] == 2


def test_exam_answers_excluded_from_mastery() -> None:
    client = make_client()
    with client:
        course_id = make_course(client)
        imported = client.post(
            "/api/v1/quiz/import",
            params={"dry_run": "false", "course_id": course_id},
            json=CAQ_DOC,
        )
        activity = imported.json()["activity"]
        questions = client.get(
            f"/api/v1/quiz/activities/{activity['id']}/questions"
        ).json()
        practice = int(
            client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()["id"]
        )
        client.post(
            f"/api/v1/quiz/attempts/{practice}/answers",
            json={"question_id": questions[0]["id"], "response": 0, "time_ms": 9000},
        )
        exam = int(
            client.post(
                f"/api/v1/quiz/activities/{activity['id']}/attempts?mode=exam"
            ).json()["id"]
        )
        client.post(
            f"/api/v1/quiz/attempts/{exam}/answers",
            json={"question_id": questions[0]["id"], "response": 1, "time_ms": 9000},
        )
        diagnostics = client.get("/api/v1/analytics/diagnostics").json()
        proc = next(
            c
            for c in diagnostics["weakness_matrix"]
            if c["concept"] == "derivatives"
        )
        assert proc["n"] == 1
        assert proc["accuracy"] == 1.0
