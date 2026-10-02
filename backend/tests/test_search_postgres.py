"""PostgreSQL twin of the search stack (ADR-0022 S3 dialect twins).

Skipped unless ``SA_TEST_DATABASE_URL`` points at a disposable PostgreSQL
server. A scratch database is created on that server, migrated to head, and
dropped again afterwards — the caller's database is never touched. Mirrors
``tests/test_search_fuzzy.py`` behaviour through the same search API, seeded
via the ORM plus ``sync_material_fts`` / ``vectors.store``.
"""

import os
import socket
import tempfile
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from alembic.config import Config
from filelock import FileLock
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app.domain.models import Chunk, Course, Extraction, Material, Profile, User
from app.services.search import hybrid_search, retrieve_chunks
from app.storage import vectors
from app.storage.fts import sync_material_fts

DATABASE_URL = os.environ.get("SA_TEST_DATABASE_URL", "")  # gate-allow: DATABASE_URL (module local; the env read is SA_TEST_DATABASE_URL)

if not DATABASE_URL:
    pytest.skip(
        "SA_TEST_DATABASE_URL is not set — the PostgreSQL search twin "
        "needs a disposable server",
        allow_module_level=True,
    )

EMBED_MODEL = "test-embed"
EMBED_DIM = 8

# xdist workers each build their own scratch database; the full Alembic
# chain must not run concurrently on the server or it exhausts PostgreSQL's
# lock table (max_locks_per_transaction).
_MIGRATION_LOCK = FileLock(
    os.path.join(tempfile.gettempdir(), "sa-search-pg-migrations.lock")
)


@pytest.fixture(scope="module", autouse=True)
def _loopback_sockets() -> Iterator[None]:
    """conftest's session-wide network guard shadows ``socket.socket.connect``
    with a deny function; talking to the PostgreSQL server needs the real
    one back. Restore the guard afterwards so other modules keep it."""
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


@pytest.fixture(scope="module")
def pg_factory(_loopback_sockets: None) -> Iterator[sessionmaker[Session]]:
    """A migrated scratch database on the same server; yields a factory."""
    base = make_url(DATABASE_URL)
    scratch = f"{base.database or 'postgres'}_searchtest_{uuid.uuid4().hex[:8]}"
    scratch_url = base.set(database=scratch)
    maintenance = create_engine(base.set(database="postgres"), poolclass=NullPool)
    engine = create_engine(scratch_url, poolclass=NullPool)
    try:
        with _MIGRATION_LOCK:
            with maintenance.connect() as conn:
                conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text(f'CREATE DATABASE "{scratch}"'))
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option(
                "sqlalchemy.url", scratch_url.render_as_string(hide_password=False)
            )
            command.upgrade(alembic_cfg, "head")
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with maintenance.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        maintenance.dispose()


@pytest.fixture
def pg_session(pg_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session whose seeded corpus is rolled back after the test."""
    session = pg_factory()
    session.begin_nested()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _no_embed(query: str) -> tuple[str, list[list[float]]] | None:
    return None


def _basis(index: int) -> list[float]:
    vec = [0.0] * EMBED_DIM
    vec[index % EMBED_DIM] = 1.0
    return vec


def _user_profile(session: Session) -> Profile:
    user = User(id=str(uuid.uuid4()), email="search@test.local", password_hash=None)
    session.add(user)
    session.flush()
    profile = Profile(user_id=user.id, name="p")
    session.add(profile)
    session.flush()
    return profile


def _material(
    session: Session,
    profile: Profile,
    course: Course,
    title: str,
    markdown: str,
    chunks: tuple[str, ...] = (),
) -> tuple[Material, list[Chunk]]:
    material = Material(
        profile_id=profile.id,
        course_id=course.id,
        kind="pdf",
        title=title,
        filename=f"{uuid.uuid4().hex[:8]}.pdf",
        status="ready",
    )
    session.add(material)
    session.flush()
    extraction = Extraction(
        material_id=material.id, extractor="test", markdown=markdown, blocks=[]
    )
    session.add(extraction)
    session.flush()
    chunk_rows = [
        Chunk(extraction_id=extraction.id, ordinal=ordinal, text=chunk_text)
        for ordinal, chunk_text in enumerate(chunks)
    ]
    session.add_all(chunk_rows)
    session.flush()
    sync_material_fts(session, material, markdown)
    return material, chunk_rows


def _hit_ids(session: Session, query: str, course_id: int | None = None) -> list[int]:
    hits = hybrid_search(session, query, 20, _no_embed, course_id)
    return [int(hit["material_id"]) for hit in hits]


def test_exact_phrase_hit(pg_session: Session) -> None:
    profile = _user_profile(pg_session)
    course = Course(profile_id=profile.id, title="Calculus")
    pg_session.add(course)
    pg_session.flush()
    material, _ = _material(
        pg_session,
        profile,
        course,
        "Integration by Parts",
        "Integration by parts moves the derivative onto one factor.",
    )
    assert _hit_ids(pg_session, "Integration by Parts")[0] == material.id


def test_or_terms_hits(pg_session: Session) -> None:
    profile = _user_profile(pg_session)
    course = Course(profile_id=profile.id, title="Calculus")
    pg_session.add(course)
    pg_session.flush()
    derivatives, _ = _material(
        pg_session,
        profile,
        course,
        "Derivatives",
        "The derivative of a function measures rates of change.",
        ("the derivative of a function",),
    )
    factors, _ = _material(
        pg_session,
        profile,
        course,
        "Factoring",
        "Products and terms expose one factor here.",
        ("one factor remains here",),
    )
    rows = retrieve_chunks(pg_session, "derivative factor", _no_embed, limit=5)
    material_ids = {int(row["material_id"]) for row in rows}
    assert material_ids == {derivatives.id, factors.id}


def test_prefix_hit(pg_session: Session) -> None:
    profile = _user_profile(pg_session)
    course = Course(profile_id=profile.id, title="Calculus")
    pg_session.add(course)
    pg_session.flush()
    material, _ = _material(
        pg_session,
        profile,
        course,
        "Integration by Parts",
        "Integration by parts moves the derivative onto one factor.",
    )
    assert material.id in _hit_ids(pg_session, "integ")


def test_misspelled_title_found_via_trigram(pg_session: Session) -> None:
    profile = _user_profile(pg_session)
    course = Course(profile_id=profile.id, title="Calculus")
    pg_session.add(course)
    pg_session.flush()
    material, _ = _material(
        pg_session,
        profile,
        course,
        "Integration by Parts",
        "The formula for integration.",
    )
    _material(pg_session, profile, course, "Thermodynamics", "Entropy and energy.")
    assert material.id in _hit_ids(pg_session, "integraton by parts")


def test_course_scoping(pg_session: Session) -> None:
    profile = _user_profile(pg_session)
    course_a = Course(profile_id=profile.id, title="A")
    course_b = Course(profile_id=profile.id, title="B")
    pg_session.add_all([course_a, course_b])
    pg_session.flush()
    material_a, _ = _material(
        pg_session,
        profile,
        course_a,
        "Integration by Parts",
        "The formula for integration.",
    )
    material_b, _ = _material(
        pg_session,
        profile,
        course_b,
        "Integration by Parts",
        "The formula for integration.",
    )
    assert _hit_ids(pg_session, "integraton by parts", course_id=course_a.id) == [material_a.id]
    assert _hit_ids(pg_session, "integraton by parts", course_id=course_b.id) == [material_b.id]


def test_exact_outranks_fuzzy(pg_session: Session) -> None:
    profile = _user_profile(pg_session)
    course = Course(profile_id=profile.id, title="Calculus")
    pg_session.add(course)
    pg_session.flush()
    exact, _ = _material(
        pg_session,
        profile,
        course,
        "Limits",
        "Limits describe the behavior of functions.",
    )
    _material(pg_session, profile, course, "Thermodynamics", "Entropy and energy.")
    assert _hit_ids(pg_session, "limits")[0] == exact.id


def test_chunk_fuzzy_fallback(pg_session: Session) -> None:
    profile = _user_profile(pg_session)
    course = Course(profile_id=profile.id, title="C")
    pg_session.add(course)
    pg_session.flush()
    chunk_text = "integration by parts moves the derivative onto one factor"
    _material(pg_session, profile, course, "Integration", chunk_text, (chunk_text,))
    exact = retrieve_chunks(pg_session, "derivative", _no_embed, limit=5)
    assert [row["text"] for row in exact]
    fuzzy = retrieve_chunks(pg_session, "derivatve", _no_embed, limit=5)
    assert fuzzy == exact
    assert retrieve_chunks(pg_session, "xylophone", _no_embed, limit=5) == []


def test_vector_knn_returns_nearest_chunk(pg_session: Session) -> None:
    profile = _user_profile(pg_session)
    course = Course(profile_id=profile.id, title="Calculus")
    pg_session.add(course)
    pg_session.flush()
    chunk_ids: list[int] = []
    for index in range(3):
        _created, chunks = _material(
            pg_session, profile, course, f"Material {index}", f"Body {index}", (f"chunk {index}",)
        )
        chunk_ids.extend(int(chunk.id) for chunk in chunks)
    vectors.store(pg_session, chunk_ids, [_basis(i) for i in range(3)], EMBED_MODEL)
    hits = vectors.search(pg_session, _basis(1), limit=3)
    assert hits[0][0] == chunk_ids[1]
    assert hits[0][1] == pytest.approx(0.0, abs=1e-6)
    assert {chunk_id for chunk_id, _distance in hits} == set(chunk_ids)
