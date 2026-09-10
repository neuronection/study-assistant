import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from alembic import command
from app.core.events import EventBus
from app.domain.models import Course, Job, Material, Profile
from app.jobs.cancellation import (
    CANCELLED_ERROR,
    JobCancelled,
    cancel_jobs_for,
    clear_cancel,
    ensure_target_exists,
    is_cancel_requested,
)
from app.jobs.runner import JobRunner
from app.storage.db import make_engine, make_session_factory


def make_factory(tmp_path: Path, name: str) -> Any:
    db_path = tmp_path / name
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, "head")
    engine = make_engine(db_path)
    return make_session_factory(engine), engine


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met before timeout")


def make_course(client: TestClient) -> int:
    created = client.post("/api/v1/courses", json={"title": "Cancel tests"})
    assert created.status_code == 201
    return int(created.json()["id"])


def upload_md(client: TestClient, course_id: int) -> dict[str, Any]:
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("notes.md", b"# Cancel me\n\nbody text", "text/markdown")},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_purge_cancels_queued_ingest_job(client: TestClient) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    course_id = make_course(client)
    upload = upload_md(client, course_id)
    material_id = int(upload["material"]["id"])

    jobs = client.get("/api/v1/jobs", params={"status": "queued"}).json()
    assert any(
        entry["material_id"] == material_id and entry["type"] == "ingest"
        for entry in jobs
    )

    deleted = client.delete(f"/api/v1/materials/{material_id}")
    assert deleted.status_code == 204

    cancelled = client.get("/api/v1/jobs", params={"status": "cancelled"}).json()
    match = [entry for entry in cancelled if entry["material_id"] == material_id]
    assert match, "queued ingest job should be cancelled on purge"
    assert match[0]["status"] == "cancelled"
    assert match[0]["retriable"] is False
    assert "deleted" in (match[0]["error"] or "")


def test_cancelled_summary_and_retry_refusal(client: TestClient) -> None:
    client.app.state.jobs.stop()  # type: ignore[attr-defined]
    course_id = make_course(client)
    upload = upload_md(client, course_id)
    material_id = int(upload["material"]["id"])
    client.delete(f"/api/v1/materials/{material_id}")

    summary = client.get("/api/v1/jobs/summary").json()
    assert summary["cancelled"] >= 1
    cancelled_ids = [
        entry["id"]
        for entry in client.get("/api/v1/jobs", params={"status": "cancelled"}).json()
    ]
    assert cancelled_ids

    retry = client.post(f"/api/v1/jobs/{cancelled_ids[0]}/retry")
    assert retry.status_code == 422

    deleted = client.delete(f"/api/v1/jobs/{cancelled_ids[0]}")
    assert deleted.status_code == 204


def test_running_job_cancelled_at_report_checkpoint(tmp_path: Path) -> None:
    factory, engine = make_factory(tmp_path, "cancel.db")
    session = factory()
    job = Job(type="noop", payload={"material_id": 4242}, status="queued")
    session.add(job)
    session.commit()
    job_id = job.id

    entered = threading.Event()
    release = threading.Event()

    def handler(session: Session, job: Any, report: Any) -> None:
        entered.set()
        assert release.wait(5)
        report(50, "halfway")

    runner = JobRunner(
        factory,
        EventBus(),
        handlers={"noop": handler},
        poll_interval=0.02,
        workers=1,
    )
    runner.start()
    try:
        assert entered.wait(5), "handler never started"
        cancel_jobs_for(session, material_ids=[4242])
        assert is_cancel_requested(job_id), "running job should get a cancel flag"
        release.set()
        wait_until(lambda: job_status_is(factory, job_id, "cancelled"))
    finally:
        runner.stop()
        session.close()
        engine.dispose()
        clear_cancel(job_id)


def job_status_is(factory: Any, job_id: int, status: str) -> bool:
    with factory() as session:
        job = session.get(Job, job_id)
        return job is not None and job.status == status


def test_flag_set_before_start_never_runs_handler(tmp_path: Path) -> None:
    factory, engine = make_factory(tmp_path, "cancel2.db")
    session = factory()
    job = Job(type="noop", payload={"material_id": 7}, status="queued")
    session.add(job)
    session.commit()
    job_id = job.id

    ran = threading.Event()

    def handler(session: Session, job: Any, report: Any) -> None:
        ran.set()
        report(10, "started")

    cancel_jobs_for(session, material_ids=[7])
    runner = JobRunner(
        factory,
        EventBus(),
        handlers={"noop": handler},
        poll_interval=0.02,
        workers=1,
    )
    runner.start()
    try:
        time.sleep(0.3)
        assert not ran.is_set(), "handler must not run for a cancelled job"
        wait_until(lambda: job_status_is(factory, job_id, "cancelled"))
    finally:
        runner.stop()
        session.close()
        engine.dispose()
        clear_cancel(job_id)


def test_ensure_target_exists_raises_after_delete(db_session: Session) -> None:
    profile = Profile(name="cancels")
    db_session.add(profile)
    db_session.flush()
    course = Course(profile_id=profile.id, title="Cancel fixture")
    db_session.add(course)
    db_session.flush()
    material = Material(
        profile_id=profile.id,
        course_id=course.id,
        filename="gone.md",
        title="gone.md",
        kind="md",
        status="processing",
    )
    db_session.add(material)
    db_session.commit()
    material_id = material.id

    ensure_target_exists(db_session, Material, material_id, "material")

    db_session.delete(material)
    db_session.commit()
    with pytest.raises(JobCancelled, match="deleted while this job was running"):
        ensure_target_exists(db_session, Material, material_id, "material")


def test_cancel_matches_note_and_chat_payloads(db_session: Session) -> None:
    note_job = Job(
        type="drawing_ocr",
        payload={"kind": "note", "note_id": 31, "drawing_id": 5},
        status="queued",
    )
    chat_job = Job(
        type="chat_turn", payload={"chat_session_id": 88}, status="queued"
    )
    unrelated = Job(
        type="ingest", payload={"material_id": 31}, status="queued"
    )
    for entry in (note_job, chat_job, unrelated):
        db_session.add(entry)
    db_session.commit()

    assert cancel_jobs_for(db_session, note_ids=[31], chat_session_ids=[88]) == 2

    db_session.expire_all()
    refreshed = {
        job.id: job.status
        for job in db_session.scalars(
            select(Job).where(Job.id.in_([note_job.id, chat_job.id, unrelated.id]))
        )
    }
    assert refreshed[note_job.id] == "cancelled"
    assert refreshed[chat_job.id] == "cancelled"
    assert refreshed[unrelated.id] == "queued"


def test_cancelled_error_text_is_stable() -> None:
    assert "deleted" in CANCELLED_ERROR
