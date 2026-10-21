"""Chat branch columns at the squashed baseline (plan 81 F rework).

The legacy-first-message backfill that 0044 performed has no analogue in
a fresh baseline (there are no pre-branch rows), so this pins the final
shape and the baseline round-trip instead.
"""

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _columns(db_path: Path, table: str) -> set[str]:
    raw = sqlite3.connect(db_path)
    try:
        return {row[1] for row in raw.execute(f"PRAGMA table_info({table})").fetchall()}
    finally:
        raw.close()


def test_branch_columns_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "head.db"
    command.upgrade(_cfg(db_path), "head")

    assert {"parent_id", "active_child_id"} <= _columns(db_path, "chat_messages")
    assert "active_root_id" in _columns(db_path, "chat_sessions")


def test_baseline_round_trip_drops_and_rebuilds_the_branch_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "round_trip.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    raw = sqlite3.connect(db_path)
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    raw.close()
    assert "chat_messages" not in tables
    assert "chat_sessions" not in tables

    command.upgrade(config, "head")
    assert {"parent_id", "active_child_id"} <= _columns(db_path, "chat_messages")
    assert "active_root_id" in _columns(db_path, "chat_sessions")
