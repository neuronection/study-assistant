"""Plan 52 T5c — bounded live indexing progress in the study retrieval path."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from alembic.config import Config
from sqlalchemy.orm import Session

from alembic import command
from app.core.events import EventBus
from app.core.vocab import JobType
from app.domain.models import Chunk, Course, Extraction, Job, Material
from app.jobs.runner import JobRunner
from app.pipelines.retrieval_ops import make_vector_reindex_handler
from app.services.progress import PROGRESS_DETAIL_KEYS
from app.services.retrieval import actions, lifecycle
from app.services.retrieval.chunk_profile import resolve_chunk_profile
from app.storage.db import make_engine, make_session_factory


class FakeEmbedder:
    def __init__(self, model: str = "fake-embed") -> None:
        self.model = model
        self.calls = 0

    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        self.calls += 1
        return (
            self.model,
            [[1.0, 0.0, 0.0, float(index)] for index, _text in enumerate(texts)],
        )


@dataclass
class Recorder:
    writes: list[tuple[int, str, dict[str, Any] | None]]

    def __init__(self) -> None:
        self.writes = []

    def __call__(self, value: int, stage: str, detail: dict[str, Any] | None = None) -> None:
        self.writes.append((value, stage, dict(detail) if detail is not None else None))

    @property
    def details(self) -> list[dict[str, Any]]:
        return [detail for _value, _stage, detail in self.writes if detail is not None]


def _seed_chunks(session: Session, profile_id: str, texts: list[str]) -> list[str]:
    course = Course(profile_id=profile_id, title="Live progress")
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
    return [str(chunk.id) for chunk in chunks]


def _job(session: Session, payload: dict[str, Any]) -> Job:
    job = Job(type=JobType.VECTOR_REINDEX.value, payload=payload, status="running", progress=0)
    session.add(job)
    session.commit()
    return job


def _run(
    session: Session, payload: dict[str, Any], embedder: FakeEmbedder | None = None
) -> tuple[Job, Recorder]:
    job = _job(session, payload)
    recorder = Recorder()
    make_vector_reindex_handler((embedder or FakeEmbedder()).embed)(session, job, recorder)
    return job, recorder


def test_progress_detail_is_folded_into_one_write_per_document(
    db_session: Session, profile_id: str
) -> None:
    chunk_ids = _seed_chunks(db_session, profile_id, ["alpha", "beta", "gamma"])
    _job_row, recorder = _run(db_session, {"limit": 10, "batch_size": 2})

    per_document = [
        stage
        for _value, stage, _detail in recorder.writes
        if stage.startswith("reindex ") and stage != "reindex complete"
    ]
    assert len(per_document) == 3, "one folded progress write per document"
    assert all(
        detail is not None
        for _value, stage, detail in recorder.writes
        if stage.startswith("reindex ")
    )

    final = recorder.details[-1]
    assert set(final) == PROGRESS_DETAIL_KEYS
    assert final["total_documents"] == 3, "documents are exact at scan start"
    assert final["processed_documents"] == 3
    assert final["embedded_documents"] == 3
    assert final["skipped_documents"] == 0
    assert final["failed_documents"] == 0
    assert final["pending_chunks"] == 0
    assert final["total_chunks"] == final["processed_chunks"]
    assert final["chunks_estimated"] is False, "the v1 path has one record per chunk"
    assert final["done"] is True
    assert final["embed_calls"] >= 1
    assert isinstance(final["tokens"], int) and final["tokens"] >= 0

    serialized = str(recorder.details)
    for chunk_id in chunk_ids:
        assert chunk_id not in serialized, "no chunk ids in the progress detail"
    for text in ("alpha", "beta", "gamma"):
        assert text not in serialized, "no document text in the progress detail"


def test_progress_carry_resumes_without_resetting_the_bar(
    db_session: Session, profile_id: str
) -> None:
    _seed_chunks(db_session, profile_id, ["one", "two", "three", "four", "five"])

    _first_job, first = _run(db_session, {"limit": 2, "batch_size": 2})
    opening = first.details[0]
    assert opening["processed_documents"] == 0
    assert opening["total_documents"] == 5
    partial = first.details[-1]
    assert partial["processed_documents"] == 2
    assert partial["total_documents"] == 5
    assert partial["pending_chunks"] > 0, "a limited run leaves a visible remainder"
    assert partial["done"] is False

    _second_job, second = _run(
        db_session,
        {
            "limit": 2,
            "batch_size": 2,
            "progress_carry": partial,
        },
    )
    resumed = second.details[0]
    assert resumed["total_documents"] == 5, "the carried total survives the continuation"
    assert resumed["processed_documents"] == 2, "the bar resumes instead of resetting"
    assert second.details[-1]["processed_documents"] == 4


def test_token_aware_run_reports_windows_and_marks_the_chunk_total_estimated(
    db_session: Session, profile_id: str
) -> None:
    _seed_chunks(db_session, profile_id, ["alpha beta gamma delta"])
    profile = resolve_chunk_profile("fake", "fake-embed-v2")
    built, _changed = lifecycle.build_space(
        db_session,
        name="progress-v2",
        provider="fake",
        model="fake-embed-v2",
        dim=4,
        tokenizer=profile.tokenizer,
        chunk=profile.chunk,
    )
    _job_row, recorder = _run(
        db_session,
        {"space_id": built.space_id, "limit": 10, "batch_size": 8},
        FakeEmbedder("fake-embed-v2"),
    )
    final = recorder.details[-1]
    assert final["total_documents"] == 1
    assert final["processed_documents"] == 1
    assert final["chunks_estimated"] is True, "the v2 window total is never claimed exact"
    assert final["processed_chunks"] >= 1
    assert final["embedded_chunks"] == final["processed_chunks"]
    assert final["exact_tokenizer"] is False, "the fake model resolves the labelled fallback"
    assert final["tokens_estimated"] is True
    assert final["tokens"] is not None and final["tokens"] > 0


def test_retry_carries_the_live_counters_forward(db_session: Session, profile_id: str) -> None:
    _seed_chunks(db_session, profile_id, ["alpha"])
    failed = Job(
        type=JobType.VECTOR_REINDEX.value,
        payload={"space_id": "legacy-chunk-vecs", "limit": 10},
        status="failed",
        error="provider exploded",
        progress_detail={
            "phase": "embedding",
            "processed_documents": 3,
            "total_documents": 9,
            "processed_chunks": 3,
            "pending_chunks": 6,
            "total_chunks": 9,
            "chunks_estimated": False,
            "embedded_chunks": 2,
            "skipped_chunks": 1,
            "failed_chunks": 0,
            "embedded_documents": 2,
            "skipped_documents": 1,
            "failed_documents": 0,
            "tokens": 120,
            "tokens_estimated": False,
            "embed_calls": 1,
            "exact_tokenizer": True,
            "done": False,
        },
    )
    db_session.add(failed)
    db_session.commit()

    response = actions.retry_run(
        db_session, actor="admin@example.com", run_id=failed.id, idempotency_key="retry-progress-1"
    )
    retried = db_session.get(Job, response["run_id"])
    assert retried is not None
    carry = cast(dict[str, Any], retried.payload)["progress_carry"]
    assert carry["processed_documents"] == 3
    assert carry["total_documents"] == 9
    assert carry["tokens"] == 120
    assert carry["tokens_exact"] is True
    assert "phase" not in carry
    assert "failed_ids" not in carry


def test_runner_bounds_the_detail_and_prunes_it_when_the_result_commits(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "progress-runner.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, "head")
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    observed: dict[str, Any] = {}

    def handler(session: Session, job: Job, report: Any) -> None:
        report(
            10,
            "scanning",
            {
                "phase": "embedding",
                "processed_documents": 2,
                "total_documents": 4,
                "tokens": -1,
                "embed_calls": 1,
                "source_ids": ["chunk-1"],
                "text": "must never persist",
            },
        )
        session.refresh(job)
        observed.update(cast(dict[str, Any], job.progress_detail or {}))
        job.result = cast(Any, {"scanned": 2, "embedded": 2})

    runner = JobRunner(
        factory,
        EventBus(),
        handlers={JobType.VECTOR_REINDEX.value: handler},
        poll_interval=0.02,
        workers=1,
    )
    with factory() as session:
        job = JobRunner.enqueue(
            session,
            JobType.VECTOR_REINDEX.value,
            cast(Any, {"space_id": "legacy-chunk-vecs"}),
        )
        session.commit()
        job_id = job.id

    runner.start()
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with factory() as session:
                row = session.get(Job, job_id)
                assert row is not None
                if row.status == "done":
                    break
            time.sleep(0.02)
        else:
            raise AssertionError("job did not finish before the timeout")
    finally:
        runner.stop()

    assert observed["phase"] == "embedding"
    assert observed["processed_documents"] == 2
    assert observed["total_documents"] == 4
    assert observed["tokens"] == 0, "a negative counter clamps to zero"
    assert "source_ids" not in observed
    assert "text" not in observed

    with factory() as session:
        row = session.get(Job, job_id)
        assert row is not None
        assert row.progress_detail is None, "the result is authoritative"
        assert row.result == {"scanned": 2, "embedded": 2}
