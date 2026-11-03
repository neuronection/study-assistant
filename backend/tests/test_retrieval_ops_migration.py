"""0010 retrieval-ops migration round-trip (SQLite)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def _columns(db_path: Path, table: str) -> dict[str, tuple[str, bool]]:
    with sqlite3.connect(db_path) as connection:
        return {
            row[1]: (row[2], bool(row[3]))
            for row in connection.execute(f"PRAGMA table_info({table})")
        }


def test_retrieval_ops_upgrade_and_downgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "retrieval-migration.db"
    config = _cfg(db_path)
    command.upgrade(config, "0010_retrieval_ops")

    assert {
        "retrieval_query_rollups",
        "retrieval_coverage_snapshots",
    } <= _tables(db_path)
    jobs = _columns(db_path, "jobs")
    assert jobs["result"][0] == "JSON"
    assert jobs["result"][1] is False

    with sqlite3.connect(db_path) as connection:
        check = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'jobs'"
        ).fetchone()[0]
        assert "VECTOR_REINDEX" in check
        assert "VECTOR_MAINTENANCE" in check
        assert "VECTOR_CUTOVER" in check
        connection.execute(
            "INSERT INTO jobs (id, type, status, progress, created_at) "
            "VALUES ('job-vector', 'VECTOR_REINDEX', 'queued', 0, CURRENT_TIMESTAMP)"
        )
        connection.execute("DELETE FROM jobs WHERE id = 'job-vector'")
        connection.commit()

    command.downgrade(config, "0009_calendar_links")
    tables = _tables(db_path)
    assert "retrieval_query_rollups" not in tables
    assert "retrieval_coverage_snapshots" not in tables
    assert "result" not in _columns(db_path, "jobs")

    command.upgrade(config, "head")
    assert {
        "retrieval_query_rollups",
        "retrieval_coverage_snapshots",
    } <= _tables(db_path)
    assert "result" in _columns(db_path, "jobs")
