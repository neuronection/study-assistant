import base64
import time
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


class ScriptedGateway(LLMGateway):
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
            external_id="scripted",
            label="scripted",
            caps=["text", "vision"],
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

    def stream(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        text = self.generate(task, messages, model)
        for i in range(0, len(text), 8):
            yield text[i : i + 8]

    def stream_events(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        from app.ai.gateway import StreamChunk

        for delta in self.stream(task, messages, model):
            yield StreamChunk("text", delta)


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

    tmp = Path(tempfile.mkdtemp(prefix="ca-notes2-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=ScriptedGateway(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


PNG = base64.b64encode(b"fakepng").decode()


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def test_recognize_returns_latex_candidates() -> None:
    client = make_client(["We differentiate: $x^2$ gives $2x$ as the result."])
    with client:
        recognized = client.post("/api/v1/quiz/recognize", json={"png_base64": PNG})
        assert recognized.status_code == 200, recognized.text
        body = recognized.json()
        assert "2x" in body["latex_candidates"]
        assert "$2x$" in body["markdown"] or "2x" in body["markdown"]


def test_recognize_rejects_bad_base64() -> None:
    client = make_client([])
    with client:
        bad = client.post("/api/v1/quiz/recognize", json={"png_base64": "!!!"})
        assert bad.status_code == 422


def test_notes_ocr_uses_skill_service_override() -> None:
    client = make_client(["$x^2$"])
    with client:
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from app.services.platform.skills import SkillService

            service = SkillService(db)
            service.save_version(
                "notes.transcribe",
                scope_type="system",
                scope_ref=None,
                system_template="OVERRIDE transcript",
            )
            db.commit()
        recognized = client.post("/api/v1/quiz/recognize", json={"png_base64": PNG})
        assert recognized.status_code == 200, recognized.text
        prompt = app.state.gateway.calls[-1][0].content
        assert "OVERRIDE transcript" in prompt
        assert recognized.json()["markdown"] == "$x^2$"


def test_handwritten_answer_stores_strokes_and_input_mode() -> None:
    client = make_client([])
    with client:
        quiz = {
            "$schema": "caq/v1",
            "title": "Write quiz",
            "questions": [
                {
                    "id": "q1",
                    "type": "equation",
                    "stem_md": "Differentiate $x^2$.",
                    "answer": {"value": "2x"},
                    "explanation_md": "Power rule.",
                    "concepts": ["derivatives"],
                    "skill": "procedural",
                    "bloom": "apply",
                    "difficulty": 1,
                    "expected_time_sec": 60,
                }
            ],
        }
        activity = client.post(
            "/api/v1/quiz/import",
            params={"dry_run": "false", "course_id": make_course(client)},
            json=quiz,
        ).json()["activity"]
        question_id = client.get(
            f"/api/v1/quiz/activities/{activity['id']}/questions"
        ).json()[0]["id"]
        attempt_id = int(
            client.post(f"/api/v1/quiz/activities/{activity['id']}/attempts").json()["id"]
        )
        answered = client.post(
            f"/api/v1/quiz/attempts/{attempt_id}/answers",
            json={
                "question_id": question_id,
                "response": "2x",
                "input_mode": "write",
                "strokes": [{"points": [[0, 0], [5, 5]], "width": 2}],
            },
        )
        assert answered.status_code == 200
        assert answered.json()["correct"] is True

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            row = db.execute(
                text("SELECT response, input_mode FROM answers WHERE attempt_id = :a"),
                {"a": attempt_id},
            ).one()
        import json as jsonlib

        response = jsonlib.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert row[1] == "write"
        assert response["strokes"][0]["points"] == [[0, 0], [5, 5]]
        assert response["value"] == "2x"


def test_note_action_summarize() -> None:
    client = make_client(["Summary: the power rule gives $nx^{n-1}$."])
    with client:
        note_id = int(
            client.post(
                "/api/v1/notes",
                json={
                    "title": "Rules",
                    "body_md": "Power rule details here.",
                    "course_id": make_course(client),
                },
            ).json()["id"]
        )
        action = client.post(f"/api/v1/notes/{note_id}/actions", json={"action": "summarize"})
        assert action.status_code == 200, action.text
        assert "power rule" in action.json()["markdown"]
        assert action.json()["violations"] is None

        unknown = client.post(f"/api/v1/notes/{note_id}/actions", json={"action": "sing"})
        assert unknown.status_code == 422

        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, ScriptedGateway)
        prompt = " ".join(
            message.content if isinstance(message.content, str) else ""
            for message in gateway.calls[0]
        )
        assert "Power rule details" in prompt


def test_chat_includes_latest_notes_context() -> None:
    client = make_client(["The rule follows from the material [1]."])
    with client:
        course = client.post("/api/v1/courses", json={"title": "Notes"})
        assert course.status_code == 201
        client.post(
            "/api/v1/notes",
            json={
                "title": "U-substitution notes",
                "body_md": "Let $u = g(x)$.",
                "course_id": course.json()["id"],
            },
        )
        material_file = ("sub.txt", b"u-substitution replaces the inner function.", "text/plain")
        client.post(
            "/api/v1/materials",
            params={"course_id": course.json()["id"]},
            files={"file": material_file},
        )
        session = client.post("/api/v1/chat/sessions", json={}).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "explain u-substitution"},
        )
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            messages = client.get(f"/api/v1/chat/sessions/{session['id']}/messages").json()
            if messages and messages[-1]["role"] == "assistant":
                break
            time.sleep(0.05)
        assert messages and messages[-1]["role"] == "assistant"

        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, ScriptedGateway)
        first_prompt = " ".join(
            message.content if isinstance(message.content, str) else ""
            for message in gateway.calls[0]
        )
        assert "U-substitution notes" in first_prompt
        assert "do NOT cite" in first_prompt
