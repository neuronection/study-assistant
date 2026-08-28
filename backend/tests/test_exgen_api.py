import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


class ExgenGateway(LLMGateway):
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
            external_id="exgen-model",
            label="exgen-model",
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


def power_steps() -> list[dict[str, Any]]:
    return [
        {
            "prompt_md": "Compute $\\frac{d}{dx} x^2$.",
            "expected_kind": "math",
            "expected_value": "2x",
        },
        {"prompt_md": "Evaluate at $x=3$.", "expected_kind": "numeric", "expected_value": "6"},
    ]


def exercise_json(
    steps: list[dict[str, Any]] | None = None, title: str = "Chain rule practice"
) -> str:
    payload: dict[str, Any] = {
        "title": title,
        "context_md": "Differentiate step by step.",
        "difficulty": 2,
        "steps": steps or power_steps(),
    }
    return json.dumps(payload)


def make_client(responses: list[str]) -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-exgen-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=ExgenGateway(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def make_math_course(client: TestClient) -> int:
    types = {
        entry["key"]: entry["id"]
        for entry in client.get("/api/v1/skills/course-types").json()
    }
    return int(
        client.post(
            "/api/v1/courses",
            json={"title": "Calculus I", "course_type_id": types.get("math")},
        ).json()["id"]
    )


def test_generate_creates_validated_exercise() -> None:
    client = make_client([exercise_json()])
    with client:
        created = client.post(
            "/api/v1/exercises/generate",
            json={
                "course_id": make_course(client),
                "topic": "power rule",
                "difficulty": 2,
                "step_count": 2,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["step_count"] == 2
        steps = client.get(f"/api/v1/exercises/{body['id']}/steps").json()
        assert len(steps) == 2
        assert all(step["has_expected"] for step in steps)
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            rows = db.execute(
                text(
                    "SELECT context_type, direction FROM ai_interactions "
                    "WHERE context_type = 'exgen'"
                )
            ).all()
        assert len(rows) == 1
        assert rows[0][1] == "exercise generation"


def test_generate_rejects_unparseable_after_repairs() -> None:
    bad = exercise_json(
        steps=[
            {"prompt_md": "Compute.", "expected_kind": "math", "expected_value": "??"},
        ]
    )
    client = make_client([bad, bad, bad])
    with client:
        created = client.post(
            "/api/v1/exercises/generate", json={"course_id": make_course(client)}
        )
        assert created.status_code == 422
        assert "does not parse" in created.json()["detail"]
        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, ExgenGateway)
        assert len(gateway.calls) == 3


def test_generate_repair_loop_recovers() -> None:
    bad = exercise_json(steps=[{"prompt_md": "", "expected_kind": "math", "expected_value": "x"}])
    client = make_client([bad, exercise_json()])
    with client:
        created = client.post(
            "/api/v1/exercises/generate", json={"course_id": make_course(client)}
        )
        assert created.status_code == 201, created.text
        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, ExgenGateway)
        assert len(gateway.calls) == 2
        repair_prompt = " ".join(
            message.content if isinstance(message.content, str) else ""
            for message in gateway.calls[1]
        )
        assert "problems" in repair_prompt


def _create_manual_exercise(client: TestClient) -> int:
    created = client.post(
        "/api/v1/exercises",
        json={
            "title": "Squares",
            "course_id": make_course(client),
            "steps": [
                {"prompt_md": "Compute $\\frac{d}{dx} x^2$.", "expected": {"value": "2x"}},
                {"prompt_md": "Evaluate at $x=3$.", "expected": {"value": "6"}},
            ],
        },
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def test_get_single_exercise() -> None:
    with make_client([]) as client:
        exercise_id = _create_manual_exercise(client)
        body = client.get(f"/api/v1/exercises/{exercise_id}")
        assert body.status_code == 200, body.text
        payload = body.json()
        assert payload["id"] == exercise_id
        assert payload["title"] == "Squares"
        assert payload["step_count"] == 2
        assert payload["course_id"] is not None

        missing = client.get("/api/v1/exercises/999999")
        assert missing.status_code == 404


def test_similar_generates_isomorphic_variant() -> None:
    variant = exercise_json(
        steps=[
            {
                "prompt_md": "Compute $\\frac{d}{dx} x^3$.",
                "expected_kind": "math",
                "expected_value": "3x^2",
            },
            {"prompt_md": "Evaluate at $x=2$.", "expected_kind": "numeric", "expected_value": "12"},
        ],
        title="Squares (variant)",
    )
    client = make_client([variant])
    with client:
        source_id = _create_manual_exercise(client)
        similar = client.post(f"/api/v1/exercises/{source_id}/similar")
        assert similar.status_code == 201, similar.text
        new_id = int(similar.json()["id"])
        assert new_id != source_id
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            row = db.execute(
                text("SELECT created_from FROM exercises WHERE id = :id"),
                {"id": new_id},
            ).one()
        created_from = json.loads(row[0])
        assert created_from["source"] == "similar"
        assert created_from["from_exercise_id"] == source_id


def test_similar_rejects_identical_variant() -> None:
    same = exercise_json(steps=power_steps())
    client = make_client([same, same, same])
    with client:
        source_id = _create_manual_exercise(client)
        similar = client.post(f"/api/v1/exercises/{source_id}/similar")
        assert similar.status_code == 422


def test_drill_patterns_and_start() -> None:
    client = make_client(
        [
            exercise_json(
                steps=[
                    {
                        "prompt_md": "Differentiate $-3x^2$.",
                        "expected_kind": "math",
                        "expected_value": "-6x",
                    },
                    {
                        "prompt_md": "Evaluate at $x=1$.",
                        "expected_kind": "numeric",
                        "expected_value": "-6",
                    },
                ],
                title="Sign slip drill",
            )
        ]
    )
    with client:
        course_id = make_math_course(client)
        patterns = client.get(
            f"/api/v1/exercises/drills/patterns?course_id={course_id}"
        )
        assert patterns.status_code == 200
        entries = {entry["pattern"]: entry for entry in patterns.json()}
        assert "sign_slip" in entries
        assert all(entry["occurrences"] == 0 for entry in entries.values())
        assert all(entry["source"] == "seeded" for entry in entries.values())

        drill = client.post(
            "/api/v1/exercises/drills",
            json={"pattern": "sign_slip", "course_id": course_id},
        )
        assert drill.status_code == 201, drill.text
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            row = db.execute(
                text("SELECT created_from FROM exercises ORDER BY id DESC LIMIT 1")
            ).one()
        created_from = json.loads(row[0])
        assert created_from["source"] == "drill"
        assert created_from["pattern"] == "sign_slip"

        prompt_text = " ".join(
            message.content if isinstance(message.content, str) else ""
            for message in (app.state.gateway.calls[0])
        )
        assert "sign" in prompt_text.lower()

        unknown = client.post(
            "/api/v1/exercises/drills",
            json={"pattern": "nope", "course_id": course_id},
        )
        assert unknown.status_code == 422

        unresolved = client.post(
            "/api/v1/exercises/drills",
            json={"pattern": "sign_slip", "course_id": make_course(client)},
        )
        assert unresolved.status_code == 422


def test_transcript_lists_hints_and_answers() -> None:
    client = make_client([])
    with client:
        exercise_id = _create_manual_exercise(client)
        session = client.post(f"/api/v1/exercises/{exercise_id}/sessions").json()
        client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer", json={"response": "5x"}
        )
        transcript = client.get(f"/api/v1/exercises/sessions/{session['id']}/transcript")
        assert transcript.status_code == 200
        entries = transcript.json()
        assert len(entries) == 1
        assert entries[0]["kind"] == "answer"
        assert entries[0]["correct"] is False
        assert entries[0]["error_class"]


def test_summary_note_requires_completed_session() -> None:
    client = make_client([])
    with client:
        exercise_id = _create_manual_exercise(client)
        session = client.post(f"/api/v1/exercises/{exercise_id}/sessions").json()
        early = client.post(f"/api/v1/exercises/sessions/{session['id']}/summary-note")
        assert early.status_code == 422

        first = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer", json={"response": "2x"}
        )
        assert first.status_code == 200, first.text
        second = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer", json={"response": "6"}
        )
        assert second.status_code == 200, second.text

        created = client.post(f"/api/v1/exercises/sessions/{session['id']}/summary-note")
        assert created.status_code == 200, created.text
        body = created.json()
        note_id = body["note_id"]
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from app.domain.models import Note

            note = db.get(Note, note_id)
            assert note is not None
            assert note.tags == ["session-summary"]
            assert "session summary" in (note.body or [{}])[0].get("md", "").lower()
