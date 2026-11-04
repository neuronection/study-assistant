"""0012 vector-space metadata migration round-trip (SQLite).

Builds a pre-P3a database (0011) with a real legacy ``chunk_vecs`` store,
upgrades to head and asserts the ``content`` space, documents and records are
backfilled from ``vec_meta`` + the rowid reverse map. Downgrade must leave the
physical vector store untouched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.domain.models import Chunk, Course, Extraction, Material, Profile, User
from app.storage import vectors
from app.storage.db import make_engine, make_session_factory
from app.storage.vector_contract import content_hash
from app.storage.vector_store import StudyVectorStore

DIM = 4


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _factory(db_path: Path) -> sessionmaker[Session]:
    return make_session_factory(make_engine(db_path))


def _seed_legacy_store(factory: sessionmaker[Session]) -> list[str]:
    with factory() as session:
        user = User(email="migration@test.local", password_hash=None)
        session.add(user)
        session.flush()
        profile = Profile(user_id=user.id, name="Default", is_default=True)
        session.add(profile)
        session.flush()
        course = Course(profile_id=profile.id, title="Migration")
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
            blocks=[{"type": "text", "md": "alpha\n\nbeta"}],
            markdown="alpha\n\nbeta",
        )
        session.add(extraction)
        session.flush()
        chunks = [
            Chunk(extraction_id=extraction.id, ordinal=0, text="alpha"),
            Chunk(extraction_id=extraction.id, ordinal=1, text="beta"),
        ]
        session.add_all(chunks)
        session.commit()
        chunk_ids = [str(chunk.id) for chunk in chunks]
        vectors.store(
            session,
            chunk_ids,
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
            "legacy-model",
        )
        session.commit()
        return chunk_ids


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def _scalar(db_path: Path, statement: str, params: dict[str, Any] | None = None) -> Any:
    engine = make_engine(db_path)
    try:
        with engine.connect() as connection:
            return connection.execute(text(statement), params or {}).scalar()
    finally:
        engine.dispose()


def test_vector_spaces_upgrade_backfills_and_downgrade_keeps_chunk_vecs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "vector-spaces.db"
    config = _cfg(db_path)
    command.upgrade(config, "0011_retrieval_run_actions")

    chunk_ids = _seed_legacy_store(_factory(db_path))
    assert _scalar(db_path, "SELECT count(*) FROM chunk_vecs") == 2
    assert _scalar(db_path, "SELECT value FROM vec_meta WHERE key = 'model'") == "legacy-model"

    command.upgrade(config, "head")

    assert {
        "vector_spaces",
        "vector_documents",
        "vector_records",
    } <= _tables(db_path)
    assert _scalar(db_path, "SELECT count(*) FROM chunk_vecs") == 2
    assert _scalar(db_path, "SELECT count(*) FROM vector_spaces") == 1
    space = sqlite3.connect(db_path).execute(
        "SELECT id, name, model, dim, index_table, status FROM vector_spaces"
    ).fetchone()
    assert space == ("legacy-chunk-vecs", "content", "legacy-model", DIM, "chunk_vecs", "active")
    assert _scalar(db_path, "SELECT count(*) FROM vector_documents") == 1
    assert _scalar(db_path, "SELECT kind FROM vector_documents") == "material"
    assert _scalar(db_path, "SELECT count(*) FROM vector_records") == 2
    assert _scalar(db_path, "SELECT count(DISTINCT view) FROM vector_records") == 1
    assert _scalar(db_path, "SELECT view FROM vector_records LIMIT 1") == "body"
    rowids = {
        int(row[0])
        for row in sqlite3.connect(db_path).execute("SELECT rowid FROM vector_records")
    }
    assert rowids == {vectors.rowid_for(chunk_id) for chunk_id in chunk_ids}
    assert _scalar(db_path, "SELECT count(*) FROM vector_records WHERE content_hash = ''") == 0
    hashes = {
        row[0]
        for row in sqlite3.connect(db_path).execute(
            "SELECT content_hash FROM vector_records"
        )
    }
    assert hashes == {content_hash("alpha"), content_hash("beta")}
    assert _scalar(db_path, "SELECT count(*) FROM retrieval_coverage_snapshots") == 0

    command.downgrade(config, "0011_retrieval_run_actions")
    assert {
        "vector_spaces",
        "vector_documents",
        "vector_records",
    }.isdisjoint(_tables(db_path))
    assert _scalar(db_path, "SELECT count(*) FROM chunk_vecs") == 2

    command.upgrade(config, "head")
    assert _scalar(db_path, "SELECT count(*) FROM vector_spaces") == 1
    assert _scalar(db_path, "SELECT count(*) FROM vector_records") == 2

    with _factory(db_path)() as session:
        store = StudyVectorStore(session)
        result = store.backfill_metadata()
        session.commit()
        assert len(store.documents()) == 1
        assert result.records == 2
        assert {record.content_hash for record in store.records()} == {
            content_hash("alpha"),
            content_hash("beta"),
        }
    assert _scalar(db_path, "SELECT count(*) FROM vector_documents") == 1
