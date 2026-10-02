"""Cross-dialect parity gate for the search stack (ADR-0022 plan §9).

One fixed corpus and one fixed query set run through the same search API
(``hybrid_search``) on both dialects — a fresh SQLite database versus a
scratch PostgreSQL database migrated to head. Prints a compact benchmark
table and asserts the parity contract: non-empty queries return non-empty on
both dialects, exact/phrase queries agree on the top hit, and the top-5
overlap is non-empty for at least 80% of the queries.

Skipped unless ``SA_TEST_DATABASE_URL`` points at a disposable PostgreSQL
server (the SQLite half alone cannot demonstrate parity).
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
from app.domain.models import Course, Material, Profile, User
from app.services.search import hybrid_search
from app.storage.fts import sync_material_fts

# gate-allow: DATABASE_URL (module local; the env read is SA_TEST_DATABASE_URL)
DATABASE_URL = os.environ.get("SA_TEST_DATABASE_URL", "")

if not DATABASE_URL:
    pytest.skip(
        "SA_TEST_DATABASE_URL is not set — the search parity gate needs "
        "a disposable PostgreSQL server",
        allow_module_level=True,
    )

CORPUS: list[tuple[str, str]] = [
    ("Integration by Parts", "Integration by parts moves the derivative onto one factor."),
    ("Limits and Continuity", "Limits describe the behavior of functions near a point."),
    ("Wahrscheinlichkeit", "Wahrscheinlichkeit und Statistik beschreiben Zufall und Daten."),
    ("Ελληνικα Μαθηματικα", "μαθηματικα και πιθανοτητες στο μαθημα των αριθμων."),
    ("Thermodynamik", "Entropie und Energie in thermodynamischen Systemen."),
    ("Substitution", "Integration by parts and substitution both simplify integrals."),
]

QUERIES: list[tuple[str, str]] = [
    ("exact", "integration by parts"),
    ("phrase", "behavior of functions"),
    ("prefix", "integ"),
    ("misspelled", "integraton by parts"),
    ("greek", "μαθηματικα"),
    ("german", "Wahrscheinlichkeit"),
    ("empty", "xylophone"),
]

TOP_HIT_KINDS = ("exact", "phrase")
LIMIT = 5

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
    scratch = f"{base.database or 'postgres'}_paritytest_{uuid.uuid4().hex[:8]}"
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


def _seed_corpus(session: Session) -> dict[str, int]:
    """Seed the fixed parity corpus; returns {title: material_id} in order."""
    user = User(id=str(uuid.uuid4()), email="parity@test.local", password_hash=None)
    session.add(user)
    session.flush()
    profile = Profile(user_id=user.id, name="parity")
    session.add(profile)
    session.flush()
    course = Course(profile_id=profile.id, title="Parity")
    session.add(course)
    session.flush()
    ids: dict[str, int] = {}
    for title, markdown in CORPUS:
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
        sync_material_fts(session, material, markdown)
        ids[title] = int(material.id)
    session.flush()
    return ids


def _hit_ids(session: Session, query: str) -> list[int]:
    hits = hybrid_search(session, query, LIMIT, _no_embed)
    return [int(hit["material_id"]) for hit in hits[:LIMIT]]


def test_search_parity_benchmark(db_session: Session, pg_session: Session) -> None:
    sqlite_ids = _seed_corpus(db_session)
    pg_ids = _seed_corpus(pg_session)
    assert list(sqlite_ids.values()) == list(pg_ids.values()), (
        "id spaces must be aligned on fresh databases for the id comparison"
    )

    rows: list[tuple[str, str, list[int], list[int], list[int]]] = []
    for kind, query in QUERIES:
        sqlite_hits = _hit_ids(db_session, query)
        pg_hits = _hit_ids(pg_session, query)
        overlap = sorted(set(sqlite_hits) & set(pg_hits))
        rows.append((kind, query, sqlite_hits, pg_hits, overlap))

    print("\nsearch parity benchmark (hybrid_search, limit=5)")
    print(f"{'kind':<11} {'query':<24} {'sqlite hits':<14} {'pg hits':<14} overlap")
    for kind, query, sqlite_hits, pg_hits, overlap in rows:
        print(
            f"{kind:<11} {query:<24} {sqlite_hits!s:<14} {pg_hits!s:<14} {overlap}"
        )

    for kind, query, sqlite_hits, pg_hits, _overlap in rows:
        if kind == "empty":
            assert sqlite_hits == [] and pg_hits == [], (
                f"empty-result query {query!r} must miss on both dialects"
            )
            continue
        assert sqlite_hits, f"{kind} query {query!r} returned nothing on SQLite"
        assert pg_hits, f"{kind} query {query!r} returned nothing on PostgreSQL"

    for kind, query, sqlite_hits, pg_hits, _overlap in rows:
        if kind in TOP_HIT_KINDS:
            assert sqlite_hits[0] == pg_hits[0], (
                f"{kind} query {query!r} disagrees on the top hit: "
                f"sqlite={sqlite_hits[0]} pg={pg_hits[0]}"
            )

    overlapping = sum(1 for _kind, _q, _s, _p, overlap in rows if overlap)
    assert overlapping / len(rows) >= 0.8, (
        f"top-5 overlap non-empty for only {overlapping}/{len(rows)} queries"
    )
