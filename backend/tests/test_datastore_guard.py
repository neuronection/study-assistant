import json
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nx_auth.instance import IdentityMode

from app.core.config import Settings
from app.local import head_revision, run_migrations
from app.main import create_app
from app.storage.datastore_guard import (
    DatastoreQuarantineError,
    guard_datastore,
    read_marker,
)
from app.storage.db import make_engine


def _settings(tmp_path: Path) -> Settings:
    settings = Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
    )
    settings.ensure_dirs()
    return settings


def _legacy_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        connection.execute("INSERT INTO alembic_version VALUES ('0067_auth_session_created_at')")
        connection.execute("CREATE TABLE materials (id VARCHAR(32) PRIMARY KEY)")
        connection.execute("INSERT INTO materials VALUES ('old-material')")
        connection.commit()
    finally:
        connection.close()


def test_legacy_datastore_is_quarantined_and_replaced(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _legacy_db(settings.db_path)
    settings.blobs_dir.mkdir(exist_ok=True)
    (settings.blobs_dir / "blob.bin").write_bytes(b"payload")
    settings.backups_dir.mkdir(exist_ok=True)
    (settings.backups_dir / "manual-20260101-000000.zip").write_bytes(b"old-backup")

    notice = guard_datastore(settings)

    assert notice is not None
    folder = Path(notice.path)
    assert folder.is_dir()
    assert not settings.db_path.exists()
    assert (folder / "study.sqlite3").is_file()
    assert (folder / "blobs" / "blob.bin").is_file()
    assert (folder / "backups" / "manual-20260101-000000.zip").is_file()
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["format"] == "nx-datastore-quarantine/v1"
    assert manifest["schema_revision"] == "0067_auth_session_created_at"
    assert manifest["reason"] == "incompatible-schema"
    assert read_marker(settings.data_dir) == notice.as_dict()

    engine = make_engine(settings.db_path)
    try:
        run_migrations(engine)
    finally:
        engine.dispose()
    connection = sqlite3.connect(settings.db_path)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        connection.close()
    assert row == (head_revision(),)


def test_current_datastore_is_untouched(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_path)
    try:
        run_migrations(engine)
    finally:
        engine.dispose()
    before = settings.db_path.read_bytes()
    assert guard_datastore(settings) is None
    assert settings.db_path.read_bytes() == before
    assert read_marker(settings.data_dir) is None


def test_fresh_install_needs_no_quarantine(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert guard_datastore(settings) is None
    assert read_marker(settings.data_dir) is None


def test_unreadable_datastore_is_preserved_not_deleted(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.db_path.write_bytes(b"this is not a sqlite database")
    notice = guard_datastore(settings)
    assert notice is not None
    assert notice.reason == "unreadable"
    assert (Path(notice.path) / "study.sqlite3").read_bytes() == b"this is not a sqlite database"
    assert not settings.db_path.exists()


def test_quarantine_failure_keeps_the_old_datastore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    _legacy_db(settings.db_path)
    before = settings.db_path.read_bytes()

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("locked")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(DatastoreQuarantineError, match="could not be moved aside"):
        guard_datastore(settings)
    assert settings.db_path.read_bytes() == before
    assert read_marker(settings.data_dir) is None
    assert not any(settings.data_dir.glob("previous-datastore-*"))


def test_instance_config_exposes_the_quarantine_marker(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _legacy_db(settings.db_path)
    notice = guard_datastore(settings)
    assert notice is not None
    desktop = Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
        identity_mode=IdentityMode.DESKTOP,
    )
    with TestClient(create_app(desktop)) as client:
        payload = client.get("/api/v1/instance/config").json()
    assert payload["datastore_quarantine"] == {
        "path": notice.path,
        "reason": "incompatible-schema",
        "quarantined_at": notice.quarantined_at,
        "schema_revision": "0067_auth_session_created_at",
        "from_version": None,
    }


def test_postgres_datastores_are_left_to_the_operator(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
        database_url="postgresql+psycopg://user:pass@localhost:5432/study",
    )
    assert guard_datastore(settings) is None
