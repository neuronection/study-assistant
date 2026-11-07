"""Study's family vector backends and physical provisioning (plan 51 Q3c2a).

These tests run on the desktop SQLite/sqlite-vec pair: the provisioned
``vec_<8hex>`` table, the rowid map, scope enforcement, the exact/linear
parity contract, the v1 backfill/fallback path and truthful health.
The PostgreSQL twin lives in ``test_vector_backends_postgres.py``.
"""

from __future__ import annotations

import uuid
from array import array
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain.models import (
    Chunk,
    Course,
    Extraction,
    Material,
    Profile,
    VectorDocument,
    VectorRecord,
    VectorSpace,
)
from app.storage import vectors
from app.storage.vector_backends import (
    LinearBackend,
    SqliteVecBackend,
    VectorIndexMissing,
    document_scope,
    filter_scope,
)
from app.storage.vector_backends import rowid_for as backend_rowid_for
from app.storage.vector_contract import VectorSpace as ContractSpace
from app.storage.vector_provisioning import provision_space, space_status
from app.storage.vector_schema import index_table_name
from app.storage.vector_store import (
    CONTENT_SPACE_ID,
    CONTENT_VIEW,
    StudyVectorStore,
)

DIM = 4


def seed_material(
    session: Session, owner_id: str, texts: list[str], *, title: str = "Notes"
) -> tuple[str, str, list[str]]:
    profile = session.scalars(select(Profile).where(Profile.user_id == owner_id)).first()
    if profile is None:
        profile = Profile(user_id=owner_id, name="Default", is_default=True)
        session.add(profile)
        session.flush()
    course = Course(profile_id=profile.id, title=f"Vector {title}")
    session.add(course)
    session.flush()
    material = Material(
        profile_id=profile.id,
        course_id=course.id,
        kind="md",
        title=title,
        filename=f"{uuid.uuid4().hex[:8]}.md",
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
        Chunk(extraction_id=extraction.id, ordinal=index, text=chunk_text)
        for index, chunk_text in enumerate(texts)
    ]
    session.add_all(chunks)
    session.commit()
    return (str(profile.id), str(material.id), [str(chunk.id) for chunk in chunks])


def basis(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index % DIM] = 1.0
    return vector


def _space(store: StudyVectorStore) -> ContractSpace:
    space = store.content_space()
    assert space is not None
    return space.as_contract()


def _seed_linear_space(
    session: Session,
    *,
    materials: list[tuple[str, str | None, list[list[float]]]],
) -> ContractSpace:
    """A second, explicitly linear space holding the same vectors.

    Its records get deterministic ids and a NULL rowid; the linear backend
    scans ``vector_records.embedding`` only. Used for the exact-scan parity
    assertion against sqlite-vec.
    """
    namespace = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    session.add(
        VectorSpace(
            id="linear-parity",
            name="parity",
            provider="test",
            model="fake-embed",
            dim=DIM,
            index_table=None,
            status="active",
        )
    )
    session.flush()
    for material_id, profile_id, vectors_batch in materials:
        document_id = str(uuid.uuid5(namespace, material_id))
        session.add(
            VectorDocument(
                id=document_id,
                space_id="linear-parity",
                kind="material",
                source_id=material_id,
                profile_id=profile_id,
                source_hash="",
                schema_version=0,
            )
        )
        session.flush()
        for index, vector in enumerate(vectors_batch):
            session.add(
                VectorRecord(
                    id=str(uuid.uuid5(namespace, f"{material_id}:{index}")),
                    document_id=document_id,
                    space_id="linear-parity",
                    view=CONTENT_VIEW,
                    chunk_index=index,
                    rowid=None,
                    content_hash="",
                    embedding=array("f", vector).tobytes(),
                )
            )
    session.flush()
    return ContractSpace(
        name="parity",
        provider="test",
        model="fake-embed",
        dim=DIM,
        space_id="linear-parity",
        index_table=None,
    )


def test_sqlite_vec_and_linear_agree_on_top_k_and_scope(db_session: Session, owner: Any) -> None:
    profile_id, material_a, chunks_a = seed_material(db_session, str(owner.id), ["a0", "a1"])
    _profile_b, material_b, chunks_b = seed_material(
        db_session, str(owner.id), ["b0", "b1"], title="Other"
    )
    store = StudyVectorStore(db_session)
    all_chunks = [*chunks_a, *chunks_b]
    vectors_batch = [basis(0), basis(1), basis(2), basis(3)]
    store.store(all_chunks, vectors_batch, "fake-embed")
    db_session.commit()

    sqlite_space = _space(store)
    json_space = _seed_linear_space(
        db_session,
        materials=[
            (material_a, profile_id, vectors_batch[:2]),
            (material_b, profile_id, vectors_batch[2:]),
        ],
    )
    db_session.commit()
    sqlite_backend = SqliteVecBackend(db_session)
    linear_backend = LinearBackend(db_session)

    def sources(space_id: str) -> dict[str, str]:
        return {
            str(document.id): str(document.source_id)
            for document in db_session.scalars(
                select(VectorDocument).where(VectorDocument.space_id == space_id)
            )
        }

    content_sources = sources(CONTENT_SPACE_ID)
    parity_sources = sources("linear-parity")

    for query in (basis(0), basis(1), basis(2), basis(3)):
        sqlite_hits = sqlite_backend.search(
            sqlite_space, query, views=(CONTENT_VIEW,), scope=document_scope([]), limit=4
        )
        assert sqlite_hits == []
        sqlite_hits = sqlite_backend.search(
            sqlite_space,
            query,
            views=(CONTENT_VIEW,),
            scope=filter_scope(source_ids=[material_a, material_b]),
            limit=4,
        )
        linear_hits = linear_backend.search(
            json_space,
            query,
            views=(CONTENT_VIEW,),
            scope=filter_scope(source_ids=[material_a, material_b]),
            limit=4,
        )
        sqlite_pairs = sorted(
            ((content_sources[hit.document_id], round(hit.distance, 6)) for hit in sqlite_hits),
            key=lambda item: (-item[1], item[0]),
        )
        linear_pairs = sorted(
            ((parity_sources[hit.document_id], round(hit.distance, 6)) for hit in linear_hits),
            key=lambda item: (-item[1], item[0]),
        )
        assert sqlite_pairs == linear_pairs
        assert sorted(hit.distance for hit in sqlite_hits) == pytest.approx(
            sorted(hit.distance for hit in linear_hits), abs=1e-6
        )

    scoped = sqlite_backend.search(
        sqlite_space,
        basis(2),
        views=(CONTENT_VIEW,),
        scope=filter_scope(source_ids=[material_a]),
        limit=4,
    )
    assert {hit.document_id for hit in scoped} == {
        document.id
        for document in db_session.scalars(
            select(VectorDocument).where(VectorDocument.space_id == CONTENT_SPACE_ID)
        )
        if str(document.source_id) == material_a
    }
    assert len(scoped) == len(chunks_a)

    by_profile = sqlite_backend.search(
        sqlite_space,
        basis(0),
        views=(CONTENT_VIEW,),
        scope=filter_scope(profile_ids=[profile_id]),
        limit=4,
    )
    assert len(by_profile) == len(all_chunks)


def test_rowid_map_matches_metadata_and_v1_reverse_map(db_session: Session, owner: Any) -> None:
    _profile, _material, chunk_ids = seed_material(db_session, str(owner.id), ["a", "b"])
    store = StudyVectorStore(db_session)
    store.store(chunk_ids, [basis(0), basis(1)], "fake-embed")
    db_session.commit()

    expected = {vectors.rowid_for(chunk_id): chunk_id for chunk_id in chunk_ids}
    assert all(backend_rowid_for(chunk_id) == vectors.rowid_for(chunk_id) for chunk_id in chunk_ids)
    assert store.stored_chunk_ids() == expected
    assert store.rowid_map() == expected
    assert {
        (int(record.rowid or 0), str(record.id))
        for record in db_session.scalars(
            select(VectorRecord).where(VectorRecord.space_id == CONTENT_SPACE_ID)
        )
    } == set(expected.items())


def test_provisioning_is_idempotent_and_keeps_the_v1_store(db_session: Session, owner: Any) -> None:
    _profile, _material, chunk_ids = seed_material(db_session, str(owner.id), ["a", "b"])
    store = StudyVectorStore(db_session)
    store.store(chunk_ids, [basis(0), basis(1)], "fake-embed")
    db_session.commit()

    physical = index_table_name(CONTENT_SPACE_ID)
    assert store.index_table == physical
    assert (
        db_session.scalar(
            text("SELECT count(*) FROM vector_spaces WHERE index_table = :table"),
            {"table": physical},
        )
        == 1
    )
    assert vectors.vector_count(db_session) == 2

    second = provision_space(db_session, CONTENT_SPACE_ID)
    assert second.index_table == physical
    assert second.created is False
    status = space_status(db_session, CONTENT_SPACE_ID)
    assert status.table_exists is True
    assert status.table_dim == DIM
    assert status.row_count == 2
    assert status.backend == "sqlite_vec"
    assert status.index_present is True

    assert store.health().ok is True
    assert store.health().provisioned is True
    assert store.health().records == 2
    assert store.health().v1_rows == 2


def test_v1_backfill_moves_vectors_and_search_stays_available(
    db_session: Session, owner: Any
) -> None:
    _profile, _material, chunk_ids = seed_material(db_session, str(owner.id), ["a", "b"])
    vectors.store(db_session, chunk_ids, [basis(0), basis(1)], "fake-embed")
    db_session.commit()
    assert db_session.scalar(text("SELECT count(*) FROM vector_spaces")) == 0

    store = StudyVectorStore(db_session)
    result = store.provision()
    assert result is not None
    assert result.index_table == index_table_name(CONTENT_SPACE_ID)
    db_session.commit()

    assert store.record_count(view=CONTENT_VIEW) == 2
    assert store.metadata_complete() is True
    assert vectors.vector_count(db_session) == 2
    assert store.search(basis(0), limit=2)[0][0] == chunk_ids[0]

    again = store.backfill_physical()
    assert again == 2
    assert db_session.scalar(text(f"SELECT count(*) FROM {result.index_table}")) == 2


def test_search_falls_back_to_the_v1_store_when_the_vec_table_is_missing(
    db_session: Session, owner: Any
) -> None:
    _profile, _material, chunk_ids = seed_material(db_session, str(owner.id), ["a", "b"])
    store = StudyVectorStore(db_session)
    store.store(chunk_ids, [basis(0), basis(1)], "fake-embed")
    db_session.commit()
    physical = index_table_name(CONTENT_SPACE_ID)

    db_session.execute(text(f"DROP TABLE {physical}"))
    db_session.commit()

    assert store.health().ok is False
    assert store.health().provisioned is True
    hits = store.search(basis(0), limit=2)
    assert [chunk_id for chunk_id, _distance in hits] == chunk_ids


def test_health_reports_a_partial_backfill_without_faking_coverage(
    db_session: Session, owner: Any
) -> None:
    _profile, _material, chunk_ids = seed_material(db_session, str(owner.id), ["a", "b"])
    store = StudyVectorStore(db_session)
    store.store(chunk_ids, [basis(0), basis(1)], "fake-embed")
    db_session.commit()
    physical = index_table_name(CONTENT_SPACE_ID)
    db_session.execute(
        text(f"DELETE FROM {physical} WHERE record_rowid = :rowid"),
        {"rowid": vectors.rowid_for(chunk_ids[0])},
    )
    db_session.commit()

    health = store.health()
    assert health.ok is True
    assert health.records == 1
    assert "partial" in health.detail


def test_sqlite_backend_raises_when_the_index_table_is_missing(
    db_session: Session, owner: Any
) -> None:
    _profile, _material, chunk_ids = seed_material(db_session, str(owner.id), ["a"])
    store = StudyVectorStore(db_session)
    store.store(chunk_ids, [basis(0)], "fake-embed")
    db_session.commit()
    space = _space(store)

    db_session.execute(text(f"DROP TABLE {index_table_name(CONTENT_SPACE_ID)}"))
    db_session.commit()
    with pytest.raises(VectorIndexMissing):
        SqliteVecBackend(db_session).search(
            space,
            basis(0),
            views=(CONTENT_VIEW,),
            scope=document_scope([]),
            limit=1,
        )


def test_factory_degrades_to_linear_without_vec0(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.storage.vector_backends as backends

    monkeypatch.setattr(backends, "sqlite_vec_available", lambda session: False)
    backend = backends.choose_backend(db_session)
    assert isinstance(backend, LinearBackend)
    assert backend.capabilities.ann is False

    monkeypatch.setattr(backends, "sqlite_vec_available", lambda session: True)
    assert isinstance(backends.choose_backend(db_session), SqliteVecBackend)


def test_provisioning_defers_to_the_v1_store_when_vec0_cannot_load(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.storage.vector_provisioning as provisioning

    monkeypatch.setattr(provisioning, "_sqlite_load_vec", lambda session: False)
    _profile, _material, chunk_ids = seed_material(db_session, str(owner.id), ["a", "b"])
    store = StudyVectorStore(db_session)
    store.store(chunk_ids, [basis(0), basis(1)], "fake-embed")
    db_session.commit()

    space = store.content_space()
    assert space is not None
    assert space.index_table == vectors.VEC_TABLE
    assert store.health().provisioned is False
    assert store.health().ok is True
    assert [chunk_id for chunk_id, _ in store.search(basis(0), limit=2)] == chunk_ids
    assert vectors.vector_count(db_session) == 2
