"""0016/0017 vector space identity and token schema round-trip (SQLite).

Upgrades a populated 0015 database, asserts every existing space is stamped
with its frozen v1 key and keeps NULL tokenizer/chunk columns, then exercises
the 0017 downgrade (which drops the token columns but keeps ``space_key``).
A new ORM row after the upgrade persists the v1 key through the model default.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.domain.models import VectorDocument, VectorRecord, VectorSpace
from app.storage.db import make_engine, make_session_factory
from app.storage.vector_contract import space_key

TOKEN_COLUMNS = (
    "tokenizer_kind",
    "tokenizer_identifier",
    "tokenizer_revision",
    "tokenizer_artifact_sha256",
    "tokenizer_exact",
    "max_input_tokens",
    "chunk_max_tokens",
    "chunk_overlap_tokens",
    "chunk_max_chars",
)
TOKEN_RECORD_COLUMNS = ("token_count", "token_start", "token_end")


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _factory(db_path: Path) -> sessionmaker[Session]:
    return make_session_factory(make_engine(db_path))


def _columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _scalar(db_path: Path, statement: str, params: dict[str, Any] | None = None) -> Any:
    engine = make_engine(db_path)
    try:
        with engine.connect() as connection:
            return connection.execute(text(statement), params or {}).scalar()
    finally:
        engine.dispose()


def _insert_0015_space(db_path: Path, spec: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO vector_spaces "
            "(id, name, provider, model, dim, metric, normalize, "
            " query_prefix, document_prefix, chunker_version, composer_version, "
            " index_table, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'cosine', ?, ?, ?, '1', '1', NULL, 'building', "
            "        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                spec["id"],
                spec["name"],
                spec["provider"],
                spec["model"],
                spec["dim"],
                1 if spec["normalize"] else 0,
                spec["query_prefix"],
                spec["document_prefix"],
            ),
        )


def _expected_v1(spec: dict[str, Any]) -> str:
    return space_key(
        spec["provider"],
        spec["model"],
        spec["dim"],
        spec["normalize"],
        spec["query_prefix"],
        spec["document_prefix"],
        spec["chunker_version"],
        spec["composer_version"],
    )


def _specs() -> list[dict[str, Any]]:
    return [
        {
            "id": str(uuid.uuid4()),
            "name": f"key-plain-{uuid.uuid4().hex[:8]}",
            "provider": "openai",
            "model": "text-embedding-3-small",
            "dim": 1536,
            "normalize": True,
            "query_prefix": None,
            "document_prefix": None,
            "chunker_version": "1",
            "composer_version": "1",
        },
        {
            "id": str(uuid.uuid4()),
            "name": f"key-asym-{uuid.uuid4().hex[:8]}",
            "provider": "Ollama",
            "model": "embeddinggemma-2:440m ",
            "dim": 768,
            "normalize": False,
            "query_prefix": "query: ",
            "document_prefix": "passage: ",
            "chunker_version": "1",
            "composer_version": "1",
        },
    ]


def test_populated_upgrade_stamps_v1_keys_and_token_columns_stay_null(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "vector-key-migration.db"
    config = _cfg(db_path)
    command.upgrade(config, "0015_retrieval_alerts")
    assert "space_key" not in _columns(db_path, "vector_spaces")

    specs = _specs()
    for spec in specs:
        _insert_0015_space(db_path, spec)

    command.upgrade(config, "head")
    for column in TOKEN_COLUMNS:
        assert column in _columns(db_path, "vector_spaces"), column
    for column in TOKEN_RECORD_COLUMNS:
        assert column in _columns(db_path, "vector_records"), column

    stored = {
        row[0]: row[1]
        for row in sqlite3.connect(db_path).execute("SELECT id, space_key FROM vector_spaces")
    }
    for spec in specs:
        assert stored[spec["id"]] == _expected_v1(spec), spec["name"]
    nulls = (
        sqlite3.connect(db_path)
        .execute(
            "SELECT count(*) FROM vector_spaces WHERE "
            + " AND ".join(f"{column} IS NULL" for column in TOKEN_COLUMNS)
        )
        .fetchone()[0]
    )
    assert nulls == len(specs)
    assert (
        _scalar(db_path, "SELECT count(*) FROM vector_records WHERE token_count IS NOT NULL") == 0
    )


def test_new_row_persists_the_key_and_downgrade_keeps_it(tmp_path: Path) -> None:
    db_path = tmp_path / "vector-key-new-row.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")

    with _factory(db_path)() as session:
        row = VectorSpace(
            id=str(uuid.uuid4()),
            name=f"new-{uuid.uuid4().hex[:8]}",
            provider="openai",
            model="text-embedding-3-small",
            dim=4,
            normalize=True,
            chunker_version="1",
            composer_version="1",
            status="building",
        )
        session.add(row)
        session.commit()
        expected = space_key("openai", "text-embedding-3-small", 4, True, None, None, "1", "1")
        assert row.space_key == expected
        space_id = row.id

    command.downgrade(config, "0016_vector_space_stored_key")
    for column in TOKEN_COLUMNS:
        assert column not in _columns(db_path, "vector_spaces"), column
    for column in TOKEN_RECORD_COLUMNS:
        assert column not in _columns(db_path, "vector_records"), column
    assert (
        _scalar(db_path, "SELECT space_key FROM vector_spaces WHERE id = :id", {"id": space_id})
        == expected
    ), "0017 downgrade keeps the stored key"

    command.upgrade(config, "head")
    for column in TOKEN_COLUMNS:
        assert column in _columns(db_path, "vector_spaces"), column
    assert (
        _scalar(db_path, "SELECT space_key FROM vector_spaces WHERE id = :id", {"id": space_id})
        == expected
    )


def test_downgrade_to_0015_drops_the_key(tmp_path: Path) -> None:
    db_path = tmp_path / "vector-key-drop.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")
    command.downgrade(config, "0015_retrieval_alerts")
    assert "space_key" not in _columns(db_path, "vector_spaces")
    assert "tokenizer_kind" not in _columns(db_path, "vector_spaces")
    assert "token_count" not in _columns(db_path, "vector_records")

    command.upgrade(config, "head")
    assert "space_key" in _columns(db_path, "vector_spaces")
    assert "tokenizer_kind" in _columns(db_path, "vector_spaces")
    assert "token_count" in _columns(db_path, "vector_records")


def test_token_windows_coexist_per_source_chunk(tmp_path: Path) -> None:
    db_path = tmp_path / "vector-token-windows.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")

    with _factory(db_path)() as session:
        space = VectorSpace(
            id=str(uuid.uuid4()),
            name=f"windows-{uuid.uuid4().hex[:8]}",
            provider="openai",
            model="text-embedding-3-small",
            dim=4,
            chunker_version="1",
            composer_version="1",
            status="active",
        )
        session.add(space)
        session.flush()
        document = VectorDocument(
            id=str(uuid.uuid4()),
            space_id=space.id,
            kind="material",
            source_id=str(uuid.uuid4()),
            profile_id=None,
            source_hash="",
            schema_version=0,
        )
        session.add(document)
        session.flush()
        chunk_id = str(uuid.uuid4())
        for index in range(2):
            session.add(
                VectorRecord(
                    id=str(uuid.uuid4()),
                    document_id=document.id,
                    space_id=space.id,
                    chunk_id=chunk_id,
                    view="body",
                    chunk_index=index,
                    char_start=index * 10,
                    char_end=index * 10 + 10,
                    token_count=4,
                    token_start=index * 4,
                    token_end=index * 4 + 4,
                    content_hash="a" * 64,
                )
            )
        session.commit()
        stored = list(
            session.scalars(select(VectorRecord).where(VectorRecord.chunk_id == chunk_id))
        )
        assert len(stored) == 2
        assert {record.chunk_index for record in stored} == {0, 1}
        assert all(
            record.token_count == record.token_end - record.token_start  # type: ignore[operator]
            for record in stored
        )
