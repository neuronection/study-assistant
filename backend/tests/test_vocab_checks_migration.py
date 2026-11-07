"""DB-level vocabulary checks at the squashed baseline (plan 81 F rework).

0072's CHECK twins are part of the baseline now. The round-trip proves the
constraint survives `downgrade base` → `upgrade head`; the pre-0072
"no CHECK" half no longer exists.
"""

import sqlite3
import uuid
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
            (uuid.uuid4().hex, unit),
        )


def test_vocab_checks_round_trip_on_the_baseline(tmp_path: Path) -> None:
    db_path = tmp_path / "checks.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_goal(db_path, "nope")
    _insert_goal(db_path, "answers")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM study_goals").fetchone()[0] == 1

    command.downgrade(config, "base")
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "study_goals" not in tables

    command.upgrade(config, "head")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_goal(db_path, "still-nope")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM study_goals").fetchone()[0] == 0
