"""Plan 51 Q3c2b1: real build/backfill/activate/retire/drop and cutover."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.vocab import JobType
from app.domain.models import (
    AuditEvent,
    Chunk,
    Course,
    Extraction,
    Job,
    Material,
    RetrievalCoverageSnapshot,
    VectorRecord,
    VectorSpace,
)
from app.pipelines.retrieval_ops import (
    make_vector_cutover_handler,
    make_vector_reindex_handler,
)
from app.services.retrieval import quality, reads
from app.services.retrieval.legacy import LEGACY_SPACE_ID
from app.services.retrieval.telemetry import QueryRollupRecorder, configure_recorder
from app.storage import retrieval_ops as ops
from app.storage import vectors
from app.storage.retrieval_ops import GateStatus, RunResultDTO
from app.storage.vector_provisioning import space_status
from app.storage.vector_schema import index_table_name
from app.storage.vector_store import StudyVectorStore

BASE = "/api/v1/admin/retrieval"
DIM = 4


class FakeEmbedder:
    def __init__(self, model: str = "fake-embed") -> None:
        self.model = model
        self.calls = 0

    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        self.calls += 1
        return (
            self.model,
            [
                [1.0, float(index) / 10.0, 0.0, 0.0]
                for index, _text in enumerate(texts)
            ],
        )


def _stop_worker(client: TestClient) -> None:
    cast(Any, client.app).state.jobs.stop()


def _key(name: str) -> dict[str, str]:
    return {"Idempotency-Key": name}


def _seed_chunks(
    session: Session, profile_id: str, texts: list[str]
) -> tuple[str, list[str]]:
    course = Course(profile_id=profile_id, title="Lifecycle")
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
    return str(material.id), [str(chunk.id) for chunk in chunks]


def _make_job(session: Session, job_type: JobType, payload: dict[str, Any]) -> Job:
    job = Job(type=job_type.value, payload=payload, status="running", progress=0)
    session.add(job)
    session.commit()
    return job


def _build(
    client: TestClient,
    *,
    name: str = "content-v2",
    model: str = "fake-embed-v2",
    dim: int = DIM,
    key: str = "build-key-0001",
) -> dict[str, Any]:
    response = client.post(
        f"{BASE}/spaces",
        json={"name": name, "provider": "fake", "model": model, "dim": dim},
        headers=_key(key),
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def _reindex(session: Session, space_id: str, embedder: FakeEmbedder) -> RunResultDTO:
    job = _make_job(
        session,
        JobType.VECTOR_REINDEX,
        {"space_id": space_id, "limit": 50, "batch_size": 8},
    )
    make_vector_reindex_handler(embedder.embed)(session, job, lambda *_: None)
    assert job.result is not None
    return RunResultDTO(**cast(dict[str, Any], job.result))


def _activate(client: TestClient, space_id: str, key: str) -> dict[str, Any]:
    response = client.post(
        f"{BASE}/spaces/{space_id}/activate", headers=_key(key)
    )
    return cast(dict[str, Any], response.json()) | {"_status": response.status_code}


class QueryEmbedder:
    """A query-only embedder for the quality compare's golden queries."""

    def __init__(self, vector: list[float], model: str = "fake-embed") -> None:
        self.vector = vector
        self.model = model

    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return (self.model, [self.vector for _ in texts])


def _stub_quality(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    *,
    space_id: str,
    material_id: str,
    query: str = "alpha",
    vector: list[float] | None = None,
) -> None:
    golden = ops.GoldenQuerySet(
        space_id=str(space_id),
        set_version=1,
        k=2,
        queries=(
            ops.GoldenQueryFixture(
                query_id="q-1",
                query=query,
                expected_document_ids=(material_id,),
                k=2,
            ),
        ),
    )
    monkeypatch.setattr(quality, "load_golden_sets", lambda: (golden,))
    cast(Any, client.app).state.embedder = QueryEmbedder(
        vector or [1.0, 0.0, 0.0, 0.0]
    )


def test_build_provisions_a_real_building_space_and_replays(
    client: TestClient, db_session: Session
) -> None:
    _stop_worker(client)
    body = _build(client)
    assert body["space_id"]
    assert body["space"]["status"] == "building"
    assert body["space"]["index_table"] == index_table_name(body["space_id"])
    assert body["space"]["space_key"]
    assert body["quality"] is None
    assert body["quality_state"] == "not_sampled"

    row = db_session.get(VectorSpace, body["space_id"])
    assert row is not None
    assert row.status == "building"
    assert row.index_table == index_table_name(row.id)
    physical = space_status(db_session, row)
    assert physical.table_exists is True
    assert physical.table_dim == DIM

    replay = _build(client)
    assert replay["space_id"] == body["space_id"]
    assert replay["deduplicated"] is True
    assert (
        db_session.scalar(select(func.count()).select_from(VectorSpace)) == 1
    )


def test_backfill_activate_retires_previous_and_keeps_chunk_vecs(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    material_id, chunk_ids = _seed_chunks(db_session, profile_id, ["alpha", "beta"])
    legacy_embedder = FakeEmbedder("fake-embed")
    legacy_job = _make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10})
    make_vector_reindex_handler(legacy_embedder.embed)(
        db_session, legacy_job, lambda *_: None
    )
    legacy = db_session.get(VectorSpace, LEGACY_SPACE_ID)
    assert legacy is not None and legacy.status == "active"
    legacy_table = legacy.index_table
    assert legacy_table is not None

    built = _build(client)
    candidate_id = built["space_id"]
    result = _reindex(db_session, candidate_id, FakeEmbedder("fake-embed-v2"))
    assert result.gate is GateStatus.PASS
    assert result.embedded == 2

    candidate = db_session.get(VectorSpace, candidate_id)
    assert candidate is not None
    assert candidate.status == "building"
    records = db_session.scalars(
        select(VectorRecord).where(VectorRecord.space_id == candidate_id)
    ).all()
    assert {record.chunk_id for record in records} == set(chunk_ids)
    snapshots = db_session.scalars(
        select(RetrievalCoverageSnapshot).where(
            RetrievalCoverageSnapshot.space_id == candidate_id
        )
    ).all()
    assert snapshots and snapshots[-1].embedded == 2

    stored_before_cutover = "f" * 64
    legacy.space_key = stored_before_cutover
    db_session.commit()

    _stub_quality(
        monkeypatch,
        client,
        space_id=candidate_id,
        material_id=material_id,
    )
    activated = _activate(client, candidate_id, "activate-key-0001")
    assert activated["_status"] == 200, activated
    assert activated["space"]["space_id"] == candidate_id
    assert activated["space"]["previous_space_id"] == LEGACY_SPACE_ID
    assert activated["space"]["previous_space_key"] == stored_before_cutover
    assert activated["quality"]["passed"] is True
    assert activated["quality_state"] == "sampled"
    assert activated["gate"] == "pass"
    assert activated["activation_gate"]["coverage_status"] == "pass"
    assert activated["activation_gate"]["quality"] == "pass"

    db_session.expire_all()
    assert db_session.get(VectorSpace, candidate_id).status == "active"  # type: ignore[union-attr]
    retired = db_session.get(VectorSpace, LEGACY_SPACE_ID)
    assert retired is not None and retired.status == "retired"
    assert (
        db_session.scalar(
            select(func.count()).select_from(VectorSpace).where(
                VectorSpace.status == "active"
            )
        )
        == 1
    )
    assert vectors.table_exists(db_session) is True
    assert vectors.vector_count(db_session) == 2

    store = StudyVectorStore(db_session)
    assert store.content_space() is not None
    assert store.content_space().space_id == candidate_id  # type: ignore[union-attr]
    hits = store.search([1.0, 0.0, 0.0, 0.0], limit=2)
    assert {chunk_id for chunk_id, _distance in hits} <= set(chunk_ids)
    assert hits

    space_dto = reads.spaces(db_session)
    assert space_dto["active_space_id"] == candidate_id
    statuses = {entry["space_id"]: entry["status"] for entry in space_dto["spaces"]}
    assert statuses == {candidate_id: "active", LEGACY_SPACE_ID: "retired"}


def test_activation_refuses_missing_coverage_and_missing_physical_index(
    client: TestClient, db_session: Session
) -> None:
    _stop_worker(client)
    built = _build(client, key="build-key-0002")
    candidate_id = built["space_id"]

    refused = _activate(client, candidate_id, "activate-key-0002")
    assert refused["_status"] == 409
    assert refused["detail"]["quality_state"] == "not_sampled"
    assert refused["detail"]["quality"] is None
    gate = refused["detail"]["activation_gate"]
    assert gate["coverage_status"] == "unknown"
    assert gate["quality"] == "fail"
    assert gate["allowed"] is False
    assert "coverage_unknown" in gate["reasons"]
    assert "quality_no_golden_set" in gate["reasons"]
    assert db_session.get(VectorSpace, candidate_id).status == "building"  # type: ignore[union-attr]

    row = db_session.get(VectorSpace, candidate_id)
    assert row is not None
    db_session.execute(text(f"DROP TABLE {row.index_table}"))
    db_session.execute(
        text("DELETE FROM retrieval_coverage_snapshots WHERE space_id = :id"),
        {"id": candidate_id},
    )
    db_session.commit()

    physical_refusal = _activate(client, candidate_id, "activate-key-0003")
    assert physical_refusal["_status"] == 409
    assert physical_refusal["detail"]["reason"] == "space_state_invalid"


def test_retire_drop_confirmations_grace_and_never_active(
    client: TestClient, db_session: Session, profile_id: str
) -> None:
    _stop_worker(client)
    _material_id, _chunk_ids = _seed_chunks(db_session, profile_id, ["alpha"])
    job = _make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10})
    make_vector_reindex_handler(FakeEmbedder().embed)(
        db_session, job, lambda *_: None
    )
    active_id = LEGACY_SPACE_ID

    active_refusal = client.post(
        f"{BASE}/spaces/{active_id}/drop",
        json={"confirm_space_name": "content", "force": True},
        headers=_key("drop-key-0001"),
    )
    assert active_refusal.status_code == 409
    assert active_refusal.json()["detail"]["reason"] == "space_state_invalid"

    built = _build(client, key="build-key-0003")
    candidate_id = built["space_id"]

    while_building = client.post(
        f"{BASE}/spaces/{candidate_id}/drop",
        json={"confirm_space_name": "content-v2", "force": True},
        headers=_key("drop-key-0002"),
    )
    assert while_building.status_code == 409

    wrong = client.post(
        f"{BASE}/spaces/{candidate_id}/retire",
        json={"confirm_space_name": "wrong"},
        headers=_key("retire-key-0001"),
    )
    assert wrong.status_code == 422
    assert wrong.json()["detail"]["reason"] == "confirmation_mismatch"

    retired = client.post(
        f"{BASE}/spaces/{candidate_id}/retire",
        json={"confirm_space_name": "content-v2"},
        headers=_key("retire-key-0002"),
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["space"]["status"] == "retired"

    in_grace = client.post(
        f"{BASE}/spaces/{candidate_id}/drop",
        json={"confirm_space_name": "content-v2"},
        headers=_key("drop-key-0003"),
    )
    assert in_grace.status_code == 409

    forced = client.post(
        f"{BASE}/spaces/{candidate_id}/drop",
        json={"confirm_space_name": "content-v2", "force": True},
        headers=_key("drop-key-0004"),
    )
    assert forced.status_code == 200, forced.text
    assert forced.json()["space"]["dropped"] is True
    assert db_session.get(VectorSpace, candidate_id) is None


def test_cutover_backfills_gates_activates_and_retires_legacy(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    material_id, _chunk_ids = _seed_chunks(
        db_session, profile_id, ["alpha", "beta", "gamma"]
    )
    legacy_job = _make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10})
    make_vector_reindex_handler(FakeEmbedder().embed)(
        db_session, legacy_job, lambda *_: None
    )
    built = _build(client, key="build-key-0004")
    candidate_id = built["space_id"]
    _stub_quality(
        monkeypatch,
        client,
        space_id=candidate_id,
        material_id=material_id,
    )

    accepted = client.post(
        f"{BASE}/cutover",
        json={"space_id": candidate_id, "limit": 10},
        headers=_key("cutover-key-0001"),
    )
    assert accepted.status_code == 202, accepted.text
    body = accepted.json()
    assert body["quality"] is None
    assert body["quality_state"] == "pending"
    run_id = body["run_id"]

    replay = client.post(
        f"{BASE}/cutover",
        json={"space_id": candidate_id, "limit": 10},
        headers=_key("cutover-key-0001"),
    )
    assert replay.status_code == 200
    assert replay.json()["run_id"] == run_id
    assert replay.json()["deduplicated"] is True

    locked = client.post(
        f"{BASE}/cutover",
        json={"space_id": candidate_id, "limit": 10},
        headers=_key("cutover-key-0002"),
    )
    assert locked.status_code == 409
    assert locked.json()["detail"]["reason"] == "run_in_progress"

    cancelled = client.post(f"{BASE}/runs/{run_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    retried = client.post(
        f"{BASE}/runs/{run_id}/retry", headers=_key("cutover-retry-0001")
    )
    assert retried.status_code == 202, retried.text
    retry_id = retried.json()["run_id"]
    assert retry_id != run_id

    db_session.expire_all()
    job = db_session.get(Job, retry_id)
    assert job is not None
    make_vector_cutover_handler(FakeEmbedder("fake-embed-v2").embed)(
        db_session, job, lambda *_: None
    )
    result = cast(dict[str, Any], job.result)
    assert result["action"] == "cutover"
    assert result["gate"] == "pass"
    assert result["quality"]["passed"] is True
    assert result["quality_state"] == "sampled"
    assert result["activation_gate"]["quality"] == "pass"
    assert result["space"]["space_id"] == candidate_id
    assert result["space"]["previous_space_id"] == LEGACY_SPACE_ID
    assert result["space"]["legacy_compat_retained"] is True

    db_session.expire_all()
    assert db_session.get(VectorSpace, candidate_id).status == "active"  # type: ignore[union-attr]
    assert db_session.get(VectorSpace, LEGACY_SPACE_ID).status == "retired"  # type: ignore[union-attr]
    assert vectors.table_exists(db_session) is True

    actions = list(db_session.scalars(select(AuditEvent.action)))
    assert "vector.space.activated" in actions
    assert "vector.gate.failed" not in actions
    serialized = json.dumps(
        [
            {"action": row.action, "resource": row.resource, "outcome": row.outcome}
            for row in db_session.scalars(select(AuditEvent))
        ]
    )
    assert "alpha" not in serialized


def test_rollups_and_health_follow_the_active_space_id(
    db_session: Session, profile_id: str
) -> None:
    _seed_chunks(db_session, profile_id, ["alpha"])
    recorder = QueryRollupRecorder(
        sessionmaker(bind=db_session.get_bind()), flush_interval=3600
    )
    configure_recorder(recorder)
    try:
        recorder.record(
            latency_ms=12,
            candidates=3,
            zero_results=False,
            kind="chunk",
            space_id="space-real-id-1",
        )
        recorder.flush(db_session)
    finally:
        configure_recorder(None)

    from app.domain.models import RetrievalQueryRollup

    db_session.add(
        VectorSpace(
            id="space-real-id-1",
            name="content",
            provider="fake",
            model="fake-embed",
            dim=DIM,
            index_table=None,
            status="active",
        )
    )
    db_session.commit()

    rows = db_session.scalars(select(RetrievalQueryRollup)).all()
    assert {row.space_id for row in rows} == {"space-real-id-1"}
    health = reads.query_health(db_session)
    assert health["health"]["space_id"] == "space-real-id-1"
    assert health["query_count"] == 1


def test_legacy_retirement_drops_chunk_vecs_but_search_stays_on_new_space(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    material_id, chunk_ids = _seed_chunks(db_session, profile_id, ["alpha", "beta"])
    legacy_job = _make_job(db_session, JobType.VECTOR_REINDEX, {"limit": 10})
    make_vector_reindex_handler(FakeEmbedder().embed)(
        db_session, legacy_job, lambda *_: None
    )
    built = _build(client, key="build-key-0005")
    candidate_id = built["space_id"]
    _reindex(db_session, candidate_id, FakeEmbedder("fake-embed-v2"))
    _stub_quality(
        monkeypatch,
        client,
        space_id=candidate_id,
        material_id=material_id,
    )
    activated = _activate(client, candidate_id, "activate-key-0005")
    assert activated["_status"] == 200, activated

    drop = client.post(
        f"{BASE}/spaces/{LEGACY_SPACE_ID}/drop",
        json={"confirm_space_name": "content", "force": True},
        headers=_key("drop-key-0005"),
    )
    assert drop.status_code == 200, drop.text
    assert db_session.get(VectorSpace, LEGACY_SPACE_ID) is None
    assert vectors.table_exists(db_session) is False

    store = StudyVectorStore(db_session)
    assert store.content_space().space_id == candidate_id  # type: ignore[union-attr]
    hits = store.search([1.0, 0.0, 0.0, 0.0], limit=2)
    assert hits and {chunk_id for chunk_id, _ in hits} <= set(chunk_ids)
