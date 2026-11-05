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


def test_alerts_and_generation_tags_upgrade_and_downgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "alerts-migration.db"
    config = _cfg(db_path)
    command.upgrade(config, "0014_vector_record_chunk_id")

    interactions = _columns(db_path, "ai_interactions")
    assert "metadata" not in interactions
    assert "metadata_schema_version" not in interactions
    assert "notifications" not in _tables(db_path)

    command.upgrade(config, "head")
    interactions = _columns(db_path, "ai_interactions")
    assert interactions["metadata"][0] == "JSON"
    assert interactions["metadata"][1] is True
    assert interactions["metadata_schema_version"][0] == "SMALLINT"
    assert interactions["metadata_schema_version"][1] is True
    assert {"notification_kinds", "notifications"} <= _tables(db_path)

    columns = _columns(db_path, "notifications")
    assert columns["dedup_key"][1] is False
    assert columns["payload"][0] == "JSON"
    assert columns["recipients"][0] == "JSON"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO notification_kinds (key, title, description, severity, admin_only, "
            "default_enabled, created_at) VALUES "
            "('retrieval.quality_gate', 'Quality', '', 'warning', 1, 1, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO notifications (id, kind, severity, title, body, payload, "
            "recipients, dedup_key, dedup_expires_at, created_at) VALUES "
            "('n-1', 'retrieval.quality_gate', 'warning', 'Quality', '', '{}', "
            "'[]', 'retrieval.quality_gate:space-a', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.commit()

    command.downgrade(config, "0014_vector_record_chunk_id")
    assert "notifications" not in _tables(db_path)
    assert "notification_kinds" not in _tables(db_path)
    interactions = _columns(db_path, "ai_interactions")
    assert "metadata" not in interactions
    assert "metadata_schema_version" not in interactions

    command.upgrade(config, "head")
    assert {"notification_kinds", "notifications"} <= _tables(db_path)
    assert "metadata" in _columns(db_path, "ai_interactions")


def test_job_progress_detail_upgrade_and_downgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "progress-migration.db"
    config = _cfg(db_path)
    command.upgrade(config, "0018_vector_record_token_windows")
    assert "progress_detail" not in _columns(db_path, "jobs")

    command.upgrade(config, "head")
    jobs = _columns(db_path, "jobs")
    assert jobs["progress_detail"][0] == "JSON"
    assert jobs["progress_detail"][1] is False

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO jobs (id, type, status, progress, progress_detail, created_at) "
            "VALUES ('job-progress', 'VECTOR_REINDEX', 'running', 42, "
            '\'{"phase": "embedding", "processed_documents": 2}\', CURRENT_TIMESTAMP)'
        )
        stored = connection.execute(
            "SELECT progress_detail FROM jobs WHERE id = 'job-progress'"
        ).fetchone()[0]
        assert "embedding" in stored
        connection.commit()

    command.downgrade(config, "0018_vector_record_token_windows")
    assert "progress_detail" not in _columns(db_path, "jobs")

    command.upgrade(config, "head")
    assert "progress_detail" in _columns(db_path, "jobs")
