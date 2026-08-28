from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.domain.models import Blob, Course, Job, Material, Profile


def _make_session(client: TestClient, tmp_path: Path) -> tuple[Session, Engine]:
    from app.storage.db import make_engine, make_session_factory

    engine = make_engine(tmp_path / "app.db")
    return make_session_factory(engine)(), engine


def _insert_job(session: Session, **overrides: Any) -> Job:
    fields = {
        "type": "ingest",
        "payload": {"material_id": 999999},
        "status": "failed",
        "progress": 30,
        "stage": "ocr",
        "error": "boom",
    }
    fields.update(overrides)
    job = Job(**fields)
    session.add(job)
    session.commit()
    return job


def test_jobs_list_filters_and_labels(client: TestClient, tmp_path: Path) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    session, engine = _make_session(client, tmp_path)
    try:
        failed = _insert_job(session)
        _insert_job(
            session,
            type="postprocess",
            status="done",
            progress=100,
            stage="indexing",
            error=None,
            payload={"material_id": "abc"},
        )
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200
        all_jobs = response.json()
        assert {entry["id"] for entry in all_jobs} == {failed.id, failed.id + 1}
        done_entry = next(entry for entry in all_jobs if entry["status"] == "done")
        assert done_entry["type"] == "postprocess"
        assert done_entry["label"] == "postprocess"
        assert done_entry["material_id"] is None
        assert done_entry["retriable"] is False
        failed_entry = next(entry for entry in all_jobs if entry["status"] == "failed")
        assert failed_entry["retriable"] is True
        assert failed_entry["error"] == "boom"
        assert failed_entry["material_id"] == 999999

        by_status = client.get("/api/v1/jobs", params={"status": "failed"})
        assert [entry["id"] for entry in by_status.json()] == [failed.id]
        by_type = client.get("/api/v1/jobs", params={"type": "postprocess"})
        assert [entry["type"] for entry in by_type.json()] == ["postprocess"]
        bad = client.get("/api/v1/jobs", params={"status": "nope"})
        assert bad.status_code == 422
    finally:
        engine.dispose()


def test_summary_counts_failed_retryable(client: TestClient, tmp_path: Path) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    session, engine = _make_session(client, tmp_path)
    try:
        _insert_job(session)
        _insert_job(session, type="chat_turn", error="model offline")
        _insert_job(session, status="running", progress=10, stage="parse", error=None)
        summary = client.get("/api/v1/jobs/summary").json()
        assert summary["failed"] == 2
        assert summary["failed_retryable"] == 1
        assert summary["running"] == 1
        assert summary["queued"] == 0
    finally:
        engine.dispose()


def test_retry_single_job_and_guards(client: TestClient, tmp_path: Path) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    session, engine = _make_session(client, tmp_path)
    try:
        failed = _insert_job(session)
        chat = _insert_job(session, type="chat_turn")
        missing = client.post("/api/v1/jobs/424242/retry")
        assert missing.status_code == 404
        not_retryable = client.post(f"/api/v1/jobs/{chat.id}/retry")
        assert not_retryable.status_code == 422

        retried = client.post(f"/api/v1/jobs/{failed.id}/retry")
        assert retried.status_code == 200
        body = retried.json()
        assert body["status"] == "queued"
        assert body["error"] is None
        assert body["finished_at"] is None

        again = client.post(f"/api/v1/jobs/{failed.id}/retry")
        assert again.status_code == 422
    finally:
        engine.dispose()


def test_retry_bulk_only_eligible_types(client: TestClient, tmp_path: Path) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    session, engine = _make_session(client, tmp_path)
    try:
        ingest = _insert_job(session)
        chat = _insert_job(session, type="chat_turn")
        result = client.post("/api/v1/jobs/retry-failed", json={})
        assert result.status_code == 200
        assert result.json() == {"retried": 1}
        session.expire_all()
        states = {job.id: job.status for job in session.query(Job).all()}
        assert states[ingest.id] == "queued"
        assert states[chat.id] == "failed"

        filtered = client.post("/api/v1/jobs/retry-failed", json={"types": ["chat_turn"]})
        assert filtered.json() == {"retried": 0}
    finally:
        engine.dispose()


def test_job_types_lists_handlers(client: TestClient) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    response = client.get("/api/v1/jobs/types")
    assert response.status_code == 200
    types = {entry["type"] for entry in response.json()}
    assert "ingest" in types
    assert "postprocess" in types
    assert "chat_turn" not in types


def test_reingest_material_requeues(client: TestClient, tmp_path: Path) -> None:
    from app.storage.blobs import BlobStore

    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    session, engine = _make_session(client, tmp_path)
    try:
        blobs = BlobStore(tmp_path / "blobs")
        stored = blobs.put(b"pdf-bytes", session=session)
        if session.get(Profile, 1) is None:
            session.add(Profile(id=1, name="Default"))
        if session.get(Course, 1) is None:
            session.add(Course(id=1, profile_id=1, title="Calculus I"))
        if session.get(Blob, stored.sha256) is None:
            session.add(
                Blob(
                    sha256=stored.sha256,
                    rel_path=str(stored.rel_path),
                    size=stored.size,
                )
            )
        session.commit()
        sha = stored.sha256
        material = Material(
            profile_id=1,
            course_id=1,
            kind="pdf",
            title="Lecture",
            filename="Lecture.pdf",
            blob_sha=sha,
            status="failed",
        )
        session.add(material)
        session.commit()

        response = client.post(f"/api/v1/materials/{material.id}/reingest")
        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] is not None
        assert body["material"]["status"] == "failed"
        job = session.get(Job, body["job_id"])
        assert job is not None and job.type == "ingest"

        session.expire_all()
        fresh = session.get(Material, material.id)
        assert fresh is not None
        fresh.status = "ready"
        ok = client.post(f"/api/v1/materials/{material.id}/reingest")
        assert ok.status_code == 200

        missing = client.post("/api/v1/materials/424242/reingest")
        assert missing.status_code == 404
    finally:
        engine.dispose()


def _insert_material(
    session: Session, tmp_path: Path, title: str = "Lecture"
) -> Material:
    from app.storage.blobs import BlobStore

    blobs = BlobStore(tmp_path / "blobs")
    stored = blobs.put(b"pdf-bytes", session=session)
    if session.get(Profile, 1) is None:
        session.add(Profile(id=1, name="Default"))
    if session.get(Course, 1) is None:
        session.add(Course(id=1, profile_id=1, title="Calculus I"))
    if session.get(Blob, stored.sha256) is None:
        session.add(
            Blob(sha256=stored.sha256, rel_path=str(stored.rel_path), size=stored.size)
        )
    material = Material(
        profile_id=1,
        course_id=1,
        kind="pdf",
        title=title,
        filename=f"{title}.pdf",
        blob_sha=stored.sha256,
        status="ready",
    )
    session.add(material)
    session.commit()
    return material


def test_delete_single_job_and_guards(client: TestClient, tmp_path: Path) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    session, engine = _make_session(client, tmp_path)
    try:
        failed = _insert_job(session)
        done = _insert_job(
            session, status="done", progress=100, stage=None, error=None
        )
        queued = _insert_job(
            session, status="queued", progress=0, stage=None, error=None
        )
        running = _insert_job(
            session, status="running", progress=10, stage="ocr", error=None
        )
        failed_id, done_id, queued_id = failed.id, done.id, queued.id

        missing = client.delete("/api/v1/jobs/424242")
        assert missing.status_code == 404

        busy_queued = client.delete(f"/api/v1/jobs/{queued_id}")
        assert busy_queued.status_code == 422
        assert "queued" in busy_queued.json()["detail"]
        busy_running = client.delete(f"/api/v1/jobs/{running.id}")
        assert busy_running.status_code == 422
        assert "running" in busy_running.json()["detail"]

        deleted = client.delete(f"/api/v1/jobs/{failed_id}")
        assert deleted.status_code == 204
        remaining_ids = {job.id for job in session.query(Job).all()}
        assert failed_id not in remaining_ids

        deleted_done = client.delete(f"/api/v1/jobs/{done_id}")
        assert deleted_done.status_code == 204
        remaining_ids = {job.id for job in session.query(Job).all()}
        assert done_id not in remaining_ids

        survivor = client.delete(f"/api/v1/jobs/{queued_id}")
        assert survivor.status_code == 422
    finally:
        engine.dispose()


def test_delete_failed_bulk_includes_chat_turn_and_type_filter(
    client: TestClient, tmp_path: Path
) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    session, engine = _make_session(client, tmp_path)
    try:
        ingest = _insert_job(session)
        chat = _insert_job(session, type="chat_turn", error="chat session not found")
        postprocess = _insert_job(session, type="postprocess", error="no extraction")
        _insert_job(session, type="ingest", status="done", progress=100)
        ingest_id, chat_id, postprocess_id = ingest.id, chat.id, postprocess.id

        everything = client.request("DELETE", "/api/v1/jobs/failed", json={})
        assert everything.status_code == 200
        assert everything.json() == {"deleted": 3}
        remaining_ids = {job.id for job in session.query(Job).all()}
        assert len(remaining_ids) == 1
        assert ingest_id not in remaining_ids
        assert chat_id not in remaining_ids
        assert postprocess_id not in remaining_ids


        filtered_missing = client.request(
            "DELETE", "/api/v1/jobs/failed", json={"types": ["nope"]}
        )
        assert filtered_missing.json() == {"deleted": 0}

        _insert_job(session, type="postprocess", error="again")
        only_post = client.request(
            "DELETE", "/api/v1/jobs/failed", json={"types": ["postprocess"]}
        )
        assert only_post.json() == {"deleted": 1}
    finally:
        engine.dispose()


def test_stale_flag_marks_missing_material_and_session(
    client: TestClient, tmp_path: Path
) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    session, engine = _make_session(client, tmp_path)
    try:
        material = _insert_material(session, tmp_path)
        material_id = material.id
        alive = _insert_job(
            session, payload={"material_id": material_id}, error="material x not found"
        )
        gone = _insert_job(session, error="material 999999 not found")
        chat_gone = _insert_job(
            session,
            type="chat_turn",
            payload={"chat_session_id": 555},
            error="chat session not found",
        )
        alive_id, gone_id, chat_gone_id = alive.id, gone.id, chat_gone.id

        listed = {entry["id"]: entry for entry in client.get("/api/v1/jobs").json()}
        assert listed[alive_id]["stale"] is False
        assert listed[gone_id]["stale"] is True
        assert listed[chat_gone_id]["stale"] is True

        summary = client.get("/api/v1/jobs/summary").json()
        assert summary["failed"] == 3
        assert summary["failed_stale"] == 2

        session.query(Material).filter(Material.id == material_id).delete()
        session.commit()
        listed = {entry["id"]: entry for entry in client.get("/api/v1/jobs").json()}
        assert listed[alive_id]["stale"] is True
        summary = client.get("/api/v1/jobs/summary").json()
        assert summary["failed_stale"] == 3

        stale_only = client.request(
            "DELETE", "/api/v1/jobs/failed", json={"stale_only": True}
        )
        assert stale_only.json() == {"deleted": 3}
        remaining_ids = {job.id for job in session.query(Job).all()}
        assert remaining_ids == set()
    finally:
        engine.dispose()


def test_delete_failed_route_is_not_parsed_as_id(client: TestClient) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    response = client.request("DELETE", "/api/v1/jobs/failed", json={"types": []})
    assert response.status_code == 200
    assert response.json() == {"deleted": 0}
