from pathlib import Path

import pytest

from app.core.config import Settings, default_data_dir


def test_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "Study Assistant"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.db_path.name == "app.db"
    assert settings.blobs_dir.name == "blobs"
    assert settings.cache_dir.name == "cache"
    assert settings.thumbnails_dir.name == "thumbnails"
    assert settings.backups_dir.name == "backups"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SA_PORT", "9123")
    monkeypatch.setenv("SA_LOG_LEVEL", "DEBUG")
    settings = Settings()
    assert settings.port == 9123
    assert settings.log_level == "DEBUG"


def test_ensure_dirs(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    settings.ensure_dirs()
    assert settings.db_path.parent.is_dir()
    assert settings.blobs_dir.is_dir()
    assert settings.cache_dir.is_dir()
    assert settings.thumbnails_dir.is_dir()
    assert settings.backups_dir.is_dir()


def test_data_dir_linux(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_data_dir() == tmp_path / "StudyAssistant"

    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_data_dir() == tmp_path / ".local" / "share" / "StudyAssistant"


def test_data_dir_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert default_data_dir() == tmp_path / "StudyAssistant"

    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_data_dir() == tmp_path / "AppData" / "Roaming" / "StudyAssistant"


def test_data_dir_macos(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert (
        default_data_dir()
        == tmp_path / "Library" / "Application Support" / "StudyAssistant"
    )


def test_data_dir_migrates_legacy_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    legacy = tmp_path / "CourseAssistant"
    (legacy / "blobs").mkdir(parents=True)
    (legacy / "app.db").write_bytes(b"db")

    assert default_data_dir() == tmp_path / "StudyAssistant"
    assert not legacy.exists()
    assert (tmp_path / "StudyAssistant" / "app.db").read_bytes() == b"db"
    assert (tmp_path / "StudyAssistant" / "blobs").is_dir()


def test_data_dir_keeps_new_dir_when_legacy_also_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    legacy = tmp_path / "CourseAssistant"
    legacy.mkdir()
    (legacy / "old.db").write_bytes(b"old")
    current = tmp_path / "StudyAssistant"
    current.mkdir()
    (current / "app.db").write_bytes(b"new")

    assert default_data_dir() == current
    assert legacy.exists()
    assert (legacy / "old.db").read_bytes() == b"old"
    assert (current / "app.db").read_bytes() == b"new"


def test_data_dir_untouched_without_legacy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    assert default_data_dir() == tmp_path / "StudyAssistant"
    assert not (tmp_path / "StudyAssistant").exists()
    assert not (tmp_path / "CourseAssistant").exists()
