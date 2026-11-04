"""Every production chunk-creation site honours an active v2 space (T5b2)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.tokenizers import resolve_tokenizer_spec
from app.domain.models import (
    Chunk,
    Course,
    Material,
    VectorSpace,
)
from app.pipelines.chunking import chunk_markdown
from app.pipelines.ingest import _store_extraction
from app.services.content.materials import MaterialsService
from app.services.retrieval.chunk_profile import chunk_texts_for_space, profile_for_space

SITES = (
    "app/pipelines/ingest.py",
    "app/services/platform/trash.py",
    "app/services/content/materials.py",
    "app/services/content/course_import.py",
)
LONG_TEXT = "alpha beta gamma delta epsilon zeta eta theta " * 40


def _active_v2(
    session: Session, *, max_chunk_tokens: int = 64, max_chars: int = 400
) -> VectorSpace:
    spec = resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")
    row = VectorSpace(
        id=str(uuid.uuid4()),
        name=f"site-{uuid.uuid4().hex[:8]}",
        provider="openai",
        model="text-embedding-3-small",
        dim=4,
        chunker_version="2",
        composer_version="1",
        tokenizer_kind=spec.kind.value,
        tokenizer_identifier=spec.identifier,
        tokenizer_artifact_sha256=spec.artifact_sha256,
        tokenizer_exact=spec.exact,
        max_input_tokens=spec.max_input_tokens,
        chunk_max_tokens=max_chunk_tokens,
        chunk_overlap_tokens=8,
        chunk_max_chars=max_chars,
        index_table=None,
        status="active",
    )
    session.add(row)
    session.commit()
    return row


def _material(session: Session, profile_id: str) -> Material:
    course = Course(profile_id=profile_id, title="Sites")
    session.add(course)
    session.flush()
    material = Material(
        profile_id=profile_id,
        course_id=course.id,
        kind="md",
        title="Site notes",
        filename="notes.md",
        status="ready",
    )
    session.add(material)
    session.commit()
    return material


def test_all_chunk_creation_sites_use_the_space_chunker() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in SITES:
        source = (root / relative).read_text(encoding="utf-8")
        assert "chunk_texts_for_space" in source, relative
        assert "chunk_markdown(" not in source, relative


def test_chunk_texts_for_space_uses_exact_token_windows(
    db_session: Session,
) -> None:
    _active_v2(db_session)
    profile = profile_for_space(db_session)
    assert profile is not None
    chunks = chunk_texts_for_space(db_session, LONG_TEXT)
    assert len(chunks) > 1
    assert all(tokens <= profile.chunk.max_chunk_tokens for _text, tokens in chunks)
    assert all(text.strip() for text, _tokens in chunks)
    assert "".join(text for text, _tokens in chunks) != LONG_TEXT


def test_ingest_creates_token_chunks_for_a_v2_space(
    db_session: Session, profile_id: str
) -> None:
    row = _active_v2(db_session)
    material = _material(db_session, profile_id)
    extraction = _store_extraction(
        db_session,
        material,
        extractor="test",
        markdown=LONG_TEXT,
        pages=1,
    )
    chunks = list(
        db_session.scalars(
            select(Chunk).where(Chunk.extraction_id == extraction.id).order_by(Chunk.ordinal)
        )
    )
    assert len(chunks) > 1
    assert all(chunk.token_count is not None for chunk in chunks)
    assert all(
        chunk.token_count <= row.chunk_max_tokens  # type: ignore[operator]
        for chunk in chunks
    )
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_material_edit_creates_token_chunks_for_a_v2_space(
    db_session: Session, profile_id: str
) -> None:
    row = _active_v2(db_session)
    material = _material(db_session, profile_id)
    service = MaterialsService(db_session, cast(Any, None))
    extraction, previous = service.edit_extraction(material, LONG_TEXT)
    assert previous == []
    chunks = list(
        db_session.scalars(
            select(Chunk).where(Chunk.extraction_id == extraction.id).order_by(Chunk.ordinal)
        )
    )
    assert len(chunks) > 1
    assert all(
        chunk.token_count is not None
        and chunk.token_count <= row.chunk_max_tokens  # type: ignore[operator]
        for chunk in chunks
    )


def test_v1_space_still_uses_the_character_chunker(
    db_session: Session, profile_id: str
) -> None:
    material = _material(db_session, profile_id)
    extraction = _store_extraction(
        db_session,
        material,
        extractor="test",
        markdown=LONG_TEXT,
        pages=1,
    )
    chunks = list(
        db_session.scalars(
            select(Chunk).where(Chunk.extraction_id == extraction.id).order_by(Chunk.ordinal)
        )
    )
    assert [chunk.text for chunk in chunks] == chunk_markdown(LONG_TEXT)
    assert all(chunk.token_count is not None for chunk in chunks)


def test_profile_reconstruction_rejects_a_legacy_space(db_session: Session) -> None:
    row = VectorSpace(
        id=str(uuid.uuid4()),
        name=f"legacy-{uuid.uuid4().hex[:8]}",
        provider="openai",
        model="text-embedding-3-small",
        dim=4,
        chunker_version="1",
        composer_version="1",
        status="active",
    )
    db_session.add(row)
    db_session.commit()
    assert profile_for_space(db_session, str(row.id)) is None
    assert profile_for_space(db_session) is None
    assert len(chunk_texts_for_space(db_session, "one two three")) == 1
