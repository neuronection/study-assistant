from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.models import Extraction, Material


def make_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Lectures"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def make_audio(client: TestClient, course_id: str) -> str:
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("lecture.mp3", b"ID3fake-audio", "audio/mpeg")},
    )
    assert response.status_code == 200, response.text
    material_id = str(response.json()["material"]["id"])
    settings = client.app.state.settings  # type: ignore[attr-defined]
    engine = create_engine(f"sqlite:///{settings.db_path}")
    with sessionmaker(bind=engine)() as session:
        material = session.get(Material, material_id)
        assert material is not None
        material.duration_sec = 12.5
        material.mime = "audio/mpeg"
        session.add(
            Extraction(
                material_id=material_id,
                version=1,
                extractor="text",
                blocks=[{"type": "text", "md": "A short lecture transcript."}],
                markdown="A short lecture transcript.",
            )
        )
        session.commit()
    engine.dispose()
    return material_id


def test_media_returns_a_seeded_segment_and_seeks_by_timestamp(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        material_id = make_audio(client, course_id)

        media = client.get(f"/api/v1/materials/{material_id}/media")
        assert media.status_code == 200, media.text
        payload = cast(dict[str, Any], media.json())
        assert payload["material_id"] == material_id
        assert payload["course_id"] == course_id
        assert payload["duration_ms"] == 12500
        assert len(payload["segments"]) == 1
        segment = payload["segments"][0]
        assert segment["start_ms"] == 0
        assert segment["end_ms"] == 12500
        assert "lecture transcript" in segment["text"]

        updated = client.patch(
            f"/api/v1/media/segments/{segment['id']}",
            json={"text": "Corrected name: Dr Chen.", "speaker": "Dr Chen"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["text"] == "Corrected name: Dr Chen."
        assert updated.json()["speaker"] == "Dr Chen"

        engine = create_engine(f"sqlite:///{client.app.state.settings.db_path}")  # type: ignore[attr-defined]
        with sessionmaker(bind=engine)() as session:
            latest = session.scalars(
                select(Extraction)
                .where(Extraction.material_id == material_id)
                .order_by(Extraction.version.desc())
            ).first()
            assert latest is not None
            assert latest.version >= 2
            assert "[0:00] Corrected name: Dr Chen." in latest.markdown
        engine.dispose()

        created = client.post(
            f"/api/v1/materials/{material_id}/media/segments",
            json={"start_ms": 13000, "end_ms": 15000, "text": "A second point.", "order_idx": 1},
        )
        assert created.status_code == 201, created.text
        assert created.json()["source"] == "manual"

        missing = client.get(f"/api/v1/materials/{material_id}/media")
        assert missing.status_code == 200
        assert len(missing.json()["segments"]) == 2

        assert client.delete(f"/api/v1/media/segments/{created.json()['id']}").status_code == 204


def test_split_and_merge_transcript_segments(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        material_id = make_audio(client, course_id)
        media = client.get(f"/api/v1/materials/{material_id}/media").json()
        original = media["segments"][0]

        split = client.post(
            f"/api/v1/media/segments/{original['id']}/split",
            json={"at_ms": 6000},
        )
        assert split.status_code == 201, split.text
        second = split.json()
        assert second["start_ms"] == 6000
        assert second["end_ms"] == 12500
        assert second["text"]
        after_split = client.get(f"/api/v1/materials/{material_id}/media").json()
        assert len(after_split["segments"]) == 2
        assert after_split["segments"][0]["end_ms"] == 6000

        merged = client.post(
            "/api/v1/media/segments/merge",
            json={"first_id": original["id"], "second_id": second["id"]},
        )
        assert merged.status_code == 200, merged.text
        assert merged.json()["start_ms"] == 0
        assert merged.json()["end_ms"] == 12500
        after_merge = client.get(f"/api/v1/materials/{material_id}/media").json()
        assert len(after_merge["segments"]) == 1


def test_media_rejects_a_non_media_material(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        material = client.post(
            "/api/v1/materials/text",
            json={"course_id": course_id, "filename": "notes.md", "content": "# Notes"},
        )
        assert material.status_code == 200, material.text
        material_id = material.json()["material"]["id"]
        response = client.get(f"/api/v1/materials/{material_id}/media")
        assert response.status_code == 422
