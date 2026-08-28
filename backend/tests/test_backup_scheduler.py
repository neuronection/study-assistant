import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.backup import (
    BackupScheduler,
    EffectiveBackupSettings,
    apply_retention,
    boot_integrity_check,
    create_backup,
    list_backups,
)


class NoAI:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None

    def describe(
        self,
        title: str,
        markdown: str,
        course_id: int | None = None,
    ) -> dict[str, Any] | None:
        return None


def make_client(data_dir: Path) -> TestClient:
    app = create_app(
        Settings(data_dir=data_dir, log_level="WARNING"),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def _settings(client: TestClient) -> Settings:
    app = client.app
    assert isinstance(app, FastAPI)
    settings = app.state.settings
    assert isinstance(settings, Settings)
    return settings


def _write_flag_backup(target_dir: Path, name: str) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / name).write_bytes(b"not a real backup")


def test_create_backup_writes_validated_archive(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    with client:
        client.post("/api/v1/courses", json={"title": "Course"})
        settings = _settings(client)
        path = create_backup(
            settings.db_path, settings.blobs_dir, settings.backups_dir, prefix="manual"
        )
        assert path.is_file()
        assert path.name.startswith("manual-")
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        assert "manifest.json" in names
        assert "database.sqlite" in names


def test_retention_keeps_dailies_and_one_weekly_per_week(tmp_path: Path) -> None:
    day = datetime(2026, 1, 5, tzinfo=UTC)
    names = []
    for index in range(40):
        stamp = day + timedelta(days=index)
        names.append(f"auto-{stamp.strftime('%Y%m%d-%H%M%S')}.zip")
    for name in names:
        _write_flag_backup(tmp_path, name)
    _write_flag_backup(tmp_path, "unrelated.zip")
    _write_flag_backup(tmp_path, "manual-20260301-000000.zip")

    apply_retention(tmp_path, keep_daily=7, keep_weekly=3)

    kept = {entry["name"] for entry in list_backups(tmp_path)}
    assert len(kept) == 10
    assert "manual-20260301-000000.zip" in kept
    for day_number in (8, 9, 10, 11, 12, 13):
        assert f"auto-202602{day_number:02d}-000000.zip" in kept
    for day_stamp in ("0207", "0201", "0125"):
        assert f"auto-2026{day_stamp}-000000.zip" in kept
    assert (tmp_path / "unrelated.zip").exists()


def test_scheduler_due_logic_and_sync_dir(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    with client:
        client.post("/api/v1/courses", json={"title": "Course"})
        settings = _settings(client)
        sync_dir = tmp_path / "synced"
        sync_dir.mkdir()
        now = {"value": datetime(2026, 8, 21, 12, 0, 0, tzinfo=UTC)}
        effective = EffectiveBackupSettings(
            auto=True,
            interval_hours=24,
            keep_daily=14,
            keep_weekly=8,
            sync_dir=str(sync_dir),
        )
        scheduler = BackupScheduler(
            lambda: effective,
            settings.db_path,
            settings.blobs_dir,
            settings.backups_dir,
            clock=lambda: now["value"],
        )

        first = scheduler.run_once(prefix="auto")
        assert first is not None and first.is_file()
        assert (sync_dir / first.name).is_file()

        assert scheduler.run_once(prefix="auto") is None

        now["value"] = now["value"] + timedelta(hours=25)
        third = scheduler.run_once(prefix="auto")
        assert third is not None
        assert len(list(sync_dir.glob("auto-*.zip"))) == 2

        effective = EffectiveBackupSettings(
            auto=False, interval_hours=24, keep_daily=14, keep_weekly=8, sync_dir=None
        )
        assert scheduler.run_once(prefix="auto") is None


def test_boot_recovery_restores_newest_valid_backup(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    with client:
        client.post("/api/v1/courses", json={"title": "Precious"})
        settings = _settings(client)
        create_backup(
            settings.db_path, settings.blobs_dir, settings.backups_dir, prefix="auto"
        )
    db_path = settings.db_path
    db_path.write_bytes(b"this is not a database anymore")
    (db_path.parent / (db_path.name + "-wal")).write_bytes(b"junk")

    recovery = boot_integrity_check(db_path, settings.backups_dir, settings.blobs_dir)

    assert recovery is not None
    assert recovery["from_backup"] is not None
    assert recovery["quarantined"].startswith("corrupt-")
    quarantined = db_path.parent / str(recovery["quarantined"])
    assert quarantined.read_bytes() == b"this is not a database anymore"
    assert not (db_path.parent / (db_path.name + "-wal")).exists()
    assert db_path.read_bytes() != b"this is not a database anymore"
    recovery_file = json.loads((tmp_path / "last-recovery.json").read_text())
    assert recovery_file["from_backup"] == recovery["from_backup"]

    client2 = make_client(tmp_path)
    with client2:
        courses = client2.get("/api/v1/courses").json()
        assert [course["title"] for course in courses] == ["Precious"]


def test_boot_recovery_without_valid_backup_quarantines(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    with client:
        client.post("/api/v1/courses", json={"title": "Doomed"})
        settings = _settings(client)
    db_path = settings.db_path
    db_path.write_bytes(b"corrupt junk")

    recovery = boot_integrity_check(db_path, settings.backups_dir, settings.blobs_dir)

    assert recovery is not None
    assert recovery["from_backup"] is None
    assert not db_path.exists()

    client2 = make_client(tmp_path)
    with client2:
        assert client2.get("/api/v1/courses").json() == []


def test_backup_api_status_create_settings_delete(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    with client:
        client.post("/api/v1/courses", json={"title": "Course"})

        status = client.get("/api/v1/backup/status")
        assert status.status_code == 200
        assert status.json()["settings"]["auto"] is True
        assert status.json()["backups"] == []

        created = client.post("/api/v1/backup/create")
        assert created.status_code == 200, created.text
        backups = created.json()["backups"]
        assert len(backups) == 1
        assert backups[0]["name"].startswith("manual-")
        assert backups[0]["size"] > 0

        interval = client.put(
            "/api/v1/backup/settings", json={"interval_hours": 6, "keep_daily": 5}
        )
        assert interval.status_code == 200
        assert interval.json()["settings"]["interval_hours"] == 6

        status = client.get("/api/v1/backup/status")
        assert status.json()["settings"]["interval_hours"] == 6
        assert status.json()["settings"]["keep_daily"] == 5

        bad_sync = client.put(
            "/api/v1/backup/settings", json={"sync_dir": "/nonexistent/path"}
        )
        assert bad_sync.status_code == 422

        sync_dir = tmp_path / "synced"
        sync_dir.mkdir()
        set_sync = client.put("/api/v1/backup/settings", json={"sync_dir": str(sync_dir)})
        assert set_sync.status_code == 200
        assert set_sync.json()["settings"]["sync_dir"] == str(sync_dir)

        clear_sync = client.put("/api/v1/backup/settings", json={"sync_dir": ""})
        assert clear_sync.status_code == 200
        assert clear_sync.json()["settings"]["sync_dir"] is None

        deleted = client.delete(f"/api/v1/backup/{backups[0]['name']}")
        assert deleted.status_code == 200
        assert deleted.json()["backups"] == []

        missing = client.delete("/api/v1/backup/manual-20990101-000000.zip")
        assert missing.status_code == 404

        bad_name = client.delete("/api/v1/backup/evil-name.zip")
        assert bad_name.status_code == 422
