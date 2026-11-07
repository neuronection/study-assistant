import io
import json
import sqlite3
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from migration_head import HEAD_REVISION
from sqlalchemy import create_engine

from app.core.config import Settings
from app.local import DatabaseVersionError, head_revision, run_migrations
from app.main import create_app
from app.services.platform.backup import BackupError, read_archive


def _client(data_dir: Path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=data_dir, log_level="WARNING")))


def _rewrite_archive(
    data: bytes,
    *,
    mutate: Callable[[dict[str, Any]], None] | None = None,
    extra: dict[str, bytes] | None = None,
) -> bytes:
    payload: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            payload[name] = archive.read(name)
    manifest = json.loads(payload["manifest.json"])
    if mutate is not None:
        mutate(manifest)
    payload["manifest.json"] = json.dumps(manifest).encode()
    if extra:
        payload.update(extra)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_read_archive_rejects_traversal_members() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"format": "sa-backup/v1"}))
        archive.writestr("database.sqlite", b"")
        archive.writestr("blobs/../../escape.txt", b"pwned")
    with pytest.raises(BackupError, match="unsafe path"):
        read_archive(buffer.getvalue())


def test_restore_refuses_an_archive_without_a_schema_stamp(tmp_path: Path) -> None:
    with _client(tmp_path / "app") as client:
        exported = client.get("/api/v1/backup/export")
        assert exported.status_code == 200
        v1 = _rewrite_archive(exported.content, mutate=lambda manifest: manifest.pop("schema"))
        before = client.get("/api/v1/backup/status").json()
        restored = client.post(
            "/api/v1/backup/restore",
            files={"file": ("backup.zip", v1, "application/zip")},
        )
        assert restored.status_code == 422
        assert "earlier release" in restored.json()["detail"]
        assert client.get("/api/v1/backup/status").json()["backups"] == before["backups"]


def test_restore_rejects_a_blob_member_that_escapes_the_blobs_dir(tmp_path: Path) -> None:
    with _client(tmp_path / "app") as client:
        exported = client.get("/api/v1/backup/export")
        assert exported.status_code == 200
        tampered = _rewrite_archive(exported.content, extra={"blobs/../../escape.txt": b"pwned"})
        restored = client.post(
            "/api/v1/backup/restore",
            files={"file": ("backup.zip", tampered, "application/zip")},
        )
        assert restored.status_code == 422
        assert "unsafe path" in restored.json()["detail"]
        assert not (tmp_path / "escape.txt").exists()


def test_restore_accepts_a_current_archive(tmp_path: Path) -> None:
    with _client(tmp_path / "app") as client:
        exported = client.get("/api/v1/backup/export")
        assert exported.status_code == 200
        restored = client.post(
            "/api/v1/backup/restore",
            files={"file": ("backup.zip", exported.content, "application/zip")},
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["status"] == "restored"


def test_run_migrations_refuses_a_foreign_revision(tmp_path: Path) -> None:
    db_path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
    connection.execute("INSERT INTO alembic_version VALUES ('0067_auth_session_created_at')")
    connection.commit()
    connection.close()

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with pytest.raises(DatabaseVersionError, match="earlier release"):
            run_migrations(engine)
    finally:
        engine.dispose()

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        connection.close()
    assert row == ("0067_auth_session_created_at",)
    assert head_revision() == HEAD_REVISION


def test_run_migrations_accepts_the_current_chain(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        run_migrations(engine)
    finally:
        engine.dispose()
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        connection.close()
    assert row == (head_revision(),)
