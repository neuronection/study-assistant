from collections.abc import Callable
from pathlib import Path

import pytest

from app.core.config import Settings, default_data_dir


def settings_from_env_file(env_file: Path | str | None) -> Settings:
    """Build ``Settings`` with the env-file source pinned explicitly.

    ``Settings.__init__`` is typed from the model's fields only, so
    pydantic-settings' init-only kwargs (``_env_file``) are invisible to
    mypy. Routing the call through an untyped factory alias keeps the
    documented constructor call intact with a single, named point of
    looseness instead of a ``# type: ignore`` per call site.
    """
    factory: Callable[..., Settings] = Settings
    return factory(_env_file=env_file)


def test_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "Study Assistant"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8200
    assert settings.db_path.name == "study.sqlite3"
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
    assert default_data_dir() == tmp_path / "Library" / "Application Support" / "StudyAssistant"


def test_data_dir_migrates_legacy_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_data_dir_untouched_without_legacy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    assert default_data_dir() == tmp_path / "StudyAssistant"
    assert not (tmp_path / "StudyAssistant").exists()
    assert not (tmp_path / "CourseAssistant").exists()


def test_unrelated_env_file_keys_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TRANSLATION_API_KEY=sk-test\nTRANSLATION_MODEL=gpt-test\nSA_PORT=9124\n",
        encoding="utf-8",
    )
    settings = settings_from_env_file(env_file)
    assert settings.port == 9124


def test_env_file_resolution_explicit_dev_and_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0028 §4 resolution: explicit `SA_ENV_FILE` always wins; the
    walk-up only applies in dev/test (S9 — a baked-in `.env` must never
    downgrade a production boot)."""
    from app.core.config import _resolve_env_file

    env_file = tmp_path / "deployment.env"
    env_file.write_text("SA_PORT=9125\n", encoding="utf-8")

    # Hermetic walk-up (S9): the §4 walk-up is anchored on the config
    # module's own path (`app/core/` upward), not the CWD, and the
    # checkout's real `.env` is untracked (absent in CI). Anchor it at a
    # constructed tree with its own `.env` so every branch resolves
    # against fixtures instead of ambient state.
    monkeypatch.setattr("app.core.config.__file__", str(tmp_path / "app" / "core" / "config.py"))
    walked_env = tmp_path / ".env"
    walked_env.write_text("SA_PORT=9126\n", encoding="utf-8")

    monkeypatch.delenv("SA_ENV_FILE", raising=False)
    monkeypatch.setenv("SA_APP_ENV", "production")
    assert _resolve_env_file() is None, "no silent .env in production"

    monkeypatch.setenv("SA_ENV_FILE", str(env_file))
    assert _resolve_env_file() == str(env_file), "explicit file is deliberate"

    monkeypatch.delenv("SA_ENV_FILE", raising=False)
    monkeypatch.setenv("SA_APP_ENV", "development")
    resolved = _resolve_env_file()
    assert resolved is not None, "dev walk-up still finds the constructed .env"
    assert Path(resolved).resolve() == walked_env.resolve(), "walk-up returns the constructed .env"
