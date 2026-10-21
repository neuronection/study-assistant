"""Payload law at the squashed baseline (plan 81 F rework).

0074's typed columns/tables are part of the single baseline revision.
These tests pin that shape — the old JSON state columns are gone, the
typed state and document version siblings exist — plus the empty-schema
round-trip. The runtime validation contract lives in
`tests/test_payload_law.py`.
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


def _columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def test_baseline_types_the_known_shape_state(tmp_path: Path) -> None:
    db_path = tmp_path / "payload.db"
    command.upgrade(_cfg(db_path), "head")

    assert {
        "target_kind",
        "target_name",
        "target_node_id",
        "target_node_path",
        "original_md",
        "payload_schema_version",
        "result_schema_version",
    } <= _columns(db_path, "chat_proposals")
    assert "quiz_pending" not in _columns(db_path, "chat_sessions")
    assert {"view_x", "view_y", "view_width", "view_height"} <= _columns(
        db_path, "material_drawings"
    )
    assert "view" not in _columns(db_path, "material_drawings")
    assert {"chat_proposal_anchors", "chat_quiz_pendings"} <= _tables(db_path)

    for table, column in (
        ("notes", "body"),
        ("note_versions", "body"),
        ("chat_messages", "blocks"),
        ("extractions", "blocks"),
        ("material_drawings", "strokes"),
        ("material_drawings", "ocr_blocks"),
        ("note_drawings", "strokes"),
        ("note_drawings", "ocr_blocks"),
    ):
        assert f"{column}_schema_version" in _columns(db_path, table), (table, column)


def test_baseline_round_trip_keeps_the_payload_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "payload-round-trip.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    tables = _tables(db_path)
    assert "chat_proposals" not in tables
    assert "chat_proposal_anchors" not in tables
    assert "chat_quiz_pendings" not in tables

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            HEAD_REVISION
        )
    assert {"chat_proposal_anchors", "chat_quiz_pendings"} <= _tables(db_path)
