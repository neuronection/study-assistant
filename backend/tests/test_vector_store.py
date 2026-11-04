"""Study vector-store adapter (plan 50 P3a).

The physical backend is deliberately legacy in P3a: these tests pin the
metadata mapping over ``chunk_vecs``/``chunk_vec_ids``, the explicit
model/dimension handoff (never a silent table drop), the cold state and the
absence of fabricated coverage.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    Chunk,
    Course,
    Extraction,
    Material,
    Profile,
    VectorSpace,
)
from app.services.retrieval import reads
from app.storage import vectors
from app.storage.vector_contract import content_hash
from app.storage.vector_schema import index_table_name
from app.storage.vector_store import (
    CONTENT_SPACE_ID,
    CONTENT_SPACE_NAME,
    CONTENT_VIEW,
    StudyVectorStore,
)

DIM = 4


def seed_material(session: Session, owner_id: str, texts: list[str]) -> tuple[str, list[str]]:
    profile = Profile(user_id=owner_id, name="Default", is_default=True)
    session.add(profile)
    session.flush()
    course = Course(profile_id=profile.id, title="Vector adapter")
    session.add(course)
    session.flush()
    material = Material(
        profile_id=profile.id,
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
    return (str(material.id), [str(chunk.id) for chunk in chunks])


def basis(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index % DIM] = 1.0
    return vector


def test_adapter_round_trip_search_delete_and_rowid_map(
    db_session: Session, owner: Any
) -> None:
    material_id, chunk_ids = seed_material(db_session, str(owner.id), ["alpha", "beta"])
    store = StudyVectorStore(db_session)
    assert store.content_space() is None

    store.store(chunk_ids, [basis(0), basis(1)], "fake-embed")
    db_session.commit()

    space = store.content_space()
    assert space is not None
    assert space.space_id == CONTENT_SPACE_ID
    assert space.name == CONTENT_SPACE_NAME
    assert space.model == "fake-embed"
    assert space.dim == DIM
    assert space.index_table == index_table_name(CONTENT_SPACE_ID)
    assert space.backend == "sqlite_vec"
    assert space.metadata_row is True
    assert space.key

    assert vectors.table_exists(db_session) is True
    assert vectors.vector_count(db_session) == 2
    health = store.health()
    assert health.ok is True
    assert health.provisioned is True
    assert health.index_table == index_table_name(CONTENT_SPACE_ID)
    assert health.legacy_rows == 2

    documents = store.documents()
    assert len(documents) == 1
    assert documents[0].kind == "material"
    assert documents[0].source_id == material_id

    records = store.records()
    assert len(records) == 2
    assert {record.view for record in records} == {CONTENT_VIEW}
    assert {record.content_hash for record in records} == {
        content_hash("alpha"),
        content_hash("beta"),
    }
    expected_rowids = {vectors.rowid_for(chunk_id) for chunk_id in chunk_ids}
    assert {
        int(record.rowid) for record in records if record.rowid is not None
    } == expected_rowids
    assert store.rowid_map() == {
        vectors.rowid_for(chunk_id): chunk_id for chunk_id in chunk_ids
    }
    assert store.metadata_complete() is True

    hits = store.search(basis(0), limit=2)
    assert hits and hits[0][0] == chunk_ids[0]
    assert [chunk_id for chunk_id, _distance in hits] == chunk_ids

    store.delete_for_extraction([chunk_ids[0]])
    db_session.commit()
    assert vectors.vector_count(db_session) == 1
    assert store.record_count(view=CONTENT_VIEW) == 1
    assert len(store.documents()) == 1

    store.delete_for_extraction([chunk_ids[1]])
    db_session.commit()
    assert vectors.vector_count(db_session) == 0
    assert store.record_count(view=CONTENT_VIEW) == 0
    assert store.documents() == []


def test_model_or_dimension_change_is_an_explicit_handoff_not_a_drop(
    db_session: Session, owner: Any
) -> None:
    _material_id, chunk_ids = seed_material(db_session, str(owner.id), ["alpha", "beta"])
    store = StudyVectorStore(db_session)
    store.store(chunk_ids, [basis(0), basis(1)], "model-a")
    db_session.commit()

    with pytest.raises(vectors.VectorSpaceChangeRequired) as error:
        store.store(chunk_ids[:1], [basis(0)], "model-b")
    assert error.value.current_model == "model-a"
    assert error.value.requested_model == "model-b"
    assert "chunk_vecs was left untouched" in str(error.value)

    assert vectors.table_exists(db_session) is True
    assert vectors.vector_count(db_session) == 2
    assert vectors.read_meta(db_session) == {"dim": str(DIM), "model": "model-a"}
    assert [chunk_id for chunk_id, _ in store.search(basis(0), limit=2)] == chunk_ids

    with pytest.raises(vectors.VectorSpaceChangeRequired) as dimension_error:
        store.store(chunk_ids[:1], [[1.0] * (DIM + 1)], "model-a")
    assert dimension_error.value.requested_dim == DIM + 1
    assert vectors.vector_count(db_session) == 2
    assert len(store.records()) == 2


def test_cold_space_has_no_metadata_row_and_no_fabricated_coverage(
    db_session: Session,
) -> None:
    store = StudyVectorStore(db_session)
    assert store.content_space() is None
    assert db_session.scalars(select(VectorSpace)).all() == []
    assert store.table_exists() is False

    coverage = reads.coverage(db_session)
    assert coverage["cold"] is True
    assert coverage["coverage"]["as_of"] is None
    assert coverage["coverage"]["coverage"] is None


def test_backfill_maps_pre_adapter_vectors_and_fills_content_hashes(
    db_session: Session, owner: Any
) -> None:
    _material_id, chunk_ids = seed_material(db_session, str(owner.id), ["alpha", "beta"])
    vectors.store(db_session, chunk_ids, [basis(0), basis(1)], "fake-embed")
    db_session.commit()

    store = StudyVectorStore(db_session)
    assert store.record_count(view=CONTENT_VIEW) == 0

    result = store.backfill_metadata()
    db_session.commit()
    assert result.scanned == 2
    assert result.records == 2
    assert result.documents == 1
    assert {record.content_hash for record in store.records()} == {
        content_hash("alpha"),
        content_hash("beta"),
    }

    second = store.backfill_metadata()
    assert (second.scanned, second.records, second.documents) == (2, 2, 1)
    assert len(store.records()) == 2

