import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app
from app.services.platform.scan_scheduler import ScanScheduler

GOOD_QUIZ = {
    "$schema": "saq/v1",
    "title": "Scheduled inbox quiz",
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


class NoAI:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None

    def describe(
        self,
        title: str,
        markdown: str,
        course_id: str | None = None,
    ) -> dict[str, Any] | None:
        return None


class QuietGateway(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(self, task: str, course_id: str | None = None) -> ResolvedModel:
        return ResolvedModel(
            provider_id="1",
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
        course_id: str | None = None,
    ) -> str:
        return "ok"


class RecordingJobs:
    def __init__(self) -> None:
        self.woken = 0

    def wake(self) -> None:
        self.woken += 1


def make_scheduler(inbox_dir: Path, published: list[tuple[str, dict[str, Any]]]) -> ScanScheduler:
    import tempfile

    data_dir = Path(tempfile.mkdtemp(prefix="sa-inbox-scheduler-"))
    app = create_app(
        Settings(data_dir=data_dir, log_level="WARNING"),
        gateway=QuietGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    scheduler = ScanScheduler(
        app.state.session_factory,
        app.state.settings.blobs_dir,
        RecordingJobs(),  # type: ignore[arg-type]
        lambda topic, payload: published.append((topic, payload)),
        interval_sec=300,
        inbox_dir=inbox_dir,
    )
    return scheduler


def test_inbox_scan_discovers_entries_and_publishes_once(tmp_path: Path) -> None:
    inbox = tmp_path / "import-inbox"
    inbox.mkdir()
    published: list[tuple[str, dict[str, Any]]] = []
    scheduler = make_scheduler(inbox, published)

    (inbox / "new.caq.json").write_text(json.dumps(GOOD_QUIZ), encoding="utf-8")

    entries = scheduler.scan_inbox(force=True)
    assert [entry["filename"] for entry in entries] == ["new.caq.json"]
    assert entries[0]["ok"] is True

    scheduler.scan_inbox(force=True)
    assert len([item for item in published if item[0] == "inbox"]) == 1

    (inbox / "new.caq.json").write_text(
        json.dumps({**GOOD_QUIZ, "title": "Changed"}), encoding="utf-8"
    )
    scheduler.scan_inbox(force=True)
    staged = [payload for topic, payload in published if topic == "inbox"]
    assert len(staged) == 2
    assert staged[-1]["count"] == 1


def test_disposition_files_are_not_rescanned(tmp_path: Path) -> None:
    inbox = tmp_path / "import-inbox"
    inbox.mkdir()
    published: list[tuple[str, dict[str, Any]]] = []
    scheduler = make_scheduler(inbox, published)

    (inbox / "done.caq.json.imported").write_text("{}", encoding="utf-8")
    (inbox / "bad.json.rejected").write_text("{}", encoding="utf-8")

    assert scheduler.scan_inbox(force=True) == []


def test_inbox_errors_do_not_break_the_source_pass(tmp_path: Path) -> None:
    inbox = tmp_path / "not-a-directory"
    inbox.write_text("file", encoding="utf-8")
    published: list[tuple[str, dict[str, Any]]] = []
    scheduler = make_scheduler(inbox, published)

    assert scheduler.scan_all(force=True) == {}
    assert scheduler.scan_inbox(force=True) == []


def test_notifications_surface_staged_imports(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app = create_app(
        Settings(data_dir=app_dir, log_level="WARNING"),
        gateway=QuietGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        inbox = Path(client.get("/api/v1/quiz/inbox/path").json()["path"])
        (inbox / "staged.caq.json").write_text(json.dumps(GOOD_QUIZ), encoding="utf-8")
        payload = client.get("/api/v1/notifications").json()
        filenames = [entry["filename"] for entry in payload["staged_imports"]]
        assert filenames == ["staged.caq.json"]
        assert payload["staged_imports"][0]["question_count"] == 1
