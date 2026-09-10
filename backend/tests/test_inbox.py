import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

GOOD_QUIZ = {
    "$schema": "caq/v1",
    "title": "Inbox quiz",
    "questions": [
        {
            "id": "q1",
            "type": "single",
            "stem_md": "Derivative of $x^2$?",
            "options_md": ["$2x$", "$x$", "$2$"],
            "answer": {"index": 0},
            "explanation_md": "Power rule.",
            "concepts": ["derivatives"],
            "skill": "procedural",
            "bloom": "apply",
            "difficulty": 2,
            "expected_time_sec": 30,
        }
    ],
}

BAD_QUIZ = {
    "title": "Broken",
    "questions": [
        {"id": "q1", "type": "single", "stem_md": "", "answer": {"index": 0}}
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


class QuietGateway(LLMGateway):
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
            external_id="quiet",
            label="quiet",
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

    tmp = Path(tempfile.mkdtemp(prefix="ca-inbox-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=QuietGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def test_inbox_scan_stages_and_authoring_kit_written(tmp_path: Path) -> None:
    client = make_client()
    with client:
        info = client.get("/api/v1/quiz/inbox/path").json()
        inbox = Path(info["path"])
        assert inbox.is_dir()
        assert (inbox / "AUTHORING.md").is_file()
        assert (inbox / "schema.json").is_file()

        (inbox / "good.caq.json").write_text(json.dumps(GOOD_QUIZ), encoding="utf-8")
        (inbox / "broken.json").write_text(json.dumps(BAD_QUIZ), encoding="utf-8")
        (inbox / "junk.txt").write_text("ignored", encoding="utf-8")

        entries = {entry["filename"]: entry for entry in client.get("/api/v1/quiz/inbox").json()}
        assert set(entries) == {"good.caq.json", "broken.json"}
        assert entries["good.caq.json"]["ok"] is True
        assert entries["good.caq.json"]["question_count"] == 1
        assert entries["broken.json"]["ok"] is False
        assert entries["broken.json"]["problems"]


def test_inbox_import_commits_and_rejects(tmp_path: Path) -> None:
    client = make_client()
    with client:
        inbox = Path(client.get("/api/v1/quiz/inbox/path").json()["path"])
        (inbox / "good.caq.json").write_text(json.dumps(GOOD_QUIZ), encoding="utf-8")
        (inbox / "broken.json").write_text(json.dumps(BAD_QUIZ), encoding="utf-8")

        course_id = make_course(client)

        imported = client.post(
            "/api/v1/quiz/inbox/good.caq.json/import", params={"course_id": course_id}
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["valid"] == 1
        assert (inbox / "good.caq.json.imported").is_file()
        assert not (inbox / "good.caq.json").exists()

        rejected = client.post(
            "/api/v1/quiz/inbox/broken.json/import", params={"course_id": course_id}
        )
        assert rejected.status_code == 200
        assert rejected.json()["valid"] == 0
        assert (inbox / "broken.json.rejected").is_file()
        assert (inbox / "broken.json.rejected.txt").is_file()

        missing = client.post(
            "/api/v1/quiz/inbox/nope.json/import", params={"course_id": course_id}
        )
        assert missing.status_code == 404

        traversal = client.post(
            "/api/v1/quiz/inbox/..%2Fapp.db/import", params={"course_id": course_id}
        )
        assert traversal.status_code in (404, 405, 422)


def test_inbox_qpkg_staged_and_imported(tmp_path: Path) -> None:
    client = make_client()
    with client:
        inbox = Path(client.get("/api/v1/quiz/inbox/path").json()["path"])
        import io
        import zipfile

        from app.pipelines.qpkg import build_qpkg

        package = build_qpkg(GOOD_QUIZ, "test")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"format": "wrong"}))
            archive.writestr("quiz.json", "{}")
        (inbox / "deck.qpkg").write_bytes(package)
        (inbox / "bad.qpkg").write_bytes(buffer.getvalue())

        entries = {entry["filename"]: entry for entry in client.get("/api/v1/quiz/inbox").json()}
        assert entries["deck.qpkg"]["ok"] is True
        assert entries["bad.qpkg"]["ok"] is False

        imported = client.post(
            "/api/v1/quiz/inbox/deck.qpkg/import",
            params={"course_id": make_course(client)},
        )
        assert imported.status_code == 200
        assert imported.json()["valid"] == 1
        assert (inbox / "deck.qpkg.imported").is_file()
