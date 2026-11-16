import hashlib
from datetime import timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.models import Extraction, LectureSession, Material, utcnow


def make_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Lecture course"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def create_lecture(client: TestClient, course_id: str, consent: bool = True) -> dict[str, Any]:
    response = client.post(
        "/api/v1/lectures",
        json={
            "course_id": course_id,
            "title": "Monday lecture",
            "consent_confirmed": consent,
            "retention": "audio_and_text",
            "mime": "audio/webm",
        },
    )
    return cast(dict[str, Any], response.json())


WEBM_HEADER = b"\x1aE\xdf\xa3" + b"\x00" * 8
WEBM_SEGMENT = b"\x18S\x80g" + b"\x00" * 4
WEBM_CLUSTER = b"\x1fC\xb6u" + b"\x00" * 4


def put_chunk(client: TestClient, session_id: str, seq: int, data: bytes) -> Any:
    digest = hashlib.sha256(data).hexdigest()
    return client.put(
        f"/api/v1/lectures/{session_id}/chunks/{seq}",
        content=data,
        headers={"X-Chunk-Sha256": digest, "Content-Type": "application/octet-stream"},
    )


def test_consent_is_required(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        response = client.post(
            "/api/v1/lectures",
            json={"course_id": course_id, "consent_confirmed": False},
        )
        assert response.status_code == 422
        assert "consent" in response.json()["detail"]


def test_chunks_are_idempotent_and_finalize_orders_them(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        lecture = create_lecture(client, course_id)
        assert lecture["status"] == "recording"
        session_id = lecture["id"]

        first = put_chunk(client, session_id, 0, WEBM_HEADER + WEBM_SEGMENT + WEBM_CLUSTER)
        assert first.status_code == 200, first.text
        replay = put_chunk(client, session_id, 0, WEBM_HEADER + WEBM_SEGMENT + WEBM_CLUSTER)
        assert replay.status_code == 200
        assert replay.json()["sha256"] == first.json()["sha256"]

        conflict = put_chunk(client, session_id, 0, b"different")
        assert conflict.status_code == 409

        assert put_chunk(client, session_id, 2, WEBM_CLUSTER).status_code == 200
        missing = client.get(f"/api/v1/lectures/{session_id}/chunks")
        assert missing.status_code == 200
        assert missing.json()["missing_sequences"] == [1]

        incomplete = client.post(f"/api/v1/lectures/{session_id}/finalize")
        assert incomplete.status_code == 409
        assert "missing" in incomplete.json()["detail"]

        assert put_chunk(client, session_id, 1, WEBM_CLUSTER + b"x").status_code == 200
        finalized = client.post(f"/api/v1/lectures/{session_id}/finalize")
        assert finalized.status_code == 200, finalized.text
        payload = finalized.json()
        assert payload["status"] == "transcribing"
        assert payload["material_id"]

        detail = client.get(f"/api/v1/lectures/{session_id}")
        assert detail.status_code == 200
        assert detail.json()["chunk_count"] == 3
        assert detail.json()["material_id"] == payload["material_id"]

        material = client.get(f"/api/v1/materials/{payload['material_id']}")
        assert material.status_code == 200
        assert material.json()["material"]["provenance"]["source"] == "lecture"


def test_pause_resume_and_cancel(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        lecture = create_lecture(client, course_id)
        paused = client.patch(
            f"/api/v1/lectures/{lecture['id']}",
            json={"status": "paused", "title": "Renamed lecture"},
        )
        assert paused.status_code == 200
        assert paused.json()["status"] == "paused"
        assert paused.json()["title"] == "Renamed lecture"

        resumed = client.patch(f"/api/v1/lectures/{lecture['id']}", json={"status": "recording"})
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "recording"

        assert client.delete(f"/api/v1/lectures/{lecture['id']}").status_code == 204
        assert client.get(f"/api/v1/lectures/{lecture['id']}").json()["status"] == "cancelled"


def test_bad_chunk_hash_is_rejected(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        lecture = create_lecture(client, course_id)
        response = client.put(
            f"/api/v1/lectures/{lecture['id']}/chunks/0",
            content=b"part",
            headers={"X-Chunk-Sha256": "bad", "Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 422


def test_invalid_container_is_refused_without_publishing(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        lecture = create_lecture(client, course_id)
        assert put_chunk(client, lecture["id"], 0, b"not-a-container").status_code == 200
        response = client.post(f"/api/v1/lectures/{lecture['id']}/finalize")
        assert response.status_code == 422
        assert "EBML" in response.json()["detail"]
        detail = client.get(f"/api/v1/lectures/{lecture['id']}").json()
        assert detail["status"] == "failed"
        assert detail["material_id"] is None


def test_text_only_audio_purge_is_ttl_and_transcript_gated(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        lecture = create_lecture(client, course_id)
        # Flip retention at the API edge, then upload a valid recording.
        patched = client.patch(f"/api/v1/lectures/{lecture['id']}", json={"retention": "text_only"})
        assert patched.status_code == 200
        assert (
            put_chunk(
                client, lecture["id"], 0, WEBM_HEADER + WEBM_SEGMENT + WEBM_CLUSTER
            ).status_code
            == 200
        )
        finalized = client.post(f"/api/v1/lectures/{lecture['id']}/finalize")
        assert finalized.status_code == 200, finalized.text
        material_id = finalized.json()["material_id"]

        settings = client.app.state.settings  # type: ignore[attr-defined]
        engine = create_engine(f"sqlite:///{settings.db_path}")
        with sessionmaker(bind=engine)() as session:
            row = session.get(LectureSession, lecture["id"])
            material = session.get(Material, material_id)
            assert row is not None and material is not None
            session.add(
                Extraction(
                    material_id=material_id,
                    version=1,
                    extractor="lecture_stt",
                    blocks=[{"type": "text", "md": "[0:00] Hello."}],
                    markdown="[0:00] Hello.",
                )
            )
            session.commit()

        early = client.post(f"/api/v1/lectures/{lecture['id']}/purge-audio")
        assert early.status_code == 409

        with sessionmaker(bind=engine)() as session:
            row = session.get(LectureSession, lecture["id"])
            assert row is not None
            row.ended_at = utcnow() - timedelta(days=8)
            session.commit()
        engine.dispose()

        purged = client.post(f"/api/v1/lectures/{lecture['id']}/purge-audio")
        assert purged.status_code == 200, purged.text
        assert purged.json()["audio_purged_at"] is not None
        material_response = client.get(f"/api/v1/materials/{material_id}")
        assert material_response.status_code == 200
        assert material_response.json()["material"]["blob_sha"] is None
        media_response = client.get(f"/api/v1/materials/{material_id}/media")
        assert media_response.status_code == 200
        assert media_response.json()["blob_sha"] is None
        assert material_response.json()["extraction"]["markdown"] == "[0:00] Hello."
