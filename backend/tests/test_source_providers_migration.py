"""Plan 86 A/E schema: provider columns, auth CHECK twin, review-event table."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _insert_source(db_path: Path, *, kind: str, provider: str, auth_kind: str) -> None:
    stamp = datetime(2026, 10, 22, 12, 0, 0).isoformat(sep=" ")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO external_sources "
            "(id, profile_id, course_id, kind, provider, auth_kind, account_ref, url, "
            "enabled, consecutive_failures, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, 'https://x.example/folder', 1, 0, ?)",
            (
                uuid.uuid4().hex,
                uuid.uuid4().hex,
                uuid.uuid4().hex,
                kind,
                provider,
                auth_kind,
                stamp,
            ),
        )


def _columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def test_provider_columns_open_string_and_auth_check(tmp_path: Path) -> None:
    db_path = tmp_path / "providers.db"
    command.upgrade(_cfg(db_path), "head")

    columns = _columns(db_path, "external_sources")
    assert {"provider", "auth_kind", "account_ref", "consecutive_failures"} <= columns
    assert "external_uid" in _columns(db_path, "exercises")

    _insert_source(
        db_path,
        kind="webdav_folder",
        provider="acme-private-webdav",
        auth_kind="token",
    )
    with pytest.raises(sqlite3.IntegrityError):
        _insert_source(db_path, kind="webdav_folder", provider="x", auth_kind="implicit")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_source(db_path, kind="ftp_folder", provider="x", auth_kind="none")

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "external_review_events" in tables


def test_downgrade_restores_previous_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "downgrade.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM external_sources WHERE kind = 'webdav_folder'")
    command.downgrade(config, "0006_vault_notes")

    columns = _columns(db_path, "external_sources")
    assert "provider" not in columns
    assert "auth_kind" not in columns
    assert "external_uid" not in _columns(db_path, "exercises")
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "external_review_events" not in tables
    with pytest.raises(sqlite3.IntegrityError):
        _insert_legacy_source(db_path, kind="webdav_folder")

    command.upgrade(config, "head")
    _insert_source(db_path, kind="webdav_folder", provider="x", auth_kind="none")


def _insert_legacy_source(db_path: Path, *, kind: str) -> None:
    stamp = datetime(2026, 10, 22, 12, 0, 0).isoformat(sep=" ")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO external_sources "
            "(id, profile_id, course_id, kind, url, enabled, created_at) "
            "VALUES (?, ?, ?, ?, 'https://x.example/folder', 1, ?)",
            (uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex, kind, stamp),
        )
