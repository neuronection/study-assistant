"""Migration 0073 cuts identity over to UUID primary keys (ADR-198).

The revision is destructive by design: SQLite cannot convert an integer
primary key into the UUID storage shape in place, so the identity domain is
rebuilt. These tests pin the shape in both directions — UUID keys at head,
integer keys after the downgrade — plus the round-trip back to head.
"""

import sqlite3
import uuid
from pathlib import Path

from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _declared_type(db_path: Path, table: str, column: str) -> str:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return next(str(row[2]).upper() for row in rows if row[1] == column)


def test_upgrade_builds_uuid_identity_and_cascades(tmp_path: Path) -> None:
    db_path = tmp_path / "identity.db"
    command.upgrade(_cfg(db_path), "head")

    assert _declared_type(db_path, "courses", "id") == "CHAR(32)"
    assert _declared_type(db_path, "tree_nodes", "course_id") == "CHAR(32)"
    assert _declared_type(db_path, "notes", "owner_id") == "CHAR(32)"
    assert _declared_type(db_path, "users", "id") == "CHAR(32)"

    course_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    material_id = str(uuid.uuid4())
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO users (id, email, full_name, is_active, is_admin, "
            "failed_login_attempts, token_version, created_at, updated_at) "
            "VALUES (?, 'identity@test.local', '', 1, 0, 0, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (str(uuid.uuid4()),),
        )
        profile_id = connection.execute("SELECT id FROM users").fetchone()[0]
        connection.execute(
            "INSERT INTO profiles (id, user_id, name, is_default, created_at, updated_at) "
            "VALUES (?, ?, 'p', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (str(uuid.uuid4()), profile_id),
        )
        course_id_row = connection.execute("SELECT id FROM profiles").fetchone()[0]
        connection.execute(
            "INSERT INTO courses (id, profile_id, title, origin, hidden, created_at, updated_at) "
            "VALUES (?, ?, 'C', 'manual', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (course_id, course_id_row),
        )
        connection.execute(
            "INSERT INTO tree_nodes (id, course_id, title, order_idx, depth, path, "
            "sort_path, is_root, created_at) "
            "VALUES (?, ?, 'root', 0, 0, '/', '/', 1, CURRENT_TIMESTAMP)",
            (node_id, course_id),
        )
        connection.execute(
            "INSERT INTO materials (id, profile_id, course_id, kind, title, filename, "
            "status, starred, created_at) "
            "VALUES (?, ?, ?, 'md', 'M', 'm.md', 'ready', 0, CURRENT_TIMESTAMP)",
            (material_id, course_id_row, course_id),
        )
        connection.execute(
            "INSERT INTO material_links (id, course_id, node_id, material_id, "
            "auto_assigned, created_at) VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)",
            (str(uuid.uuid4()), course_id, node_id, material_id),
        )
        connection.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        assert connection.execute("SELECT COUNT(*) FROM material_links").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM tree_nodes").fetchone()[0] == 0
        connection.commit()


def test_downgrade_restores_the_empty_integer_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "identity_down.db"
    command.upgrade(_cfg(db_path), "head")
    command.downgrade(_cfg(db_path), "0072_vocab_checks")

    assert _declared_type(db_path, "courses", "id") == "INTEGER"
    assert _declared_type(db_path, "tree_nodes", "course_id") == "INTEGER"
    assert _declared_type(db_path, "notes", "owner_id") == "INTEGER"
    assert _declared_type(db_path, "users", "id") == "CHAR(32)"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0072_vocab_checks"
        )
        assert connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO courses (id, profile_id, title, origin, hidden, created_at, "
            "updated_at) VALUES (1, 'p', 'legacy', 'manual', 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        assert connection.execute("SELECT id FROM courses").fetchone()[0] == 1
        connection.execute("DELETE FROM courses")

    command.upgrade(_cfg(db_path), "head")
    assert _declared_type(db_path, "courses", "id") == "CHAR(32)"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0
