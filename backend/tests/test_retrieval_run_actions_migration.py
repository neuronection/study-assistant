"""0011 retrieval-run action columns and partial unique indexes (SQLite)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _columns(db_path: Path, table: str) -> dict[str, tuple[str, bool, object]]:
    with sqlite3.connect(db_path) as connection:
        return {
            row[1]: (row[2], bool(row[3]), row[4])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }


def _indexes(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {row[1] for row in connection.execute("PRAGMA index_list('jobs')")}


def _insert_job(
    connection: sqlite3.Connection,
    job_id: str,
    *,
    status: str = "queued",
    idempotency_key: str | None = None,
    lock_key: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO jobs "
        "(id, type, status, progress, created_at, idempotency_key, lock_key, cancel_requested) "
        "VALUES (?, 'VECTOR_REINDEX', ?, 0, CURRENT_TIMESTAMP, ?, ?, 0)",
        (job_id, status, idempotency_key, lock_key),
    )


def test_run_action_columns_indexes_and_downgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "retrieval-actions.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")

    columns = _columns(db_path, "jobs")
    for name in ("idempotency_key", "lock_key", "heartbeat_at", "cancel_requested"):
        assert name in columns
    assert columns["cancel_requested"][1] is True  # NOT NULL
    indexes = _indexes(db_path)
    assert {"uq_jobs_idempotency_active", "uq_jobs_lock_key_active"} <= indexes

    with sqlite3.connect(db_path) as connection:
        _insert_job(
            connection,
            "job-1",
            idempotency_key="key-00000001",
            lock_key="vector_space:legacy-chunk-vecs",
        )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_job(
                connection,
                "job-2",
                idempotency_key="key-00000001",
                lock_key="vector_space:legacy-chunk-vecs",
            )
        connection.rollback()

        _insert_job(
            connection,
            "job-1",
            idempotency_key="key-00000001",
            lock_key="vector_space:legacy-chunk-vecs",
        )
        connection.execute("UPDATE jobs SET status = 'done' WHERE id = 'job-1'")
        _insert_job(
            connection,
            "job-2",
            idempotency_key="key-00000001",
            lock_key="vector_space:legacy-chunk-vecs",
        )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_job(
                connection,
                "job-3",
                idempotency_key="key-00000002",
                lock_key="vector_space:legacy-chunk-vecs",
            )
        connection.rollback()

    command.downgrade(config, "0010_retrieval_ops")
    columns = _columns(db_path, "jobs")
    for name in ("idempotency_key", "lock_key", "heartbeat_at", "cancel_requested"):
        assert name not in columns
    assert not ({"uq_jobs_idempotency_active", "uq_jobs_lock_key_active"} & _indexes(db_path))

    command.upgrade(config, "head")
    assert "heartbeat_at" in _columns(db_path, "jobs")
    assert {"uq_jobs_idempotency_active", "uq_jobs_lock_key_active"} <= _indexes(db_path)
