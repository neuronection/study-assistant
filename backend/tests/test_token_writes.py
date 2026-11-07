"""Token-aware v2 writes, batching and cutover beside retained v1 (T5b2)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.tokenizers import resolve_tokenizer_spec
from app.core.vocab import JobType
from app.domain.models import (
    Chunk,
    Course,
    Extraction,
    Job,
    Material,
    VectorRecord,
    VectorSpace,
)
from app.pipelines.chunking import InputTooLong
from app.pipelines.retrieval_ops import make_vector_reindex_handler
from app.services.retrieval import lifecycle
from app.services.retrieval.chunk_profile import (
    ChunkProfile,
    WindowSpec,
    batch_window_specs,
    profile_for_space,
    resolve_chunk_profile,
)
from app.storage.retrieval_ops import GateStatus
from app.storage.tokenizer_contract import ChunkConfig, TokenizerKind
from app.storage.vector_contract import content_hash, space_key_token_aware
from app.storage.vector_contract import space_key as v1_key
from app.storage.vector_store import StudyVectorStore, content_space_for

DIM = 4


class FakeEmbedder:
    def __init__(self, model: str = "fake-embed") -> None:
        self.model = model
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        self.calls.append(list(texts))
        return (
            self.model,
            [[1.0, float(index) / 10.0, 0.0, 0.0] for index, _text in enumerate(texts)],
        )


def _seed(session: Session, profile_id: str, texts: list[str]) -> tuple[Material, list[Chunk]]:
    course = Course(profile_id=profile_id, title="Token writes")
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
    return material, chunks


def _job(session: Session, job_type: JobType, payload: dict[str, Any]) -> Job:
    job = Job(type=job_type.value, payload=payload, status="running", progress=0)
    session.add(job)
    session.commit()
    return job


def _reindex(session: Session, space_id: str | None, embedder: FakeEmbedder) -> Job:
    payload: dict[str, Any] = {"limit": 50, "batch_size": 8}
    if space_id is not None:
        payload["space_id"] = space_id
    job = _job(session, JobType.VECTOR_REINDEX, payload)
    make_vector_reindex_handler(embedder.embed)(session, job, lambda *_: None)
    return job


def _exact_profile(**overrides: int) -> ChunkProfile:
    chunk = ChunkConfig(
        max_chunk_tokens=overrides.get("max_chunk_tokens", 64),
        overlap_tokens=overrides.get("overlap_tokens", 8),
        max_chars=overrides.get("max_chars", 400),
    )
    return resolve_chunk_profile(
        "openai_compatible",
        "text-embedding-3-small",
        tokenizer=resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small"),
        chunk=chunk,
    )


def _build_v2(
    session: Session,
    *,
    name: str = "content-v2",
    max_chunk_tokens: int = 64,
    overlap_tokens: int = 8,
    max_chars: int = 400,
) -> VectorSpace:
    profile = _exact_profile(
        max_chunk_tokens=max_chunk_tokens,
        overlap_tokens=overlap_tokens,
        max_chars=max_chars,
    )
    built, _changed = lifecycle.build_space(
        session,
        name=name,
        provider="openai",
        model="fake-embed",
        dim=DIM,
        tokenizer=profile.tokenizer,
        chunk=profile.chunk,
    )
    row = session.get(VectorSpace, built.space_id)
    assert row is not None
    return row


def test_profile_resolution_is_curated_then_labelled_fallback() -> None:
    exact = resolve_chunk_profile("openai_compatible", "text-embedding-3-small")
    assert exact.tokenizer.kind is TokenizerKind.TIKTOKEN
    assert exact.tokenizer.identifier == "cl100k_base"
    assert exact.exact is True
    assert exact.chunk.max_chunk_tokens == 512
    assert exact.chunk.overlap_tokens == 64

    fallback = resolve_chunk_profile("ollama", "unknown-embed")
    assert fallback.tokenizer.kind is TokenizerKind.HEURISTIC
    assert fallback.exact is False
    assert fallback.tokenizer.max_input_tokens == 2048


def test_build_space_persists_the_v2_pair_and_reconstructs_it(
    db_session: Session,
) -> None:
    row = _build_v2(db_session)
    assert row.chunker_version == "2"
    assert row.tokenizer_kind == "tiktoken"
    assert row.tokenizer_exact is True
    assert row.chunk_max_tokens == 64
    assert row.chunk_overlap_tokens == 8
    assert row.chunk_max_chars == 400
    assert row.space_key == space_key_token_aware(
        "openai",
        "fake-embed",
        DIM,
        True,
        None,
        None,
        "2",
        "1",
        tokenizer=resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small"),
        chunk=ChunkConfig(max_chunk_tokens=64, overlap_tokens=8, max_chars=400),
    )

    profile = profile_for_space(db_session, str(row.id))
    assert profile is not None
    assert profile.tokenizer.identifier == "cl100k_base"
    assert profile.chunk.max_chunk_tokens == 64

    space = StudyVectorStore(db_session, space_id=str(row.id)).content_space()
    assert space is not None
    assert space.token_aware is True
    assert space.tokenizer is not None and space.chunk is not None
    assert space.as_contract().token_aware is True
    assert space.as_contract().key == row.space_key
    assert space.as_contract().chunker_version == "2"


def test_half_a_pair_and_v1_builds(db_session: Session) -> None:
    with pytest.raises(ValueError, match="together"):
        lifecycle.build_space(
            db_session,
            name="half",
            provider="openai",
            model="fake-embed",
            dim=DIM,
            tokenizer=resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small"),
        )
    v1, _changed = lifecycle.build_space(
        db_session,
        name="v1",
        provider="openai",
        model="fake-embed",
        dim=DIM,
    )
    row = db_session.get(VectorSpace, v1.space_id)
    assert row is not None
    assert row.chunker_version == "1"
    assert row.tokenizer_kind is None
    assert row.space_key == v1_key("openai", "fake-embed", DIM, True, None, None, "1", "1")


def test_v2_backfill_writes_token_windows_and_retains_v1(
    db_session: Session, profile_id: str
) -> None:
    long_text = "alpha beta gamma delta epsilon zeta eta theta " * 40
    _material, chunks = _seed(db_session, profile_id, [long_text, "short"])
    v1_job = _reindex(db_session, None, FakeEmbedder("fake-embed"))
    assert v1_job.result is not None

    v1 = db_session.get(VectorSpace, "v1-chunk-vecs")
    assert v1 is not None
    v1_key = v1.space_key
    v1_records = list(
        db_session.scalars(select(VectorRecord).where(VectorRecord.space_id == v1.id))
    )
    assert v1_records
    assert all(record.token_count is None and record.token_start is None for record in v1_records)

    row = _build_v2(db_session, max_chunk_tokens=64, overlap_tokens=8, max_chars=400)
    job = _reindex(db_session, str(row.id), FakeEmbedder("fake-embed"))
    result = dict(job.result or {})
    assert result["gate"] == "pass"
    assert result["failed"] == 0

    records = list(
        db_session.scalars(
            select(VectorRecord)
            .where(VectorRecord.space_id == row.id)
            .order_by(VectorRecord.chunk_index)
        )
    )
    assert records
    long_id = str(chunks[0].id)
    long_records = [record for record in records if record.chunk_id == long_id]
    assert len(long_records) > 1
    assert {record.chunk_index for record in long_records} == set(range(len(long_records)))
    for record in records:
        assert record.token_count is not None
        assert record.token_start is not None
        assert record.token_end is not None
        assert record.token_count == record.token_end - record.token_start
        assert record.char_start is not None and record.char_end is not None
        assert record.char_end >= record.char_start
        assert record.content_hash
        assert record.chunk_id is not None
        source = next(chunk for chunk in chunks if str(chunk.id) == record.chunk_id)
        assert source.text[record.char_start : record.char_end]
        assert content_hash(source.text[record.char_start : record.char_end]) == (
            record.content_hash
        )

    db_session.expire_all()
    v1 = db_session.get(VectorSpace, "v1-chunk-vecs")
    assert v1 is not None
    assert v1.status == "active"
    assert v1.space_key == v1_key
    assert (
        db_session.scalar(select(VectorRecord).where(VectorRecord.space_id == v1.id).limit(1))
        is not None
    )
    assert (
        db_session.scalar(
            select(VectorRecord).where(
                VectorRecord.space_id == v1.id,
                VectorRecord.token_count.is_not(None),
            )
        )
        is None
    )

    store = StudyVectorStore(db_session, space_id=str(row.id))
    hits = store.search([1.0, 0.0, 0.0, 0.0], limit=10)
    assert hits
    assert len({chunk_id for chunk_id, _distance in hits}) == len(hits)


def test_v2_cutover_keeps_v1_and_reconstructs_the_active_space(
    db_session: Session, profile_id: str
) -> None:
    long_text = "one two three four five six seven eight " * 30
    _material, chunks = _seed(db_session, profile_id, [long_text, "short"])
    _reindex(db_session, None, FakeEmbedder("fake-embed"))
    v1 = db_session.get(VectorSpace, "v1-chunk-vecs")
    assert v1 is not None
    v1_key = v1.space_key
    v1_count = len(
        list(db_session.scalars(select(VectorRecord).where(VectorRecord.space_id == v1.id)))
    )

    row = _build_v2(db_session, max_chunk_tokens=48, overlap_tokens=8)
    job = _reindex(db_session, str(row.id), FakeEmbedder("fake-embed"))
    assert dict(job.result or {})["gate"] == "pass"

    activated = lifecycle.activate_space(
        db_session,
        str(row.id),
        quality=GateStatus.PASS,
        quality_state="sampled",
    )
    assert activated.previous_space_id == v1.id
    assert activated.previous_space_key == v1_key
    assert activated.v1_store_retained is True

    db_session.expire_all()
    previous = db_session.get(VectorSpace, v1.id)
    assert previous is not None and previous.status == "retired"
    current = content_space_for(db_session)
    assert current is not None
    assert current.space_id == str(row.id)
    assert current.token_aware is True
    assert current.key == activated.space_key
    assert current.tokenizer is not None
    assert current.tokenizer.identifier == "cl100k_base"
    assert current.chunk is not None and current.chunk.max_chunk_tokens == 48

    remaining = list(db_session.scalars(select(VectorRecord).where(VectorRecord.space_id == v1.id)))
    assert len(remaining) == v1_count
    assert all(record.token_count is None for record in remaining)
    assert chunks


def test_batching_honours_items_and_tokens_separately() -> None:
    profile = resolve_chunk_profile(
        "openai_compatible",
        "text-embedding-3-small",
        tokenizer=resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small"),
        chunk=ChunkConfig(max_chunk_tokens=64, overlap_tokens=8, max_chars=400),
    )
    profile = ChunkProfile(
        tokenizer=profile.tokenizer,
        chunk=profile.chunk,
        batch_max_items=2,
        batch_max_tokens=100,
    )
    specs = [
        WindowSpec(
            chunk_id=f"chunk-{index}",
            window_index=0,
            text="token " * 10,
            char_start=0,
            char_end=60,
            token_count=10,
            token_start=0,
            token_end=10,
        )
        for index in range(5)
    ]
    batches = batch_window_specs(specs, profile)
    assert [len(batch) for batch in batches] == [2, 2, 1]

    token_limited = ChunkProfile(
        tokenizer=profile.tokenizer,
        chunk=profile.chunk,
        batch_max_items=10,
        batch_max_tokens=15,
    )
    assert [len(batch) for batch in batch_window_specs(specs, token_limited)] == [
        1,
        1,
        1,
        1,
        1,
    ]


def test_per_item_limit_surfaces_input_too_long() -> None:
    profile = resolve_chunk_profile(
        "openai_compatible",
        "text-embedding-3-small",
        tokenizer=resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small"),
        chunk=ChunkConfig(max_chunk_tokens=64, overlap_tokens=8, max_chars=400),
    )
    spec = WindowSpec(
        chunk_id="chunk-1",
        window_index=0,
        text="x",
        char_start=0,
        char_end=1,
        token_count=8191,
        token_start=0,
        token_end=8191,
    )
    with pytest.raises(InputTooLong) as error:
        batch_window_specs([spec], profile)
    assert error.value.reason == "input_too_long"


def test_reindex_records_input_too_long_once_and_never_raw_text(
    db_session: Session, profile_id: str
) -> None:
    _material, chunks = _seed(db_session, profile_id, ["hello world"])
    row = _build_v2(db_session, max_chunk_tokens=32, overlap_tokens=4, max_chars=2)
    job = _reindex(db_session, str(row.id), FakeEmbedder("fake-embed"))
    result = dict(job.result or {})
    assert result["failed"] == 1
    assert result["embedded"] == 0
    assert result["failed_ids"] == [str(chunks[0].id)]
    assert result["failed_reason"] == "input_too_long"
    assert result["gate"] == "fail"
    serialized = json.dumps(result)
    assert "hello" not in serialized
    records = list(db_session.scalars(select(VectorRecord).where(VectorRecord.space_id == row.id)))
    assert records == []


def test_direct_insert_cannot_mix_v1_and_v2(db_session: Session) -> None:
    row = VectorSpace(
        id=str(uuid.uuid4()),
        name=f"mixed-{uuid.uuid4().hex[:8]}",
        provider="openai",
        model="fake-embed",
        dim=DIM,
        chunker_version="1",
        space_key="a" * 64,
        status="building",
        tokenizer_kind="tiktoken",
        tokenizer_identifier="cl100k_base",
        tokenizer_artifact_sha256="b" * 64,
        tokenizer_exact=True,
        max_input_tokens=8191,
        chunk_max_tokens=64,
        chunk_overlap_tokens=8,
        chunk_max_chars=400,
    )
    db_session.add(row)
    with pytest.raises(Exception, match="tokenizer_requires_chunker_version_2"):
        db_session.flush()
    db_session.rollback()
