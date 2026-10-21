"""Migration 0075 removes the dead group schema and applies the law (plan 81 E).

Pinned from the pre-0075 shape: a `material_groups` row, a material pointing
at it, and a `skill_versions` row whose `scope_ref` is stored in the integer
column. Upgrade asserts the table/column are gone, the scope ref becomes a
canonical UUID, and global-scope versions are unique. Downgrade restores the
empty group shape and the integer column, then re-upgrade is clean.
"""

import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command

HEAD = "0075_scope_lifecycle"
PREVIOUS = "0074_payload_law"
NOW = "2026-10-21 10:00:00"


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_old_shape(db_path: Path) -> dict[str, str]:
    ids = {
        "user": _uid(),
        "profile": _uid(),
        "course": _uid(),
        "group": _uid(),
        "material": _uid(),
        "skill": _uid(),
        "version": _uid(),
    }
    scope_ref = _uid()
    ids["scope_ref"] = scope_ref
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO users (id, email, full_name, is_active, is_admin, "
            "failed_login_attempts, token_version, created_at, updated_at) "
            "VALUES (?, 'scope75@test.local', '', 1, 0, 0, 1, ?, ?)",
            (ids["user"], NOW, NOW),
        )
        connection.execute(
            "INSERT INTO profiles (id, user_id, name, is_default, created_at, updated_at) "
            "VALUES (?, ?, 'p', 1, ?, ?)",
            (ids["profile"], ids["user"], NOW, NOW),
        )
        connection.execute(
            "INSERT INTO courses (id, profile_id, title, origin, hidden, created_at, updated_at) "
            "VALUES (?, ?, 'C', 'manual', 0, ?, ?)",
            (ids["course"], ids["profile"], NOW, NOW),
        )
        connection.execute(
            "INSERT INTO material_groups (id, profile_id, course_id, title, kind, order_idx, "
            "created_at) VALUES (?, ?, ?, 'Group', 'image-set', 0, ?)",
            (ids["group"], ids["profile"], ids["course"], NOW),
        )
        connection.execute(
            "INSERT INTO materials (id, profile_id, course_id, group_id, kind, title, filename, "
            "status, starred, created_at) VALUES (?, ?, ?, ?, 'md', 'M', 'm.md', 'ready', 0, ?)",
            (ids["material"], ids["profile"], ids["course"], ids["group"], NOW),
        )
        connection.execute(
            "INSERT INTO skills (id, task, key, name, is_system) "
            "VALUES (?, 'description', 'scope75', 'Scope 75', 1)",
            (ids["skill"],),
        )
        connection.execute(
            "INSERT INTO skill_versions (id, skill_id, scope_type, scope_ref, version, "
            "system_template, user_template, is_active, created_at) "
            "VALUES (?, ?, 'course', ?, 1, '', '', 1, ?)",
            (ids["version"], ids["skill"], scope_ref, NOW),
        )
        connection.commit()
    return ids


def test_upgrade_drops_groups_and_types_the_scope_ref(tmp_path: Path) -> None:
    db_path = tmp_path / "scope.db"
    command.upgrade(_cfg(db_path), "head")
    command.downgrade(_cfg(db_path), PREVIOUS)
    ids = _seed_old_shape(db_path)

    command.upgrade(_cfg(db_path), "head")
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "material_groups" not in tables
        columns = {row[1] for row in connection.execute("PRAGMA table_info(materials)").fetchall()}
        assert "group_id" not in columns
        assert (
            connection.execute(
                "SELECT title FROM materials WHERE id = ?", (ids["material"],)
            ).fetchone()[0]
            == "M"
        )

        scope_type = connection.execute(
            "SELECT type FROM pragma_table_info('skill_versions') WHERE name = 'scope_ref'"
        ).fetchone()[0]
        assert scope_type == "CHAR(32)"
        stored = connection.execute(
            "SELECT scope_ref FROM skill_versions WHERE id = ?", (ids["version"],)
        ).fetchone()[0]
        assert stored == ids["scope_ref"].replace("-", "")

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name = 'skill_versions'"
            ).fetchall()
        }
        assert {"uq_skill_versions", "uq_skill_versions_global"} <= indexes

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO skill_versions (id, skill_id, scope_type, scope_ref, version, "
                "system_template, user_template, is_active, created_at) "
                "VALUES (?, ?, 'system', NULL, 1, '', '', 1, ?)",
                (_uid(), ids["skill"], NOW),
            )
            connection.execute(
                "INSERT INTO skill_versions (id, skill_id, scope_type, scope_ref, version, "
                "system_template, user_template, is_active, created_at) "
                "VALUES (?, ?, 'system', NULL, 1, '', '', 1, ?)",
                (_uid(), ids["skill"], NOW),
            )

    command.downgrade(_cfg(db_path), PREVIOUS)
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "material_groups" in tables
        columns = {row[1] for row in connection.execute("PRAGMA table_info(materials)").fetchall()}
        assert "group_id" in columns
        scope_type = connection.execute(
            "SELECT type FROM pragma_table_info('skill_versions') WHERE name = 'scope_ref'"
        ).fetchone()[0]
        assert scope_type == "INTEGER"
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name = 'materials'"
            ).fetchall()
        }
        assert "ix_materials_group_id" in indexes

    command.upgrade(_cfg(db_path), "head")
    with sqlite3.connect(db_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == HEAD
