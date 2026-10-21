"""The squashed baseline: head assertion and empty-schema round-trip (plan 81 F).

The chain is one revision generated from the post-A-E models (ADR-196).
This module owns the head assertion and the `downgrade base` → `upgrade
head` proof; every other migration test imports the shared
`HEAD_REVISION` from `tests/migration_head.py`.
"""

import sqlite3
from pathlib import Path

from alembic.config import Config
from migration_head import HEAD_REVISION

from alembic import command


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def test_migration_head_is_latest(tmp_path: Path) -> None:
    db_path = tmp_path / "head.db"
    command.upgrade(_cfg(db_path), "head")

    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
    columns = {
        row[1]: (row[2], bool(row[3]))
        for row in raw.execute("PRAGMA table_info(profiles)").fetchall()
    }
    # identity-auth §5 `profiles`: uuid PK, user_id NOT NULL, is_default,
    # created_at/updated_at + product columns color/preferences/last_used_at
    assert columns["id"][0].startswith("CHAR") or columns["id"][0] == "UUID"
    assert columns["user_id"][1] is True
    assert columns["is_default"][1] is True
    assert columns["updated_at"][1] is True
    assert "last_used_at" in columns
    assert "color" in columns and "preferences" in columns

    fk = {
        (row[2], row[3], row[6])
        for row in raw.execute("PRAGMA foreign_key_list(profiles)").fetchall()
    }
    assert ("users", "user_id", "CASCADE") in fk

    for table, column in (("courses", "profile_id"), ("study_goals", "profile_id")):
        col = next(
            row for row in raw.execute(f"PRAGMA table_info({table})").fetchall() if row[1] == column
        )
        assert col[2].startswith("CHAR") or col[2] == "UUID", (table, col)
    raw.close()


def test_downgrade_base_drops_the_schema_and_upgrade_rebuilds(tmp_path: Path) -> None:
    db_path = tmp_path / "round_trip.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")

    command.downgrade(config, "base")
    raw = sqlite3.connect(db_path)
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"alembic_version"}, tables
    assert raw.execute("SELECT COUNT(*) FROM alembic_version").fetchone()[0] == 0
    raw.close()

    command.upgrade(config, "head")
    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
    course_id_type = next(
        row[2] for row in raw.execute("PRAGMA table_info(courses)").fetchall() if row[1] == "id"
    )
    assert course_id_type == "CHAR(32)"
    raw.close()
