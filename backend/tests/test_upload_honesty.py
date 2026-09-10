import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.gateway import LLMGateway, Message, ResolvedModel, TaskUnassigned
from app.core.config import Settings
from app.domain.models import Blob, Material
from app.main import create_app
from app.services.content.materials import (
    UnsupportedMaterialError,
    accepted_suffixes,
    detect_kind,
)


def test_detect_kind_matrix() -> None:
    assert detect_kind("lecture.pdf") == "pdf"
    assert detect_kind("scan.PNG") == "image"
    assert detect_kind("notes.md") == "md"
    assert detect_kind("notes.markdown") == "md"
    assert detect_kind("plain.txt") == "txt"
    assert detect_kind("handout.docx") == "docx"
    assert detect_kind("deck.pptx") == "pptx"
    assert detect_kind("book.epub") == "epub"
    assert detect_kind("page.html") == "html"
    assert detect_kind("page.HTM") == "html"
    assert detect_kind("lecture.mp3") == "audio"
    assert detect_kind("voice.m4a") == "audio"
    assert detect_kind("recording.webm") == "video"
    assert detect_kind("movie.mp4") == "video"
    with pytest.raises(UnsupportedMaterialError) as excinfo:
        detect_kind("legacy.doc")
    assert excinfo.value.suffix == ".doc"
    with pytest.raises(UnsupportedMaterialError):
        detect_kind("archive.zip")


def test_accepted_suffixes_sorted_and_complete() -> None:
    suffixes = accepted_suffixes()
    assert suffixes == sorted(suffixes)
    for suffix in (".pdf", ".docx", ".pptx", ".epub", ".html", ".mp3", ".mp4"):
        assert suffix in suffixes


class QuietGateway(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        raise TaskUnassigned(task)

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        return "ok"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=QuietGateway(),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_upload_unsupported_returns_machine_422_and_writes_nothing(
    client: TestClient,
) -> None:
    course_id = client.post("/api/v1/courses", json={"title": "Honest"}).json()["id"]
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("notes.rtf", b"rich text", "application/rtf")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason"] == "unsupported_type"
    assert detail["suffix"] == ".rtf"
    assert ".docx" in detail["accepted"]

    listed = client.get("/api/v1/materials", params={"course_id": course_id}).json()
    assert listed == []
    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as db:
        assert db.scalars(select(Material)).all() == []
        assert db.scalars(select(Blob)).all() == []


def test_accepted_types_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/materials/accepted")
    assert response.status_code == 200
    body = response.json()
    assert body["suffixes"] == accepted_suffixes()
    assert body["accept"] == ",".join(body["suffixes"])
    assert ".txt" in body["accept"]


def test_scan_skips_unsupported_files_with_reason(tmp_path: Path) -> None:
    lectures = tmp_path / "lectures"
    lectures.mkdir()
    (lectures / "real.pdf").write_bytes(b"%PDF-1.4 not really parseable")
    (lectures / "notes.rtf").write_bytes(b"rich text")
    (lectures / "archive.exe").write_bytes(b"binary")
    app = create_app(
        Settings(data_dir=tmp_path / "data", log_level="WARNING"),
        gateway=QuietGateway(),
    )
    with TestClient(app) as client:
        course_id = client.post("/api/v1/courses", json={"title": "Linked"}).json()["id"]
        created = client.post(
            "/api/v1/sources",
            json={
                "label": "Lectures",
                "path": str(lectures),
                "course_id": course_id,
                "include_globs": ["*"],
            },
        )
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]
        result = client.post(f"/api/v1/sources/{source_id}/scan")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["stats"]["skipped"] == 2
        assert body["stats"]["new"] == 1
        assert any("notes.rtf" in entry and ".rtf" in entry for entry in body["skipped"])
        assert any("archive.exe" in entry for entry in body["skipped"])
        materials = client.get("/api/v1/materials", params={"course_id": course_id}).json()
        assert [material["filename"] for material in materials] == ["real.pdf"]

        refused = client.post(
            f"/api/v1/sources/{source_id}/ingest",
            json={"relpath": "notes.rtf"},
        )
        assert refused.status_code == 422
        assert refused.json()["detail"]["reason"] == "unsupported_type"


def test_upload_convertible_kind_accepted_at_door(client: TestClient) -> None:
    course_id = client.post("/api/v1/courses", json={"title": "Kinds"}).json()["id"]
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("handout.docx", b"PK placeholder bytes")},
    )
    assert response.status_code == 200, response.text
    material = response.json()["material"]
    assert material["kind"] == "docx"
    assert response.json()["job_id"] is not None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = client.get(f"/api/v1/materials/{material['id']}").json()["material"]["status"]
        if state in ("ready", "failed"):
            break
        time.sleep(0.05)
