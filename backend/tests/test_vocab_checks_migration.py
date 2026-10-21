"""Migration 0072 adds DB-level vocabulary checks; downgrade removes them.

Also proves the batch table rebuilds preserve rows (the CHECK adds rebuild
each affected SQLite table).
"""

import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _insert_goal(db_path: Path, unit: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO study_goals (profile_id, unit, answers_per_day, minutes_per_day) "
            "VALUES (?, ?, 20, 30)",
            (f"profile-{unit}", unit),
        )


def test_vocab_checks_upgrade_downgrade_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "checks.db"
    command.upgrade(_cfg(db_path), "head")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_goal(db_path, "nope")
    _insert_goal(db_path, "answers")

    command.downgrade(_cfg(db_path), "0071_chat_transport")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0071_chat_transport"
        )
        assert connection.execute("SELECT COUNT(*) FROM study_goals").fetchone()[0] == 1
    _insert_goal(db_path, "nope")
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM study_goals WHERE unit = 'nope'")

    command.upgrade(_cfg(db_path), "head")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM study_goals").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        _insert_goal(db_path, "still-nope")
