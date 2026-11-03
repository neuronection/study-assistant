"""Plan 51 Q3a: job slot, bounded handlers, telemetry and the read surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.vocab import JobType
from app.domain.models import (
    Chunk,
    Course,
    Extraction,
    Job,
    Material,
    RetrievalCoverageSnapshot,
    RetrievalQueryRollup,
)
from app.jobs.cancellation import JobCancelled
from app.jobs.runner import JobError
from app.pipelines.retrieval_ops import (
    make_vector_cutover_handler,
    make_vector_maintenance_handler,
    make_vector_reindex_handler,
)
from app.services.retrieval import reads
from app.services.retrieval.legacy import LEGACY_KIND, LEGACY_SPACE_ID, load_store
from app.services.retrieval.telemetry import (
    QueryRollupRecorder,
    aggregate_rows,
    configure_recorder,
    histogram_percentile,
)
from app.services.search import hybrid_search, retrieve_chunks_hybrid
from app.storage import vectors
from app.storage.db import make_engine, make_session_factory
from app.storage.retrieval_ops import (
    DegradedReason,
    GateStatus,
    RunResultDTO,
    assert_no_raw_text,
)

DIM = 4


@dataclass
class FakeEmbedder:
    fail_on: str | None = None
    calls: int = 0

    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        self.calls += 1
        if self.fail_on is not None and any(self.fail_on in text for text in texts):
            raise RuntimeError("provider exploded")
        return ("fake-embed", [[1.0, 0.0, 0.0, float(index)] for index, _ in enumerate(texts)])


class NoEmbedder:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None


def _migrated_factory(tmp_path: Path, name: str = "retrieval.db") -> sessionmaker[Session]:
    db_path = tmp_path / name
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, "head")
    engine = make_engine(db_path)
    return make_session_factory(engine)


def seed_chunks(session: Session, profile_id: str, texts: list[str]) -> list[str]:
    course = Course(profile_id=profile_id, title="Retrieval test")
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
        blocks=[{"type": "text", "md": "\n\n".join(texts)}],
        markdown="\n\n".join(texts),
    )
    session.add(extraction)
    session.flush()
    chunks = [
        Chunk(extraction_id=extraction.id, ordinal=index, text=text)
        for index, text in enumerate(texts)
    ]
    session.add_all(chunks)
    session.commit()
    return [chunk.id for chunk in chunks]


def make_job(session: Session, job_type: JobType, payload: dict[str, Any]) -> Job:
    job = Job(type=job_type.value, payload=payload, status="running", progress=0)
    session.add(job)
    session.commit()
    return job


def no_report(_progress: int, _stage: str) -> None:
    return None


def result_of(job: Job) -> RunResultDTO:
    assert job.result is not None
    return RunResultDTO(**cast(dict[str, Any], job.result))


def test_job_vocabulary_carries_the_exact_contract_names() -> None:
    assert JobType.VECTOR_REINDEX.value == "VECTOR_REINDEX"
    assert JobType.VECTOR_MAINTENANCE.value == "VECTOR_MAINTENANCE"
    assert JobType.VECTOR_CUTOVER.value == "VECTOR_CUTOVER"


def test_reindex_embeds_then_verifies_and_publishes_one_snapshot(
    db_session: Session, profile_id: str
) -> None:
    chunk_ids = seed_chunks(db_session, profile_id, ["alpha", "beta"])
    embedder = FakeEmbedder()
    handler = make_vector_reindex_handler(embedder.embed)

    first = make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10, "batch_size": 2})
    handler(db_session, first, no_report)
    first_result = result_of(first)
    assert (first_result.scanned, first_result.embedded, first_result.skipped) == (2, 2, 0)
    assert first_result.failed == 0
    assert first_result.gate == GateStatus.PASS
    assert vectors.vector_count(db_session) == 2

    snapshots = db_session.scalars(
        select(RetrievalCoverageSnapshot).where(
            RetrievalCoverageSnapshot.space_id == LEGACY_SPACE_ID
        )
    ).all()
    assert len(snapshots) == 1
    assert snapshots[0].total == 2
    assert snapshots[0].embedded == 2
    assert snapshots[0].kind == LEGACY_KIND

    second = make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10, "batch_size": 2})
    handler(db_session, second, no_report)
    second_result = result_of(second)
    assert (second_result.scanned, second_result.embedded, second_result.skipped) == (2, 0, 2)
    assert embedder.calls == 1  # verified existing vectors cost no provider call

    assert set(chunk_ids)  # the seeded identities stayed stable


def test_reindex_bounds_failed_ids_and_keeps_partial_coverage(
    db_session: Session, profile_id: str
) -> None:
    seed_chunks(db_session, profile_id, ["good", "bad", "also-bad"])
    handler = make_vector_reindex_handler(FakeEmbedder(fail_on="bad").embed)
    job = make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10, "batch_size": 1})
    handler(db_session, job, no_report)
    result = result_of(job)
    assert result.scanned == 3
    assert result.embedded == 1
    assert result.failed == 2
    assert len(result.failed_ids) == 2
    assert result.failed_ids_truncated is False
    assert result.gate == GateStatus.FAIL
    snapshot = db_session.scalars(select(RetrievalCoverageSnapshot)).one()
    assert snapshot.total == 3
    assert snapshot.embedded == 1
    assert snapshot.missing == 2


def test_unassigned_embeddings_is_reported_not_invented(
    db_session: Session, profile_id: str
) -> None:
    seed_chunks(db_session, profile_id, ["alpha"])
    job = make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10})
    make_vector_reindex_handler(NoEmbedder().embed)(db_session, job, no_report)
    result = result_of(job)
    assert result.embedded == 0
    assert result.failed == 1
    assert result.gate == GateStatus.FAIL


def test_reindex_honours_cancel_without_publishing_coverage(
    db_session: Session, profile_id: str
) -> None:
    seed_chunks(db_session, profile_id, ["alpha", "beta"])
    job = make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10, "batch_size": 1})

    def cancel_report(_progress: int, _stage: str) -> None:
        raise JobCancelled("cancelled by test")

    with pytest.raises(JobCancelled):
        make_vector_reindex_handler(FakeEmbedder().embed)(db_session, job, cancel_report)
    assert job.result is None
    assert db_session.scalars(select(RetrievalCoverageSnapshot)).all() == []


def test_maintenance_orphan_sweep_removes_dead_rows(
    db_session: Session, profile_id: str
) -> None:
    chunk_ids = seed_chunks(db_session, profile_id, ["alpha"])
    vectors.store(db_session, chunk_ids, [[1.0, 0.0, 0.0, 0.0]], "fake-embed")
    db_session.commit()
    db_session.delete(db_session.get(Chunk, chunk_ids[0]))
    db_session.commit()

    job = make_job(db_session, JobType.VECTOR_MAINTENANCE, {"action": "orphan-sweep"})
    make_vector_maintenance_handler(FakeEmbedder().embed)(db_session, job, no_report)
    payload = cast(dict[str, Any], job.result)
    assert payload["action"] == "orphan-sweep"
    assert payload["removed"] == 1
    assert vectors.vector_count(db_session) == 0


def test_maintenance_rejects_unknown_action(db_session: Session) -> None:
    job = make_job(db_session, JobType.VECTOR_MAINTENANCE, {"action": "drop-everything"})
    with pytest.raises(JobError):
        make_vector_maintenance_handler(FakeEmbedder().embed)(db_session, job, no_report)


def test_cutover_refuses_honestly(db_session: Session) -> None:
    job = make_job(db_session, JobType.VECTOR_CUTOVER, {})
    with pytest.raises(JobError, match="no vector-space lifecycle"):
        make_vector_cutover_handler()(db_session, job, no_report)


def test_telemetry_batches_without_query_text(db_session: Session) -> None:
    factory = make_session_factory(cast(Engine, db_session.get_bind()))
    recorder = QueryRollupRecorder(factory, max_pending=64)
    recorder.record(latency_ms=12, candidates=10, zero_results=False)
    recorder.record(
        latency_ms=120,
        candidates=0,
        zero_results=True,
        degraded_reason=DegradedReason.PROVIDER_UNASSIGNED.value,
    )
    recorder.record(latency_ms=9_000, candidates=4, zero_results=False)
    assert recorder.flush(db_session) == 3

    rows = db_session.scalars(select(RetrievalQueryRollup)).all()
    assert sum(row.count for row in rows) == 3
    assert sum(row.zero_results for row in rows) == 1
    metrics = aggregate_rows(rows)
    assert metrics["query_count"] == 3
    assert metrics["zero_result_rate"] == pytest.approx(1 / 3)
    assert metrics["degraded_rate"] == pytest.approx(1 / 3)
    assert metrics["degraded_reasons"] == {"provider_unassigned": 1}
    assert metrics["p50_ms"] is not None
    assert metrics["p95_ms"] == 10_000
    assert histogram_percentile(metrics["histogram"], 0.95) == 10_000

    columns = set(RetrievalQueryRollup.__table__.columns.keys())
    assert not columns & {"query", "query_text", "text", "prompt", "document"}
    payload = json.dumps(
        [
            {
                "latency": row.latency_histogram,
                "kind": row.kind,
                "reason": row.degraded_reason,
            }
            for row in rows
        ]
    )
    assert "alpha" not in payload


def test_telemetry_buffer_is_bounded(db_session: Session) -> None:
    factory = make_session_factory(cast(Engine, db_session.get_bind()))
    recorder = QueryRollupRecorder(factory, max_pending=2)
    for _ in range(5):
        recorder.record(latency_ms=10, candidates=1, zero_results=False)
    assert recorder.pending_count == 2
    assert recorder.dropped == 3
    recorder.flush(db_session)
    assert recorder.pending_count == 0


def test_search_hot_path_emits_off_path_samples(db_session: Session) -> None:
    factory = make_session_factory(cast(Engine, db_session.get_bind()))
    recorder = QueryRollupRecorder(factory, max_pending=16)
    configure_recorder(recorder)
    try:
        retrieve_chunks_hybrid(
            db_session,
            "alpha",
            lambda _query: None,
            limit=5,
            use_embeddings=True,
        )
        hybrid_search(db_session, "alpha", 5, lambda _query: None)
    finally:
        configure_recorder(None)
    assert recorder.pending_count == 2
    assert recorder.flush(db_session) == 2
    rows = db_session.scalars(select(RetrievalQueryRollup)).all()
    reasons = {row.degraded_reason for row in rows}
    assert "provider_unassigned" in reasons
    assert {row.kind for row in rows} == {"chunk", "material"}


def test_read_surface_cold_and_ready(
    client: TestClient, db_session: Session, profile_id: str
) -> None:
    empty = client.get("/api/v1/admin/retrieval/overview")
    assert empty.status_code == 200
    body = empty.json()
    assert body["state"] == "empty"
    assert body["cold"] is True
    assert body["space"] is None
    assert body["coverage"]["as_of"] is None
    assert client.get("/api/v1/admin/retrieval/spaces").json()["spaces"] == []
    cold_coverage = client.get("/api/v1/admin/retrieval/coverage").json()
    assert cold_coverage["cold"] is True
    assert cold_coverage["coverage"]["coverage"] is None
    assert_no_raw_text(body)

    seed_chunks(db_session, profile_id, ["alpha", "beta"])
    handler = make_vector_reindex_handler(FakeEmbedder().embed)
    job = make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10, "batch_size": 2})
    handler(db_session, job, no_report)
    job.status = "done"
    job.finished_at = job.created_at
    db_session.commit()

    overview = client.get("/api/v1/admin/retrieval/overview").json()
    assert overview["state"] == "ready"
    assert overview["cold"] is False
    assert overview["space"]["space_id"] == LEGACY_SPACE_ID
    assert overview["space"]["backend"] == "sqlite_vec"
    assert overview["space"]["records"] == 2
    assert overview["coverage"]["total"] == 2
    assert overview["coverage"]["coverage"] == 1.0
    assert overview["space"]["last_reindex_at"] is not None
    assert overview["recent_runs"][0]["run"]["job_type"] == "VECTOR_REINDEX"
    assert overview["recent_runs"][0]["run"]["status"] == "succeeded"
    assert overview["recent_runs"][0]["result"]["embedded"] == 2
    assert_no_raw_text(overview)

    spaces = client.get("/api/v1/admin/retrieval/spaces").json()
    assert len(spaces["spaces"]) == 1
    assert spaces["cold"] is False

    runs = client.get("/api/v1/admin/retrieval/runs").json()["runs"]
    assert runs and runs[0]["run"]["job_type"] == "VECTOR_REINDEX"

    health = client.get(
        "/api/v1/admin/retrieval/query-health", params={"window": "24h"}
    ).json()
    assert health["query_count"] == 0
    assert health["health"]["per_view_hits"] == {}
    assert health["health"]["sampled"] is False


def test_read_surface_degraded_state(
    client: TestClient, db_session: Session, profile_id: str
) -> None:
    seed_chunks(db_session, profile_id, ["bad text"])
    job = make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10})
    make_vector_reindex_handler(FakeEmbedder(fail_on="bad").embed)(db_session, job, no_report)

    body = client.get("/api/v1/admin/retrieval/overview").json()
    assert body["state"] == "degraded"
    assert body["coverage"]["failed"] == 1
    assert body["coverage"]["coverage"] == 0.0
    assert any("Q3b" in note for note in body["notes"])
    assert_no_raw_text(body)


def test_read_helpers_treat_partial_scan_as_no_snapshot(
    db_session: Session, profile_id: str
) -> None:
    seed_chunks(db_session, profile_id, ["alpha", "beta", "gamma"])
    job = make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 1, "batch_size": 1})
    make_vector_reindex_handler(FakeEmbedder().embed)(db_session, job, no_report)
    assert db_session.scalars(select(RetrievalCoverageSnapshot)).all() == []
    store = load_store(db_session)
    assert store is not None
    assert reads.coverage(db_session)["cold"] is True


def test_read_surface_requires_admin(raw_client: TestClient) -> None:
    response = raw_client.get("/api/v1/admin/retrieval/overview")
    assert response.status_code in (401, 403)
