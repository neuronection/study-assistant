"""Scope & lifecycle law at the squashed baseline (plan 81 F rework).

0075's dead-schema removal and `scope_ref` retype are folded into the
baseline: this pins that `material_groups` never exists, the UUID
`scope_ref` shape, the nullable-unique partial index, and the baseline
round-trip.
"""

import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from migration_head import HEAD_REVISION

from alembic import command

NOW = "2026-10-21 10:00:00"


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _uid() -> str:
    return uuid.uuid4().hex


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def test_baseline_drops_groups_and_types_the_scope_ref(tmp_path: Path) -> None:
    db_path = tmp_path / "scope.db"
    command.upgrade(_cfg(db_path), "head")

    assert "material_groups" not in _tables(db_path)
    with sqlite3.connect(db_path) as connection:
        material_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(materials)").fetchall()
        }
        assert "group_id" not in material_columns

        scope_type = connection.execute(
            "SELECT type FROM pragma_table_info('skill_versions') WHERE name = 'scope_ref'"
        ).fetchone()[0]
        assert scope_type == "CHAR(32)"

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name = 'skill_versions'"
            ).fetchall()
        }
        assert {"uq_skill_versions", "uq_skill_versions_global"} <= indexes

        skill_id = _uid()
        connection.execute(
            "INSERT INTO skills (id, task, key, name, is_system) "
            "VALUES (?, 'description', 'scope81', 'Scope 81', 1)",
            (skill_id,),
        )
        connection.execute(
            "INSERT INTO skill_versions (id, skill_id, scope_type, scope_ref, version, "
            "system_template, user_template, is_active, created_at) "
            "VALUES (?, ?, 'system', NULL, 1, '', '', 1, ?)",
            (_uid(), skill_id, NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO skill_versions (id, skill_id, scope_type, scope_ref, version, "
                "system_template, user_template, is_active, created_at) "
                "VALUES (?, ?, 'system', NULL, 1, '', '', 1, ?)",
                (_uid(), skill_id, NOW),
            )


def test_baseline_round_trip_restores_the_scope_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "scope-round-trip.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert "skill_versions" not in _tables(db_path)
    assert "materials" not in _tables(db_path)

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            HEAD_REVISION
        )
        scope_type = connection.execute(
            "SELECT type FROM pragma_table_info('skill_versions') WHERE name = 'scope_ref'"
        ).fetchone()[0]
        assert scope_type == "CHAR(32)"
    assert "material_groups" not in _tables(db_path)
