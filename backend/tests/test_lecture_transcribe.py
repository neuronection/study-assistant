from types import SimpleNamespace
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.transcribe import TranscriptionResult, TranscriptionSegment
from app.domain.models import Extraction, MediaSegment
from app.jobs.payloads import LectureTranscribePayload
from app.pipelines.lecture_transcribe import make_lecture_transcribe_handler

WEBM_HEADER = b"\x1aE\xdf\xa3" + b"\x00" * 8
WEBM_SEGMENT = b"\x18S\x80g" + b"\x00" * 4
WEBM_CLUSTER = b"\x1fC\xb6u" + b"\x00" * 4


class FakeSpeechGateway:
    def transcribe(self, data: bytes, mime: str, **kwargs: Any) -> TranscriptionResult:
        return TranscriptionResult(
            text="Hello there. This is a lecture.",
            model="fake-stt",
            segments=[
                TranscriptionSegment(0, 1200, "Hello there."),
                TranscriptionSegment(1200, 3000, "This is a lecture."),
            ],
        )


def make_course(client: TestClient) -> str:
    return str(client.post("/api/v1/courses", json={"title": "Lectures"}).json()["id"])


def create_finalized_lecture(client: TestClient) -> tuple[str, str]:
    course_id = make_course(client)
    lecture = client.post(
        "/api/v1/lectures",
        json={"course_id": course_id, "title": "STT lecture", "consent_confirmed": True},
    ).json()
    data = WEBM_HEADER + WEBM_SEGMENT + WEBM_CLUSTER
    import hashlib

    response = client.put(
        f"/api/v1/lectures/{lecture['id']}/chunks/0",
        content=data,
        headers={
            "X-Chunk-Sha256": hashlib.sha256(data).hexdigest(),
            "Content-Type": "application/octet-stream",
        },
    )
    assert response.status_code == 200, response.text
    finalized = client.post(f"/api/v1/lectures/{lecture['id']}/finalize")
    assert finalized.status_code == 200, finalized.text
    return lecture["id"], str(finalized.json()["material_id"])


def test_transcription_persists_timestamped_segments_and_extraction(client: TestClient) -> None:
    with client:
        session_id, material_id = create_finalized_lecture(client)
        session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
        job = SimpleNamespace(
            id="lecture-job",
            payload=LectureTranscribePayload(session_id=session_id, material_id=material_id),
        )
        handler = make_lecture_transcribe_handler(
            FakeSpeechGateway(),
            client.app.state.blobs,  # type: ignore[attr-defined]
        )
        with session_factory() as session:
            handler(session, cast(Any, job), lambda *args, **kwargs: None)
            segments = list(
                session.scalars(
                    select(MediaSegment)
                    .where(MediaSegment.material_id == material_id)
                    .order_by(MediaSegment.start_ms)
                )
            )
            assert [segment.text for segment in segments] == [
                "Hello there.",
                "This is a lecture.",
            ]
            assert segments[0].start_ms == 0
            assert segments[1].start_ms == 1200
            extraction = session.scalars(
                select(Extraction)
                .where(Extraction.material_id == material_id)
                .order_by(Extraction.version.desc())
            ).first()
            assert extraction is not None
            assert extraction.extractor == "lecture_stt"
            assert "[0:00] Hello there." in extraction.markdown
