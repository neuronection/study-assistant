"""Plan 85 schema: discovery-kind widening + citation/planner/vault shapes.

Each slice's revision is exercised at the DB boundary (CHECK acceptance),
then the whole chain round-trips `base` → `head`.
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _insert_suggestion(db_path: Path, kind: str) -> None:
    stamp = datetime(2026, 10, 22, 12, 0, 0).isoformat(sep=" ")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO material_suggestions "
            "(id, profile_id, provider, url, url_norm, title, kind, status, "
            "created_at, updated_at) "
            "VALUES (?, ?, 'arxiv', 'https://x.example/a', 'https://x.example/a', 't', ?, "
            "'suggested', ?, ?)",
            (uuid.uuid4().hex, uuid.uuid4().hex, kind, stamp, stamp),
        )


def test_discovery_kind_widening_round_trips(tmp_path: Path) -> None:
    db_path = tmp_path / "kinds.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")

    _insert_suggestion(db_path, "paper")
    _insert_suggestion(db_path, "dataset")
    _insert_suggestion(db_path, "reference")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_suggestion(db_path, "lecture")

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "DELETE FROM material_suggestions WHERE kind IN ('paper', 'dataset', 'reference')"
        )
    command.downgrade(config, "0002_vocab_sweep")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_suggestion(db_path, "paper")

    command.upgrade(config, "head")
    _insert_suggestion(db_path, "paper")
    with sqlite3.connect(db_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM material_suggestions WHERE kind = 'paper'"
            ).fetchone()[0]
            == 1
        )


def test_chain_round_trips_from_base(tmp_path: Path) -> None:
    db_path = tmp_path / "round_trip.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert tables == {"alembic_version"}
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "0005_plan_item_external_uid"
        )


def _insert_material(db_path: Path, citation_kind: str | None) -> None:
    stamp = datetime(2026, 10, 22, 12, 0, 0).isoformat(sep=" ")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO materials "
            "(id, profile_id, course_id, kind, title, filename, status, starred, "
            "created_at, citation_kind) "
            "VALUES (?, ?, ?, 'link', 'Paper', 'paper', 'ready', 0, ?, ?)",
            (uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex, stamp, citation_kind),
        )


def test_citation_kind_check_accepts_members_and_null(tmp_path: Path) -> None:
    db_path = tmp_path / "citations.db"
    command.upgrade(_cfg(db_path), "head")
    _insert_material(db_path, None)
    _insert_material(db_path, "article")
    _insert_material(db_path, "dataset")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_material(db_path, "lecture")


def _insert_plan_item(db_path: Path, course_id: str, external_uid: str | None) -> None:
    stamp = datetime(2026, 10, 22, 12, 0, 0).isoformat(sep=" ")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO plan_items "
            "(id, profile_id, course_id, title, kind, due_date, origin, sort_key, "
            "external_uid, created_at) "
            "VALUES (?, ?, ?, 'Lecture', 'study', '2026-10-23', 'manual', 0, ?, ?)",
            (uuid.uuid4().hex, uuid.uuid4().hex, course_id, external_uid, stamp),
        )


def test_plan_item_external_uid_is_unique_per_course(tmp_path: Path) -> None:
    db_path = tmp_path / "plan_uid.db"
    command.upgrade(_cfg(db_path), "head")
    course_id = uuid.uuid4().hex
    _insert_plan_item(db_path, course_id, None)
    _insert_plan_item(db_path, course_id, None)
    _insert_plan_item(db_path, course_id, "lecture-1")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_plan_item(db_path, course_id, "lecture-1")
    _insert_plan_item(db_path, uuid.uuid4().hex, "lecture-1")
