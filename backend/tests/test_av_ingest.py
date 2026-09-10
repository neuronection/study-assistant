import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, ProviderError, ResolvedModel
from app.ai.transcribe import TranscriptionResult
from app.core.config import Settings
from app.main import create_app
from app.services.content import materials as materials_service

TRANSCRIPT = "Good morning everyone. Today we cover the chain rule and its applications."


class AudioGateway(LLMGateway):
    def __init__(self, transcript: str | None = None, error: Exception | None = None) -> None:
        super().__init__(session_factory=None)
        self.transcript = transcript
        self.error = error
        self.calls: list[tuple[bytes, str]] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="whisper-small",
            label="whisper-small",
            caps=["audio"],
            api_key=None,
        )

    def transcribe(
        self,
        data: bytes,
        mime: str,
        *,
        language: str | None = None,
        instruction: str | None = None,
        task: str = "transcribe",
        model: Any = None,
        course_id: int | None = None,
    ) -> TranscriptionResult:
        del language, instruction, task, model, course_id
        if self.error is not None:
            raise self.error
        self.calls.append((data, mime))
        assert self.transcript is not None
        return TranscriptionResult(text=self.transcript, model="whisper-small")


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


@pytest.fixture
def av_client(tmp_path: Path) -> Iterator[tuple[TestClient, AudioGateway]]:
    gateway = AudioGateway()
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Lectures"}).json()["id"])


def upload(client: TestClient, course_id: int, filename: str, data: bytes) -> dict[str, Any]:
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, data)},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def wait_terminal(client: TestClient, material_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        status = detail["material"]["status"]
        if status in ("ready", "failed"):
            reached: dict[str, Any] = detail
            return reached
        time.sleep(0.05)
    raise AssertionError("material never reached a terminal status")


def test_audio_lecture_becomes_searchable_transcript(
    av_client: tuple[TestClient, AudioGateway],
) -> None:
    client, gateway = av_client
    gateway.transcript = TRANSCRIPT
    course_id = make_course(client)
    result = upload(client, course_id, "lecture.mp3", b"fake-mp3-bytes")
    material_id = result["material"]["id"]
    assert result["warnings"] == []

    detail = wait_terminal(client, material_id)
    assert detail["material"]["status"] == "ready"
    markdown = detail["extraction"]["markdown"]
    assert "chain rule and its applications" in markdown
    assert "whisper-small" in markdown
    assert detail["material"]["provenance"]["source"] == "transcribed"
    assert detail["material"]["provenance"]["model"] == "whisper-small"
    assert gateway.calls, "gateway.transcribe was never called"

    search = client.get("/api/v1/search", params={"course_id": course_id, "q": "chain rule"})
    assert any(hit["material_id"] == material_id for hit in search.json()["hits"])


def test_reingest_retranscribes_to_new_version(
    av_client: tuple[TestClient, AudioGateway],
) -> None:
    client, gateway = av_client
    gateway.transcript = TRANSCRIPT
    course_id = make_course(client)
    material_id = upload(client, course_id, "lecture.m4a", b"fake-audio")["material"]["id"]
    wait_terminal(client, material_id)

    gateway.transcript = "Second take: the chain rule, revisited with better audio."
    reingest = client.post(f"/api/v1/materials/{material_id}/reingest")
    assert reingest.status_code == 200, reingest.text

    deadline = time.monotonic() + 10
    versions: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        listing = client.get(f"/api/v1/materials/{material_id}/extractions").json()
        versions = list(listing)
        latest = client.get(f"/api/v1/materials/{material_id}").json()
        if latest["material"]["status"] == "ready" and len(versions) >= 2:
            break
        time.sleep(0.05)
    assert len(versions) >= 2
    latest_version = client.get(
        f"/api/v1/materials/{material_id}/extractions/{max(int(v['version']) for v in versions)}"
    ).json()
    assert "Second take" in latest_version["markdown"]


def test_video_provider_rejection_fails_job_with_reason(
    av_client: tuple[TestClient, AudioGateway],
) -> None:
    client, gateway = av_client
    resolved = gateway.resolve("transcribe")
    gateway.error = ProviderError(resolved, "video files are not supported by this provider")
    course_id = make_course(client)
    material_id = upload(client, course_id, "lecture.mp4", b"fake-video")["material"]["id"]

    detail = wait_terminal(client, material_id)
    assert detail["material"]["status"] == "failed"

    jobs = client.get("/api/v1/jobs", params={"status": "failed"}).json()
    assert any(
        job["type"] == "ingest" and "not supported by this provider" in (job.get("error") or "")
        for job in jobs
    )


def test_transcribe_size_warning_surfaces_before_ingest(
    av_client: tuple[TestClient, AudioGateway], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _gateway = av_client
    monkeypatch.setattr(materials_service, "TRANSCRIBE_SIZE_LIMIT_BYTES", 8)
    course_id = make_course(client)
    result = upload(client, course_id, "big-lecture.mp3", b"1234567890")
    assert result["material"]["kind"] == "audio"
    assert result["warnings"] == [
        {"code": "transcribe_size_exceeded", "limit_mb": 25, "file_mb": 0.0}
    ]


def test_zero_byte_av_upload_is_refused(av_client: tuple[TestClient, AudioGateway]) -> None:
    client, _gateway = av_client
    course_id = make_course(client)
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("empty.mp3", b"")},
    )
    assert response.status_code == 422
