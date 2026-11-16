from pathlib import Path

import pytest

from app.core.config import Settings
from app.reset import collect_targets, delete_targets, run_reset


def test_collect_targets_respects_backups_flag(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    settings.ensure_dirs()
    (tmp_path / "study.sqlite3").write_text("db")
    (tmp_path / "study.sqlite3-wal").write_text("wal")
    (tmp_path / "study.sqlite3-shm").write_text("shm")
    (tmp_path / "blobs" / "abc").write_text("blob")
    (tmp_path / "backups" / "snapshot.zip").write_text("backup")

    without_backups = {target.name for target in collect_targets(settings, include_backups=False)}
    assert without_backups == {
        "study.sqlite3",
        "study.sqlite3-wal",
        "study.sqlite3-shm",
        "blobs",
        "cache",
        "thumbnails",
        "import-inbox",
    }

    with_backups = {target.name for target in collect_targets(settings, include_backups=True)}
    assert "backups" in with_backups


def test_delete_targets_removes_only_listed_paths(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    settings.ensure_dirs()
    (tmp_path / "study.sqlite3").write_text("db")
    (tmp_path / "study.sqlite3-wal").write_text("wal")
    (tmp_path / "blobs" / "abc").write_text("blob")
    (tmp_path / "backups" / "snapshot.zip").write_text("backup")

    delete_targets(collect_targets(settings, include_backups=False))
    assert not (tmp_path / "study.sqlite3").exists()
    assert not (tmp_path / "study.sqlite3-wal").exists()
    assert not (tmp_path / "blobs").exists()
    assert (tmp_path / "backups" / "snapshot.zip").exists()

    delete_targets(collect_targets(settings, include_backups=True))
    assert not (tmp_path / "backups").exists()


def test_reset_refuses_an_object_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        data_dir=tmp_path,
        object_storage_backend="s3",
        s3_bucket="bucket1",
    )
    monkeypatch.setattr("app.reset.get_settings", lambda: settings)
    (tmp_path / "study.sqlite3").write_text("db")
    assert run_reset(include_backups=False, assume_yes=True) is False
    assert (tmp_path / "study.sqlite3").exists()
