"""`app/local.py` — the desktop bootstrap (plan 20 Phase 4).

Migrations are an entrypoint responsibility (D6): `run_migrations` runs
here (and in the docker `migrate` service / dev scripts / test fixtures)
— `create_app` never migrates.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.local import (
    bootstrap_environment,
    default_data_dir,
    find_alembic_ini,
    run_migrations,
)


def test_bootstrap_environment_sets_desktop_defaults(tmp_path: Path) -> None:
    env: dict[str, str] = {}
    returned = bootstrap_environment(tmp_path, env)
    assert returned is env
    assert (tmp_path / "blobs").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert env["SA_DATA_DIR"] == str(tmp_path)
    assert env["SA_DATABASE_URL"] == f"sqlite:///{tmp_path / 'study.sqlite3'}"
    assert env["SA_IDENTITY_MODE"] == "desktop"
    assert env["SA_ENV_FILE"] == str(tmp_path / "env")


def test_bootstrap_environment_never_overrides_real_env(tmp_path: Path) -> None:
    env: dict[str, str] = {"SA_IDENTITY_MODE": "server", "SA_DATA_DIR": "/srv/study"}
    bootstrap_environment(tmp_path, env)
    assert env["SA_IDENTITY_MODE"] == "server"
    assert env["SA_DATA_DIR"] == "/srv/study"


def test_default_data_dir_honors_override(tmp_path: Path) -> None:
    assert default_data_dir({"SA_DATA_DIR": str(tmp_path)}) == tmp_path


def test_find_alembic_ini() -> None:
    assert find_alembic_ini().name == "alembic.ini"


def test_run_migrations_migrates_the_settings_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D6 — the entrypoint migrates; the app does not."""
    db_file = tmp_path / "bootstrapped.sqlite3"
    monkeypatch.setenv("SA_APP_ENV", "test")
    monkeypatch.setenv("SA_DATABASE_URL", f"sqlite:///{db_file}")
    get_settings.cache_clear()
    try:
        run_migrations()
    finally:
        get_settings.cache_clear()
    with sqlite3.connect(db_file) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "users" in tables
    assert "alembic_version" in tables
