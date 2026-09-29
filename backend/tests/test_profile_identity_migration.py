"""Migration 0066_profile_identity — the aligned `profiles` schema
(identity-auth §5) and the family head assertion.

0066 is the destructive greenfield baseline (no backwards
compatibility): the profile domain is rebuilt from the model metadata
and downgrade is irreversible. Legacy-chain data tests stop at
0065_identity_core; this module pins the head (moved to
0067_auth_session_created_at when `auth_sessions.created_at` landed).
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


def test_migration_head_is_profile_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "head.db"
    command.upgrade(_cfg(db_path), "head")

    raw = sqlite3.connect(db_path)
    assert (
        raw.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        == "0067_auth_session_created_at"
    )
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
            row
            for row in raw.execute(f"PRAGMA table_info({table})").fetchall()
            if row[1] == column
        )
        assert col[2].startswith("CHAR") or col[2] == "UUID", (table, col)
    raw.close()


def test_migration_downgrade_is_irreversible(tmp_path: Path) -> None:
    db_path = tmp_path / "irreversible.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")
    with pytest.raises(NotImplementedError):
        command.downgrade(config, "0065_identity_core")
