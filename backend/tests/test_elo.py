import json
from typing import Any

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app
from app.services.study.elo import (
    expected_score,
    is_elo_outlier,
    k_factor,
    rating_to_difficulty,
    seeded_item_rating,
)


class TestEloMath:
    def test_seeded_rating_maps_difficulty(self) -> None:
        assert seeded_item_rating(1) == 900.0
        assert seeded_item_rating(3) == 1100.0
        assert seeded_item_rating(5) == 1300.0
        assert seeded_item_rating(None) == 1100.0
        assert seeded_item_rating(99) == 1300.0

    def test_expected_score_symmetry(self) -> None:
        assert expected_score(1000.0, 1000.0) == 0.5
        assert expected_score(1300.0, 1000.0) > 0.5
        assert expected_score(1300.0, 1000.0) + expected_score(1000.0, 1300.0) == 1.0

    def test_k_declines_with_attempts(self) -> None:
        assert k_factor(0) == 32.0
        assert k_factor(10) == 22.0
        assert k_factor(100) == 8.0

    def test_rating_to_difficulty(self) -> None:
        assert rating_to_difficulty(900.0) == 1
        assert rating_to_difficulty(1100.0) == 3
        assert rating_to_difficulty(1500.0) == 5

    def test_outlier_threshold(self) -> None:
        assert not is_elo_outlier(None, 20, 3)
        assert not is_elo_outlier(1100.0, 5, 3)
        assert not is_elo_outlier(1150.0, 20, 3)
        assert is_elo_outlier(1300.0, 20, 3)


SINGLE_QUESTION = json.dumps(
    {
        "questions": [
            {
                "type": "single",
                "stem_md": "What is $2+2$?",
                "options_md": ["3", "4"],
                "answer": {"index": 1},
                "explanation_md": "Addition.",
                "concepts": ["derivatives"],
                "skill": "procedural",
                "bloom": "apply",
                "difficulty": 2,
                "expected_time_sec": 30,
            }
        ]
    }
)


class EloGateway(LLMGateway):
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
            external_id="elo-model",
            label="elo-model",
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
        return SINGLE_QUESTION


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


def make_client() -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-elo-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=EloGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def answer_question(client: TestClient, mode: str) -> None:
    course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
    activity = client.post(
        "/api/v1/quiz/generate", json={"count": 1, "course_id": course_id}
    ).json()
    question = client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()[0]
    attempt = client.post(
        f"/api/v1/quiz/activities/{activity['id']}/attempts", params={"mode": mode}
    ).json()
    answered = client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": question["id"], "response": 0},
    )
    assert answered.status_code == 200, answered.text


def test_exam_attempts_do_not_update_ratings() -> None:
    client = make_client()
    with client:
        answer_question(client, "exam")
        from fastapi import FastAPI

        app = client.app
        assert isinstance(app, FastAPI)
        from sqlalchemy import select

        from app.domain.models import ItemStat

        with app.state.session_factory() as session:
            stat = session.scalars(select(ItemStat)).first()
            assert stat is None or stat.rating is None


def test_practice_attempts_update_item_and_student_cell() -> None:
    client = make_client()
    with client:
        answer_question(client, "practice")
        from fastapi import FastAPI

        app = client.app
        assert isinstance(app, FastAPI)
        from sqlalchemy import select

        from app.domain.models import ConceptSkillRating, ItemStat

        with app.state.session_factory() as session:
            stat = session.scalars(select(ItemStat)).first()
            assert stat is not None
            assert stat.rating is not None
            assert stat.rating_count == 1
            cell = session.scalars(select(ConceptSkillRating)).first()
            assert cell is not None
            assert cell.concept == "derivatives"
            assert cell.skill == "procedural"
            assert cell.rating is not None
            assert cell.rating_count == 1
            item_expected = seeded_item_rating(2.0)
            assert stat.rating != item_expected
