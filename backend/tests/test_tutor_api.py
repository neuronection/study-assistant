import contextlib
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


class TutorGateway(LLMGateway):
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
            external_id="tutor-model",
            label="tutor-model",
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


@contextlib.contextmanager
def make_client(responses: list[str]) -> Iterator[TestClient]:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-tutor-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=TutorGateway(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def create_exercise(client: TestClient) -> int:
    created = client.post(
        "/api/v1/exercises",
        json={
            "title": "Differentiate step by step",
            "course_id": make_course(client),
            "steps": [
                {
                    "prompt_md": "Compute $\\frac{d}{dx} x^2$.",
                    "expected": {"value": "2x"},
                },
                {
                    "prompt_md": "Compute $\\frac{d}{dx} x^3$.",
                    "expected": {"value": "3*x^2"},
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    exercise_id: int = created.json()["id"]
    return exercise_id


def test_exercise_full_flow_with_hints_and_independence() -> None:
    with make_client(
        [
            "Which rule governs derivatives of products of two functions?",
            "What identity relates $u'v$ and $uv'$ for a product?",
        ]
    ) as client:
        exercise_id = create_exercise(client)
        session = client.post(f"/api/v1/exercises/{exercise_id}/sessions").json()
        assert session["status"] == "active"

        wrong = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer",
            json={"response": "3x"},
        ).json()
        assert wrong["correct"] is False
        assert wrong["error_class"] in ("conceptual", "procedural", "misread")

        hint1 = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/hint",
            json={"level": 1, "last_response": "3x"},
        ).json()
        assert hint1["level"] == 1
        assert hint1["violations"] is None
        assert "?" in hint1["markdown"]

        skip = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/hint", json={"level": 4}
        )
        assert skip.status_code == 422

        hint2 = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/hint", json={"level": 2}
        )
        assert hint2.status_code == 200

        right = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer",
            json={"response": "x + x"},
        ).json()
        assert right["correct"] is True
        assert right["advanced"] is True
        assert right["session"]["current_step_idx"] == 1

        final = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer",
            json={"response": "3*x*x"},
        ).json()
        assert final["correct"] is True
        assert final["session"]["status"] == "completed"
        score = final["session"]["independence_score"]
        assert score is not None and 0.0 < score < 1.0


def test_hint_repair_loop_strips_leaked_answer() -> None:
    with make_client(
        [
            "Just write $x \\cdot x$ and you are done.",
            "Think about what operation, applied twice, returns the base.",
        ]
    ) as client:
        exercise = client.post(
            "/api/v1/exercises",
            json={
                "title": "Squares",
                "course_id": make_course(client),
                "steps": [{"prompt_md": "Compute $x \\cdot x$.", "expected": {"value": "x^2"}}],
            },
        ).json()
        session = client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
        hint = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/hint", json={"level": 1}
        ).json()
        assert "x \\cdot x" not in hint["markdown"]
        assert hint["violations"] is None
        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, TutorGateway)
        assert len(gateway.calls) == 2
        repair_prompt = " ".join(
            message.content if isinstance(message.content, str) else ""
            for message in gateway.calls[1]
        )
        assert "broke the rules" in repair_prompt


def test_audit_logged_for_tutor_hints() -> None:
    with make_client(["What does the product rule say?"]) as client:
        exercise_id = create_exercise(client)
        session = client.post(f"/api/v1/exercises/{exercise_id}/sessions").json()
        client.post(
            f"/api/v1/exercises/sessions/{session['id']}/hint", json={"level": 1}
        )
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            rows = db.execute(
                text(
                    "SELECT context_type, direction, model FROM ai_interactions "
                    "WHERE context_type = 'tutor'"
                )
            ).all()
        assert len(rows) == 1
        context_type, direction, model = rows[0]
        assert context_type == "tutor"
        assert direction == "hint level 1"
        assert model == "tutor-model"


def test_socratic_mode_requires_question() -> None:
    with make_client(
        ["The product rule applies here, consider its structure carefully."]
    ) as client:
        exercise_id = create_exercise(client)
        session = client.post(
            f"/api/v1/exercises/{exercise_id}/sessions?socratic=true"
        ).json()
        hint = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/hint", json={"level": 1}
        ).json()
        assert hint["level"] == 1
