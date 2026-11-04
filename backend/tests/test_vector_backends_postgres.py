"""PostgreSQL twin of the family vector backends (plan 51 Q3c2a).

Skipped unless ``SA_TEST_DATABASE_URL`` points at a disposable PostgreSQL
server. A migrated template database is created once per module; each test
clones it (``CREATE DATABASE ... TEMPLATE``) and drops it afterwards, so the
pgvector HNSW table, extension and metadata stay isolated per test.
"""

from __future__ import annotations

import os
import socket
import tempfile
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from alembic.config import Config
from filelock import FileLock
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app.domain.models import (
    Chunk,
    Course,
    Extraction,
    Material,
    Profile,
    User,
    VectorDocument,
    VectorRecord,
    VectorSpace,
)
from app.storage import vectors
from app.storage.vector_backends import (
    LinearBackend,
    PgVectorBackend,
    document_scope,
    filter_scope,
)
from app.storage.vector_contract import VectorSpace as ContractSpace
from app.storage.vector_provisioning import provision_space, space_status
from app.storage.vector_schema import index_table_name
from app.storage.vector_store import CONTENT_SPACE_ID, CONTENT_VIEW, StudyVectorStore

# gate-allow: DATABASE_URL (module local; the env read is SA_TEST_DATABASE_URL)
DATABASE_URL = os.environ.get("SA_TEST_DATABASE_URL", "")

if not DATABASE_URL:
    pytest.skip(
        "SA_TEST_DATABASE_URL is not set — the PostgreSQL vector-backend twin needs "
        "a disposable server",
        allow_module_level=True,
    )

DIM = 4
_MIGRATION_LOCK = FileLock(os.path.join(tempfile.gettempdir(), "sa-vector-pg-migrations.lock"))


@pytest.fixture(scope="module", autouse=True)
def _loopback_sockets() -> Iterator[None]:
    """Restore the real socket connect used by the PostgreSQL client."""
    saved: dict[str, Any] = {
        name: socket.socket.__dict__.get(name) for name in ("connect", "connect_ex")
    }
    for name, original in saved.items():
        if original is not None:
            delattr(socket.socket, name)
    try:
        yield
    finally:
        for name, original in saved.items():
            if original is not None:
                setattr(socket.socket, name, original)


def _admin(url: str) -> Engine:
    return create_engine(make_url(url).set(database="postgres"), poolclass=NullPool)


def _drop(engine: Engine, name: str) -> None:
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(scope="module")
def template_url(_loopback_sockets: None) -> Iterator[str]:
    """One migrated database that every test clones from."""
    base = make_url(DATABASE_URL)
    name = f"{base.database or 'postgres'}_vectpl_{uuid.uuid4().hex[:8]}"
    template = base.set(database=name)
    admin = _admin(DATABASE_URL)
    try:
        with _MIGRATION_LOCK:
            with admin.connect() as connection:
                connection = connection.execution_options(isolation_level="AUTOCOMMIT")
                connection.execute(text(f'CREATE DATABASE "{name}"'))
            config = Config("alembic.ini")
            config.set_main_option(
                "sqlalchemy.url", template.render_as_string(hide_password=False)
            )
            command.upgrade(config, "head")
        yield template.render_as_string(hide_password=False)
    finally:
        _drop(admin, name)
        admin.dispose()


@pytest.fixture
def pg_engine(template_url: str, _loopback_sockets: None) -> Iterator[Engine]:
    base = make_url(template_url)
    name = f"{base.database}_t_{uuid.uuid4().hex[:8]}"
    admin = _admin(template_url)
    with admin.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{base.database}"'))
    engine = create_engine(base.set(database=name), poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()
        _drop(admin, name)
        admin.dispose()


@pytest.fixture
def pg_session(pg_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    with factory() as session:
        yield session


def _scalar(engine: Engine, statement: str, params: dict[str, Any] | None = None) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(statement), params or {}).scalar()


def basis(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index % DIM] = 1.0
    return vector


def seed_material(
    session: Session, texts: list[str], *, title: str = "Notes"
) -> tuple[str, str, str, list[str]]:
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.local", password_hash=None)
    session.add(user)
    session.flush()
    profile = Profile(user_id=user.id, name="Default", is_default=True)
    session.add(profile)
    session.flush()
    course = Course(profile_id=profile.id, title=f"PG vector {title}")
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
    return (
        str(profile.id),
        str(course.id),
        str(material.id),
        [str(chunk.id) for chunk in chunks],
    )


def _sources(session: Session, space_id: str) -> dict[str, str]:
    return {
        str(document.id): str(document.source_id)
        for document in session.scalars(
            select(VectorDocument).where(VectorDocument.space_id == space_id)
        )
    }


def _seed_linear_space(
    session: Session,
    materials: list[tuple[str, str | None, list[list[float]]]],
) -> ContractSpace:
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
    from array import array

    namespace = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
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


def test_pg_provisions_hnsw_and_filters_scope_before_the_scan(
    pg_engine: Engine, pg_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _profile, _course_id, material_a, chunks_a = seed_material(
        pg_session, ["a0", "a1"], title="A"
    )
    _profile_b, _course_b, material_b, chunks_b = seed_material(
        pg_session, ["b0", "b1"], title="B"
    )
    store = StudyVectorStore(pg_session)
    store.store([*chunks_a, *chunks_b], [basis(0), basis(1), basis(2), basis(3)], "fake-embed")
    pg_session.commit()

    space = store.content_space()
    assert space is not None
    physical = index_table_name(CONTENT_SPACE_ID)
    assert physical == "vec_dfbcce9b"
    assert space.index_table == physical
    assert _scalar(pg_engine, "SELECT to_regclass(:name)", {"name": physical}) == physical
    assert (
        _scalar(
            pg_engine,
            "SELECT 1 FROM pg_indexes WHERE tablename = :table AND indexname = :index",
            {"table": physical, "index": f"ix_{physical}_hnsw"},
        )
        == 1
    )
    status = space_status(pg_session, CONTENT_SPACE_ID)
    assert status.backend == "pgvector"
    assert status.table_dim == DIM
    assert status.table_exists is True
    assert status.index_present is True
    assert status.row_count == 4

    health = store.health()
    assert health.ok is True
    assert health.provisioned is True
    assert health.records == 4

    backend = PgVectorBackend(pg_session)
    scoped = backend.search(
        space.as_contract(),
        basis(2),
        views=(CONTENT_VIEW,),
        scope=filter_scope(source_ids=[material_a]),
        limit=4,
    )
    assert {hit.record_id for hit in scoped} == set(chunks_a)
    assert {_sources(pg_session, CONTENT_SPACE_ID)[hit.document_id] for hit in scoped} == {
        material_a
    }

    unknown_profile = backend.search(
        space.as_contract(),
        basis(0),
        views=(CONTENT_VIEW,),
        scope=filter_scope(profile_ids=["00000000-0000-0000-0000-000000000000"]),
        limit=4,
    )
    assert unknown_profile == []

    every = backend.search(
        space.as_contract(),
        basis(0),
        views=(CONTENT_VIEW,),
        scope=document_scope([]),
        limit=4,
    )
    assert every == []

    # The same corpus through the exact and the ANN branch must agree on the
    # scoped top hit (the threshold is the only switch between them).
    import app.storage.vector_backends as backends

    exact_hits = backend.search(
        space.as_contract(),
        basis(0),
        views=(CONTENT_VIEW,),
        scope=filter_scope(source_ids=[material_a, material_b]),
        limit=4,
    )
    assert exact_hits[0].record_id == chunks_a[0]
    monkeypatch.setattr(backends, "EXACT_SCAN_THRESHOLD", 1)
    ann_hits = backend.search(
        space.as_contract(),
        basis(0),
        views=(CONTENT_VIEW,),
        scope=filter_scope(source_ids=[material_a, material_b]),
        limit=4,
    )
    assert ann_hits[0].record_id == exact_hits[0].record_id
    assert {hit.record_id for hit in ann_hits} == {hit.record_id for hit in exact_hits}

    # The course scope resolves to its materials before the ANN scan.
    by_course = backend.search(
        space.as_contract(),
        basis(0),
        views=(CONTENT_VIEW,),
        scope=document_scope(
            [
                document.id
                for document in pg_session.scalars(
                    select(VectorDocument).where(VectorDocument.space_id == CONTENT_SPACE_ID)
                )
                if str(document.source_id) == material_b
            ]
        ),
        limit=4,
    )
    assert {hit.record_id for hit in by_course} == set(chunks_b)


def test_pg_pgvector_and_linear_agree_on_top_k(pg_session: Session) -> None:
    profile_id, _course_id, material_a, chunks_a = seed_material(pg_session, ["a0", "a1"])
    _profile_b, _course_b, material_b, chunks_b = seed_material(
        pg_session, ["b0", "b1"], title="B"
    )
    store = StudyVectorStore(pg_session)
    vectors_batch = [basis(0), basis(1), basis(2), basis(3)]
    store.store([*chunks_a, *chunks_b], vectors_batch, "fake-embed")
    pg_session.commit()
    space = store.content_space()
    assert space is not None

    linear_space = _seed_linear_space(
        pg_session,
        materials=[
            (material_a, profile_id, vectors_batch[:2]),
            (material_b, profile_id, vectors_batch[2:]),
        ],
    )
    pg_session.commit()
    pg = PgVectorBackend(pg_session)
    linear = LinearBackend(pg_session)
    content_sources = _sources(pg_session, CONTENT_SPACE_ID)
    parity_sources = _sources(pg_session, "linear-parity")

    for query in (basis(0), basis(1), basis(2), basis(3)):
        scope = filter_scope(source_ids=[material_a, material_b])
        pg_hits = pg.search(
            space.as_contract(), query, views=(CONTENT_VIEW,), scope=scope, limit=4
        )
        linear_hits = linear.search(
            linear_space, query, views=(CONTENT_VIEW,), scope=scope, limit=4
        )
        pg_pairs = sorted(
            (
                (content_sources[hit.document_id], round(hit.distance, 6))
                for hit in pg_hits
            ),
            key=lambda item: (-item[1], item[0]),
        )
        linear_pairs = sorted(
            (
                (parity_sources[hit.document_id], round(hit.distance, 6))
                for hit in linear_hits
            ),
            key=lambda item: (-item[1], item[0]),
        )
        assert pg_pairs == linear_pairs
        assert sorted(hit.distance for hit in pg_hits) == pytest.approx(
            sorted(hit.distance for hit in linear_hits), abs=1e-6
        )


def test_pg_search_falls_back_to_the_legacy_store_when_the_vec_table_is_missing(
    pg_session: Session,
) -> None:
    _profile, _course, _material, chunk_ids = seed_material(pg_session, ["a", "b"])
    store = StudyVectorStore(pg_session)
    store.store(chunk_ids, [basis(0), basis(1)], "fake-embed")
    pg_session.commit()
    physical = index_table_name(CONTENT_SPACE_ID)

    pg_session.execute(text(f"DROP TABLE {physical}"))
    pg_session.commit()
    assert store.health().ok is False
    assert [chunk_id for chunk_id, _ in store.search(basis(0), limit=2)] == chunk_ids


def test_pg_provisioning_is_idempotent_and_keeps_chunk_vecs_like_sqlite(
    pg_session: Session,
) -> None:
    _profile, _course, _material, chunk_ids = seed_material(pg_session, ["a", "b"])
    store = StudyVectorStore(pg_session)
    store.store(chunk_ids, [basis(0), basis(1)], "fake-embed")
    pg_session.commit()

    again = provision_space(pg_session, CONTENT_SPACE_ID)
    pg_session.commit()
    assert again.created is False
    assert again.index_table == index_table_name(CONTENT_SPACE_ID)
    assert vectors.vector_count(pg_session) == 2
    assert store.stored_chunk_ids() == {
        vectors.rowid_for(chunk_id): chunk_id for chunk_id in chunk_ids
    }
    assert store.health().legacy_rows == 2
