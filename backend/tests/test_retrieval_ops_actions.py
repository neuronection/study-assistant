"""Plan 51 Q3b: the retrieval action seam, idempotency, lock, reaper and audit."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.vocab import JobType
from app.domain.models import AuditEvent, Chunk, Course, Extraction, Job, Material
from app.jobs.cancellation import clear_cancel, is_cancel_requested
from app.pipelines.retrieval_ops import make_vector_maintenance_handler
from app.services.retrieval.jobs import STALE_ERROR
from app.services.retrieval.legacy import LEGACY_SPACE_ID
from app.storage.retrieval_ops import assert_no_raw_text, run_lock_key

BASE = "/api/v1/admin/retrieval"
LOCK = run_lock_key(LEGACY_SPACE_ID)


class FakeEmbedder:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return ("fake-embed", [[1.0, 0.0, 0.0, float(index)] for index, _ in enumerate(texts)])


def _stop_worker(client: TestClient) -> None:
    cast(Any, client.app).state.jobs.stop()


def _key(name: str) -> dict[str, str]:
    return {"Idempotency-Key": name}


def _seed_chunk(session: Session, profile_id: str, text: str = "alpha") -> str:
    course = Course(profile_id=profile_id, title="Retrieval actions")
    session.add(course)
    session.flush()
    material = Material(
        profile_id=profile_id,
        course_id=course.id,
        kind="md",
        title="Notes",
        filename="notes.md",
        status="ready",
    )
    session.add(material)
    session.flush()
    extraction = Extraction(
        material_id=material.id,
        extractor="test",
        blocks=[{"type": "text", "md": text}],
        markdown=text,
    )
    session.add(extraction)
    session.flush()
    chunk = Chunk(extraction_id=extraction.id, ordinal=0, text=text)
    session.add(chunk)
    session.commit()
    return chunk.id


def _job(session: Session, job_type: str, payload: dict[str, Any], **values: Any) -> Job:
    job = Job(type=job_type, payload=payload, status=values.pop("status", "queued"), **values)
    session.add(job)
    session.commit()
    return job


def _audit_actions(session: Session) -> list[str]:
    session.expire_all()
    return list(session.scalars(select(AuditEvent.action).order_by(AuditEvent.created_at)))


def test_reindex_enqueue_replay_and_mismatch(
    client: TestClient, db_session: Session, profile_id: str
) -> None:
    _stop_worker(client)
    chunk_id = _seed_chunk(db_session, profile_id, "TOP-SECRET-CHUNK-TEXT")

    first = client.post(f"{BASE}/reindex", json={}, headers=_key("reindex-key-0001"))
    assert first.status_code == 202, first.text
    body = first.json()
    assert body["action"] == "reindex"
    assert body["status"] == "queued"
    assert body["deduplicated"] is False
    assert body["idempotency_key"] == "reindex-key-0001"

    db_session.expire_all()
    job = db_session.get(Job, body["run_id"])
    assert job is not None
    assert job.type == JobType.VECTOR_REINDEX.value
    assert job.status == "queued"
    assert job.lock_key == LOCK
    assert cast(dict[str, Any], job.payload)["space_id"] == LEGACY_SPACE_ID
    assert job.heartbeat_at is None

    replay = client.post(f"{BASE}/reindex", json={}, headers=_key("reindex-key-0001"))
    assert replay.status_code == 200, replay.text
    assert replay.json()["run_id"] == body["run_id"]
    assert replay.json()["deduplicated"] is True
    assert len(db_session.scalars(select(Job)).all()) == 1

    mismatch = client.post(
        f"{BASE}/reindex", json={"force": True}, headers=_key("reindex-key-0001")
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["reason"] == "idempotency_mismatch"

    locked = client.post(f"{BASE}/reindex", json={}, headers=_key("reindex-key-0002"))
    assert locked.status_code == 409
    assert locked.json()["detail"]["reason"] == "run_in_progress"
    assert locked.json()["detail"]["active_run_id"] == body["run_id"]

    missing = client.post(f"{BASE}/reindex", json={})
    assert missing.status_code == 422
    assert missing.json()["detail"]["reason"] == "idempotency_key_required"

    assert _audit_actions(db_session) == ["vector.reindex.started"]
    assert "TOP-SECRET-CHUNK-TEXT" not in json.dumps(first.json())
    assert chunk_id  # identity stayed stable


def test_stale_running_row_is_reaped_and_releases_the_lock(
    client: TestClient, db_session: Session
) -> None:
    _stop_worker(client)
    stale_at = datetime.now(UTC) - timedelta(minutes=30)
    stale = _job(
        db_session,
        JobType.VECTOR_REINDEX.value,
        {"space_id": LEGACY_SPACE_ID},
        status="running",
        started_at=stale_at,
        heartbeat_at=stale_at,
        lock_key=LOCK,
        idempotency_key="stale-key-0001",
    )

    accepted = client.post(f"{BASE}/reindex", json={}, headers=_key("reindex-key-0003"))
    assert accepted.status_code == 202, accepted.text

    db_session.expire_all()
    reaped = db_session.get(Job, stale.id)
    assert reaped is not None
    assert reaped.status == "failed"
    assert reaped.error == STALE_ERROR
    assert reaped.lock_key is None
    assert "vector.run.stalled" in _audit_actions(db_session)


def test_cancel_queued_and_running(
    client: TestClient, db_session: Session
) -> None:
    _stop_worker(client)
    queued = _job(
        db_session,
        JobType.VECTOR_REINDEX.value,
        {"space_id": LEGACY_SPACE_ID},
        idempotency_key="cancel-key-0001",
        lock_key=LOCK,
    )
    response = client.post(f"{BASE}/runs/{queued.id}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    db_session.expire_all()
    queued_after = db_session.get(Job, queued.id)
    assert queued_after is not None
    assert queued_after.status == "cancelled"

    again = client.post(f"{BASE}/runs/{queued.id}/cancel")
    assert again.status_code == 409
    assert again.json()["detail"]["reason"] == "run_not_active"

    running = _job(
        db_session,
        JobType.VECTOR_MAINTENANCE.value,
        {"action": "vacuum", "space_id": LEGACY_SPACE_ID},
        status="running",
        started_at=datetime.now(UTC),
        heartbeat_at=datetime.now(UTC),
        idempotency_key="cancel-key-0002",
        lock_key=LOCK,
    )
    try:
        requested = client.post(f"{BASE}/runs/{running.id}/cancel")
        assert requested.status_code == 200, requested.text
        assert requested.json()["status"] == "running"
        assert requested.json()["cancel_requested"] is True
        db_session.expire_all()
        running_after = db_session.get(Job, running.id)
        assert running_after is not None
        assert running_after.cancel_requested is True
        assert is_cancel_requested(running.id) is True
    finally:
        clear_cancel(running.id)

    assert _audit_actions(db_session).count("vector.reindex.cancelled") == 2


def test_retry_failed_run_enqueues_a_fresh_row(
    client: TestClient, db_session: Session
) -> None:
    _stop_worker(client)
    failed = _job(
        db_session,
        JobType.VECTOR_REINDEX.value,
        {"space_id": LEGACY_SPACE_ID, "limit": 10},
        status="failed",
        error="provider exploded",
        finished_at=datetime.now(UTC),
    )
    response = client.post(
        f"{BASE}/runs/{failed.id}/retry", headers=_key("retry-key-0001")
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["action"] == "retry_run"
    assert body["retry_of"] == failed.id
    assert body["run_id"] != failed.id
    db_session.expire_all()
    retried = db_session.get(Job, body["run_id"])
    assert retried is not None
    assert retried.status == "queued"
    assert cast(dict[str, Any], retried.payload)["requeue_of"] == failed.id
    assert retried.lock_key == LOCK

    replay = client.post(
        f"{BASE}/runs/{failed.id}/retry", headers=_key("retry-key-0001")
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["run_id"] == body["run_id"]
    assert replay.json()["deduplicated"] is True

    done = _job(
        db_session,
        JobType.VECTOR_REINDEX.value,
        {"space_id": LEGACY_SPACE_ID},
        status="done",
        finished_at=datetime.now(UTC),
    )
    refused = client.post(f"{BASE}/runs/{done.id}/retry", headers=_key("retry-key-0002"))
    assert refused.status_code == 409
    assert refused.json()["detail"]["reason"] == "run_not_retriable"


def test_maintenance_actions_and_dry_run(
    client: TestClient, db_session: Session, profile_id: str
) -> None:
    _stop_worker(client)
    _seed_chunk(db_session, profile_id, "alpha")

    dry = client.post(
        f"{BASE}/maintenance",
        json={"action": "orphan-sweep", "dry_run": True},
        headers=_key("maint-key-0001"),
    )
    assert dry.status_code == 202, dry.text
    db_session.expire_all()
    job = db_session.get(Job, dry.json()["run_id"])
    assert job is not None
    make_vector_maintenance_handler(FakeEmbedder().embed)(db_session, job, lambda *_: None)
    result = cast(dict[str, Any], job.result)
    assert result["dry_run"] is True
    assert result["removed"] == 0
    assert "would_remove" in result

    unknown = client.post(
        f"{BASE}/maintenance",
        json={"action": "retry-failed"},
        headers=_key("maint-key-0002"),
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["reason"] == "invalid_request"

    unsupported_dry = client.post(
        f"{BASE}/maintenance",
        json={"action": "vacuum", "dry_run": True},
        headers=_key("maint-key-0003"),
    )
    assert unsupported_dry.status_code == 422
    assert unsupported_dry.json()["detail"]["reason"] == "unsupported_dry_run"

    retry_failed = client.post(
        f"{BASE}/maintenance",
        json={"action": "retry-failed", "chunk_ids": ["missing-chunk"]},
        headers=_key("maint-key-0004"),
    )
    assert retry_failed.status_code == 409  # the previous maintenance run still holds the lock
    assert retry_failed.json()["detail"]["reason"] == "run_in_progress"

    db_session.expire_all()
    job = db_session.get(Job, dry.json()["run_id"])
    assert job is not None
    job.status = "done"
    job.lock_key = None
    db_session.commit()

    retry_again = client.post(
        f"{BASE}/maintenance",
        json={"action": "retry-failed", "chunk_ids": ["missing-chunk"]},
        headers=_key("maint-key-0005"),
    )
    assert retry_again.status_code == 202, retry_again.text
    db_session.expire_all()
    retry_job = db_session.get(Job, retry_again.json()["run_id"])
    assert retry_job is not None
    assert cast(dict[str, Any], retry_job.payload)["chunk_ids"] == ["missing-chunk"]


def test_quality_compare_requires_a_body_key_and_real_spaces(
    client: TestClient,
) -> None:
    _stop_worker(client)
    missing_body = client.post(f"{BASE}/quality/compare")
    assert missing_body.status_code == 422
    missing_key = client.post(
        f"{BASE}/quality/compare",
        json={"space_id": "a", "compare_space_id": "b"},
    )
    assert missing_key.status_code == 422
    assert missing_key.json()["detail"]["reason"] == "idempotency_key_required"
    unknown = client.post(
        f"{BASE}/quality/compare",
        json={"space_id": "no-such-space", "compare_space_id": "other"},
        headers=_key("quality-key-0001"),
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["reason"] == "space_not_found"


def test_lifecycle_verbs_require_a_space_and_key(
    client: TestClient,
) -> None:
    _stop_worker(client)
    missing_body = client.post(f"{BASE}/cutover")
    assert missing_body.status_code == 422
    unknown = client.post(
        f"{BASE}/spaces/no-such-space/activate",
        headers=_key("activate-key-missing"),
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["reason"] == "space_not_found"
    missing_key = client.post(f"{BASE}/spaces", json={})
    assert missing_key.status_code == 422
    assert missing_key.json()["detail"]["reason"] == "idempotency_key_required"


def test_actions_require_admin(raw_client: TestClient) -> None:
    response = raw_client.post(
        f"{BASE}/reindex", json={}, headers=_key("admin-key-0001")
    )
    assert response.status_code in (401, 403)


def test_runs_and_audit_carry_no_raw_text(
    client: TestClient, db_session: Session, profile_id: str
) -> None:
    _stop_worker(client)
    _seed_chunk(db_session, profile_id, "NEEDLE-DOCUMENT-TEXT")
    accepted = client.post(f"{BASE}/reindex", json={}, headers=_key("text-key-0001"))
    assert accepted.status_code == 202, accepted.text

    runs = client.get(f"{BASE}/runs")
    assert runs.status_code == 200
    assert_no_raw_text(runs.json())
    assert "NEEDLE-DOCUMENT-TEXT" not in json.dumps(runs.json())

    db_session.expire_all()
    rows = db_session.scalars(select(AuditEvent)).all()
    assert rows
    payload = json.dumps(
        [
            {
                "actor": row.actor,
                "action": row.action,
                "resource": row.resource,
                "outcome": row.outcome,
            }
            for row in rows
        ]
    )
    assert "NEEDLE-DOCUMENT-TEXT" not in payload
