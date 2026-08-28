from pathlib import Path

from app.core.config import Settings
from app.reset import collect_targets, delete_targets


def test_collect_targets_respects_backups_flag(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    settings.ensure_dirs()
    (tmp_path / "app.db").write_text("db")
    (tmp_path / "app.db-wal").write_text("wal")
    (tmp_path / "app.db-shm").write_text("shm")
    (tmp_path / "blobs" / "abc").write_text("blob")
    (tmp_path / "backups" / "snapshot.zip").write_text("backup")

    without_backups = {target.name for target in collect_targets(settings, include_backups=False)}
    assert without_backups == {
        "app.db",
        "app.db-wal",
        "app.db-shm",
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
    (tmp_path / "app.db").write_text("db")
    (tmp_path / "app.db-wal").write_text("wal")
    (tmp_path / "blobs" / "abc").write_text("blob")
    (tmp_path / "backups" / "snapshot.zip").write_text("backup")

    delete_targets(collect_targets(settings, include_backups=False))
    assert not (tmp_path / "app.db").exists()
    assert not (tmp_path / "app.db-wal").exists()
    assert not (tmp_path / "blobs").exists()
    assert (tmp_path / "backups" / "snapshot.zip").exists()

    delete_targets(collect_targets(settings, include_backups=True))
    assert not (tmp_path / "backups").exists()
