import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

WEAK_AREA_QUIZ = json.dumps(
    {
        "questions": [
            {
                "type": "single",
                "stem_md": "Which rule differentiates $f(g(x))$?",
                "options_md": ["chain rule", "product rule", "quotient rule", "sum rule"],
                "answer": {"index": 0},
                "explanation_md": "Composite functions use the chain rule.",
                "concepts": ["chain rule"],
                "skill": "conceptual",
                "bloom": "understand",
                "difficulty": 2,
                "expected_time_sec": 45,
            }
        ]
    }
)


class ScriptedGateway(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)
        self.calls: list[tuple[str, list[Message]]] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="scripted",
            label="scripted",
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
        self.calls.append((task, messages))
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

    tmp = Path(tempfile.mkdtemp(prefix="ca-p7s2-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=ScriptedGateway(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def test_weak_area_quiz_generation_focuses_topic() -> None:
    client = make_client([WEAK_AREA_QUIZ])
    with client:
        generated = client.post(
            "/api/v1/quiz/generate",
            json={
                "course_id": make_course(client),
                "topic": "chain rule",
                "skill": "conceptual",
                "count": 1,
                "difficulty": 2,
            },
        )
        assert generated.status_code == 201, generated.text
        body = generated.json()
        assert body["title"].startswith("chain rule")
        assert body["question_count"] == 1

        questions = client.get(f"/api/v1/quiz/activities/{body['id']}/questions").json()
        assert questions[0]["skill"] == "conceptual"

        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, ScriptedGateway)
        task, messages = gateway.calls[0]
        assert task == "quizgen"
        prompt = " ".join(
            message.content if isinstance(message.content, str) else ""
            for message in messages
        )
        assert "FOCUS TOPIC" in prompt
        assert "chain rule" in prompt
        assert "SKILL FOCUS" in prompt
        assert "conceptual" in prompt


def test_backup_export_restore_round_trip() -> None:
    source = make_client([])
    with source:
        note = source.post(
            "/api/v1/notes",
            json={
                "title": "Survivor note",
                "body_md": "$e^{i\\pi}$",
                "course_id": make_course(source),
            },
        )
        assert note.status_code == 201, note.text
        exported = source.get("/api/v1/backup/export")
        assert exported.status_code == 200
        assert exported.headers["content-disposition"].endswith('.zip"')
        package = exported.content

    target = make_client([])
    with target:
        restored = target.post(
            "/api/v1/backup/restore",
            files={"file": ("backup.zip", package, "application/zip")},
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["status"] == "restored"

        listing = target.get("/api/v1/notes")
        titles = [entry["title"] for entry in listing.json()["items"]]
        assert "Survivor note" in titles


def test_restore_rejects_garbage() -> None:
    client = make_client([])
    with client:
        not_zip = client.post(
            "/api/v1/backup/restore",
            files={"file": ("backup.zip", b"definitely not a zip", "application/zip")},
        )
        assert not_zip.status_code == 422

        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"format": "ca-backup/v1"}))
        incomplete = client.post(
            "/api/v1/backup/restore",
            files={"file": ("backup.zip", buffer.getvalue(), "application/zip")},
        )
        assert incomplete.status_code == 422
