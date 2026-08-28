import json
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

CAQ_DOC = {
    "$schema": "caq/v1",
    "title": "Pkg quiz",
    "questions": [
        {
            "id": "q1",
            "type": "single",
            "stem_md": "Derivative of $x^3$?",
            "options_md": ["$3x^2$", "$x^2$", "$3x$"],
            "answer": {"index": 0},
            "explanation_md": "Power rule.",
            "concepts": ["derivatives"],
            "skill": "procedural",
            "bloom": "apply",
            "difficulty": 2,
            "expected_time_sec": 40,
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

    tmp = Path(tempfile.mkdtemp(prefix="ca-p7s3-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=QuietGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def test_linked_folder_scan_lifecycle(tmp_path: Path) -> None:
    client = make_client()
    with client:
        lectures = tmp_path / "lectures"
        lectures.mkdir()
        (lectures / "week1.md").write_text("# Week 1\n\nPower rule: $(x^n)' = nx^{n-1}$")

        course = client.post("/api/v1/courses", json={"title": "Linked"})
        assert course.status_code == 201
        course_id = course.json()["id"]

        bad = client.post("/api/v1/sources", json={"label": "L", "path": "/nonexistent"})
        assert bad.status_code == 422

        no_course = client.post(
            "/api/v1/sources", json={"label": "L", "path": str(lectures)}
        )
        assert no_course.status_code == 422

        created = client.post(
            "/api/v1/sources",
            json={"label": "Lectures", "path": str(lectures), "course_id": course_id},
        )
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]

        first = client.post(f"/api/v1/sources/{source_id}/scan").json()
        assert first["stats"]["new"] == 1
        assert first["queued_jobs"] >= 1

        listing = client.get("/api/v1/materials").json()
        assert any(material["filename"] == "week1.md" for material in listing)

        second = client.post(f"/api/v1/sources/{source_id}/scan").json()
        assert second["stats"]["unchanged"] == 1
        assert second["stats"]["new"] == 0

        time.sleep(0.01)
        (lectures / "week1.md").write_text("# Week 1 revised\n\nMore content here.")
        third = client.post(f"/api/v1/sources/{source_id}/scan").json()
        assert third["stats"]["updated"] == 1

        (lectures / "week1.md").unlink()
        fourth = client.post(f"/api/v1/sources/{source_id}/scan").json()
        assert fourth["stats"]["missing"] == 1

        deleted = client.delete(f"/api/v1/sources/{source_id}")
        assert deleted.status_code == 204


def test_course_delete_purges_linked_source_folder(tmp_path: Path) -> None:
    client = make_client()
    with client:
        lectures = tmp_path / "purge-me"
        lectures.mkdir()
        (lectures / "notes.md").write_text("# Notes\n\nChain rule: $(uv)' = u'v + uv'$")

        course_id = make_course(client)

        created = client.post(
            "/api/v1/sources",
            json={"label": "Lectures", "path": str(lectures), "course_id": course_id},
        )
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]

        scanned = client.post(f"/api/v1/sources/{source_id}/scan").json()
        assert scanned["stats"]["new"] == 1
        assert any(
            material["filename"] == "notes.md"
            for material in client.get("/api/v1/materials").json()
        )

        deleted = client.delete(
            f"/api/v1/courses/{course_id}", params={"confirmed_backup": True}
        )
        assert deleted.status_code == 200, deleted.text
        assert client.get("/api/v1/courses").json() == []
        assert client.get("/api/v1/sources").json() == []
        assert client.get("/api/v1/materials").json() == []


def make_course(client: TestClient, headers: dict[str, str] | None = None) -> int:
    created = client.post(
        "/api/v1/courses", json={"title": "Test course"}, headers=headers
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def test_profiles_create_and_header_scoping() -> None:
    client = make_client()
    with client:
        first = client.post("/api/v1/profiles", json={"name": "Exam prep"})
        assert first.status_code == 201, first.text
        second_id = first.json()["id"]
        scoped_headers = {"X-Profile-Id": str(second_id)}

        client.post(
            "/api/v1/notes",
            json={"title": "Default note", "course_id": make_course(client)},
        )
        scoped_course = make_course(client, scoped_headers)
        scoped = client.post(
            "/api/v1/notes",
            json={"title": "Scoped note", "course_id": scoped_course},
            headers=scoped_headers,
        )
        assert scoped.status_code == 201, scoped.text

        default_notes = client.get("/api/v1/notes").json()
        assert [note["title"] for note in default_notes["items"]] == ["Default note"]

        other_notes = client.get("/api/v1/notes", headers={"X-Profile-Id": str(second_id)}).json()
        assert [note["title"] for note in other_notes["items"]] == ["Scoped note"]

        listing = client.get("/api/v1/profiles").json()
        assert len(listing) == 2

        blocked = client.delete(f"/api/v1/profiles/{second_id}")
        assert blocked.status_code == 422
        assert "content" in blocked.json()["detail"]

        client.delete(
            f"/api/v1/courses/{scoped_course}",
            headers=scoped_headers,
            params={"confirmed_backup": True},
        )
        removed = client.delete(f"/api/v1/profiles/{second_id}")
        assert removed.status_code == 204


def test_qpkg_round_trip_and_integrity() -> None:
    client = make_client()
    with client:
        course_id = make_course(client)
        imported = client.post(
            "/api/v1/quiz/import",
            params={"dry_run": "false", "course_id": course_id},
            json=CAQ_DOC,
        )
        assert imported.status_code == 200, imported.text
        activity_id = imported.json()["activity"]["id"]

        exported = client.get(f"/api/v1/quiz/activities/{activity_id}/export-qpkg")
        assert exported.status_code == 200
        assert exported.headers["content-disposition"].endswith('.qpkg"')
        package = exported.content

        dry = client.post(
            "/api/v1/quiz/import-qpkg",
            params={"dry_run": "true", "course_id": course_id},
            files={"file": ("quiz.qpkg", package, "application/octet-stream")},
        )
        assert dry.status_code == 200, dry.text
        assert dry.json()["valid"] == 1

        committed = client.post(
            "/api/v1/quiz/import-qpkg",
            params={"dry_run": "false", "course_id": course_id},
            files={"file": ("quiz.qpkg", package, "application/octet-stream")},
        )
        assert committed.status_code == 200
        assert committed.json()["activity"]["question_count"] == 1

        import io
        import zipfile

        corrupted = io.BytesIO(package)
        with zipfile.ZipFile(corrupted, "a") as archive:
            archive.writestr("quiz.json", json.dumps({"title": "tampered", "questions": []}))
        tampered = client.post(
            "/api/v1/quiz/import-qpkg",
            params={"dry_run": "true", "course_id": course_id},
            files={"file": ("quiz.qpkg", corrupted.getvalue(), "application/octet-stream")},
        )
        assert tampered.status_code == 422
        assert "integrity" in tampered.json()["detail"]

        not_zip = client.post(
            "/api/v1/quiz/import-qpkg",
            params={"course_id": course_id},
            files={"file": ("quiz.qpkg", b"garbage", "application/octet-stream")},
        )
        assert not_zip.status_code == 422


def test_sample_course_onboarding() -> None:
    client = make_client()
    with client:
        created = client.post("/api/v1/onboarding/sample")
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["created"] is True
        assert body["materials"] == 3

        again = client.post("/api/v1/onboarding/sample").json()
        assert again["created"] is False

        courses = client.get("/api/v1/courses").json()
        sample = next(c for c in courses if c["title"] == "Calculus I (sample)")
        materials = client.get("/api/v1/materials", params={"course_id": sample["id"]}).json()
        assert len(materials) == 3
        assert all(material["status"] == "ready" for material in materials)

        hits = client.get("/api/v1/search", params={"q": "power rule"}).json()["hits"]
        assert len(hits) >= 1
