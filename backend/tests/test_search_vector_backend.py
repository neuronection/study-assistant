"""Search stays unchanged across the vector-backend adoption (plan 51 Q3c2a).

``retrieve_chunks_hybrid`` keeps the same FTS5/tsvector candidate set and RRF
weights; only the vector candidate source moves from the v1 ``chunk_vecs``
SQL to the provisioned backend. These tests pin:

* a cold store (no vectors) degrades to lexical, exactly as before;
* once vectors exist, the fused result is deterministic;
* forcing the v1 fallback (the backend reports its table missing) returns
  the same fused result — no silent ranking change during the compatibility
  window.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.domain.models import Chunk, Course, Extraction, Material, Profile
from app.services.search import retrieve_chunks_hybrid
from app.storage import vectors
from app.storage.fts import sync_material_fts
from app.storage.vector_backends import SqliteVecBackend, VectorIndexMissing
from app.storage.vector_store import StudyVectorStore

DIM = 4


def basis(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index % DIM] = 1.0
    return vector


def _seed(session: Session, owner: Any) -> list[str]:
    profile = Profile(user_id=owner.id, name="Default", is_default=True)
    session.add(profile)
    session.flush()
    course = Course(profile_id=profile.id, title="Search parity")
    session.add(course)
    session.flush()
    material = Material(
        profile_id=profile.id,
        course_id=course.id,
        kind="md",
        title="Calculus notes",
        filename=f"{uuid.uuid4().hex[:8]}.md",
        status="ready",
    )
    session.add(material)
    session.flush()
    texts = ["derivative limit rules", "integral area theorem"]
    extraction = Extraction(
        material_id=material.id,
        extractor="test",
        blocks=[{"type": "text", "md": "\n\n".join(texts)}],
        markdown="\n\n".join(texts),
    )
    session.add(extraction)
    session.flush()
    sync_material_fts(session, material, extraction.markdown)
    chunks = [
        Chunk(extraction_id=extraction.id, ordinal=index, text=text)
        for index, text in enumerate(texts)
    ]
    session.add_all(chunks)
    session.commit()
    return [str(chunk.id) for chunk in chunks]


def _embed(query: str) -> tuple[str, list[list[float]]]:
    del query
    return ("fake-embed", [basis(0)])


def test_hybrid_search_cold_store_falls_back_to_lexical(db_session: Session, owner: Any) -> None:
    chunk_ids = _seed(db_session, owner)
    rows = retrieve_chunks_hybrid(db_session, "derivative", _embed)
    assert rows
    assert {row["chunk_id"] for row in rows} == set(chunk_ids)

    assert vectors.table_exists(db_session) is False


def test_hybrid_search_is_identical_on_the_provisioned_and_v1_paths(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunk_ids = _seed(db_session, owner)
    store = StudyVectorStore(db_session)
    store.store(chunk_ids, [basis(0), basis(1)], "fake-embed")
    db_session.commit()
    assert store.health().provisioned is True

    provisioned = retrieve_chunks_hybrid(db_session, "derivative", _embed)
    assert provisioned
    assert provisioned[0]["chunk_id"] == chunk_ids[0]

    def missing(self: SqliteVecBackend, *args: Any, **kwargs: Any) -> Any:
        del self, args, kwargs
        raise VectorIndexMissing("forced v1 fallback")

    monkeypatch.setattr(SqliteVecBackend, "search", missing)
    v1 = retrieve_chunks_hybrid(db_session, "derivative", _embed)
    assert v1 == provisioned

    lexical = retrieve_chunks_hybrid(db_session, "derivative", _embed, use_embeddings=False)
    assert [row["chunk_id"] for row in lexical] == [row["chunk_id"] for row in provisioned]


def test_hybrid_search_lexical_path_never_calls_the_vector_store(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(db_session, owner)

    def boom(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("vector path must not run when embeddings are disabled")

    monkeypatch.setattr(StudyVectorStore, "search", boom)
    rows = retrieve_chunks_hybrid(db_session, "integral", _embed, use_embeddings=False)
    assert rows
    assert {row["text"] for row in rows} == {"derivative limit rules", "integral area theorem"}
