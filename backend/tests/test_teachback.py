import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.core.config import Settings
from app.domain.models import Activity, Answer, Attempt, Question
from app.main import create_app


@fixture
def gateway() -> ScriptedGateway:
    return ScriptedGateway([])


@fixture
def client(
    tmp_path: Path, gateway: ScriptedGateway
) -> Iterator[tuple[TestClient, ScriptedGateway, FastAPI]]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway, app


def make_course(client: TestClient, title: str = "Teach-back course") -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def root_node(client: TestClient, course_id: int) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    return int(tree[0]["id"])


def test_teach_back_creates_explain_exercise(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        response = test_client.post(
            "/api/v1/exercises/teach-back",
            json={"course_id": course_id, "concept": "Chain rule"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["kind"] == "explain"
        assert body["title"] == "Teach-back: Chain rule"

        steps = test_client.get(f"/api/v1/exercises/{body['id']}/steps").json()
        step = steps[0]
        assert step["input"]["widget"] == "essay"
        assert step["input"]["prompt_md"].startswith("Explain Chain rule")
        assert "rubric" not in step["input"]


def test_teach_back_from_node_uses_node_title(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        root = root_node(test_client, course_id)
        node = test_client.post(
            f"/api/v1/courses/{course_id}/nodes",
            json={"course_id": course_id, "parent_id": root, "title": "Eigenvectors"},
        ).json()
        response = test_client.post(
            "/api/v1/exercises/teach-back",
            json={"course_id": course_id, "node_id": int(node["id"])},
        )
        assert response.status_code == 201, response.text
        assert response.json()["title"] == "Teach-back: Eigenvectors"


def test_teach_back_result_lands_in_diagnostics(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        db = app.state.session_factory()
        try:
            from app.domain.models import Exercise, ExerciseStep

            exercise = Exercise(
                profile_id=1,
                course_id=course_id,
                title="Teach-back: Eigenvalues",
                kind="explain",
                created_from={"source": "teach-back"},
            )
            db.add(exercise)
            db.flush()
            db.add(
                ExerciseStep(
                    exercise_id=exercise.id,
                    order_idx=0,
                    prompt=[{"type": "text", "md": "Explain eigenvalues"}],
                    expected={
                        "kind": "explain",
                        "prompt_md": "Explain eigenvalues",
                        "rubric": [],
                        "concept": "Eigenvalues",
                        "skill": "explanation",
                    },
                )
            )
            db.commit()
            exercise_id = int(exercise.id)
        finally:
            db.close()

        gateway.responses.append(
            json.dumps(
                {
                    "verdict": "correct",
                    "score": 1.0,
                    "rationale": [
                        {"rubric_id": "definition", "reason": "stated correctly"}
                    ],
                }
            )
        )
        started = test_client.post(f"/api/v1/exercises/{exercise_id}/sessions")
        assert started.status_code in (200, 201), started.text
        session_id = int(started.json()["id"])
        answered = test_client.post(
            f"/api/v1/exercises/sessions/{session_id}/answer",
            json={
                "response": "For A v = λ v, λ is the eigenvalue scaling the "
                "eigenvector; example: stretching (1,0) by 2 gives eigenvalue 2."
            },
        )
        assert answered.status_code == 200, answered.text

        materialized = test_client.post("/api/v1/analytics/materialize")
        assert materialized.status_code == 200, materialized.text
        diagnostics = test_client.get("/api/v1/analytics/diagnostics").json()
        cells = diagnostics.get("weakness_matrix") or []
        assert any(
            cell["concept"] == "Eigenvalues" and cell["skill"] == "explanation"
            for cell in cells
        )


def test_teachback_recommendation_after_repeated_drilling(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)

        db = test_client.app.state.session_factory()  # type: ignore[attr-defined]
        try:
            db.add(
                Activity(
                    profile_id=1, course_id=course_id, type="quiz", title="drills"
                )
            )
            db.commit()
            activity = (
                db.query(Activity)
                .filter(Activity.course_id == course_id, Activity.type == "quiz")
                .first()
            )
            assert activity is not None
            question = Question(
                activity_id=activity.id,
                type="choice",
                stem=[{"type": "text", "md": "integrate by parts"}],
                options=[{"type": "text", "md": "ok"}],
                answer={"index": 0},
                tags=["integration by parts"],
                skill="procedural",
            )
            db.add(question)
            db.flush()
            now = datetime.now(UTC)
            for index, correct in enumerate(
                [False, False, True, False, False, True, False]
            ):
                attempt = Attempt(activity_id=activity.id, mode="practice")
                db.add(attempt)
                db.flush()
                db.add(
                    Answer(
                        attempt_id=attempt.id,
                        question_id=question.id,
                        correct=correct,
                        created_at=now - timedelta(hours=7 - index),
                    )
                )
            db.commit()
        finally:
            db.close()

        recs = test_client.get("/api/v1/analytics/recommendations").json()
        teachback = [rec for rec in recs if rec["kind"] == "teachback"]
        assert teachback, "expected a teach-back recommendation"
        assert teachback[0]["concept"] == "integration by parts"
        assert teachback[0]["skill"] == "procedural"
        assert teachback[0]["evidence"]["n"] >= 6
