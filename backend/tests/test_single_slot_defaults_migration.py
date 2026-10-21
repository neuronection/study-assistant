"""Single-slot capability defaults at the squashed baseline (plan 81 F).

ADR-0037's transform (retire capability fallbacks, keep decision-kind
overrides) is folded into the baseline: the course-default table simply
never has the fallback corner, and the decision slots are seeded. Pins
the final shape and the baseline round-trip.
"""

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return alembic_cfg


def test_baseline_single_slot_defaults_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "defaults.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")

    raw = sqlite3.connect(db_path)
    course_columns = {
        row[1]
        for row in raw.execute("PRAGMA table_info(course_default_task_assignments)").fetchall()
    }
    assert "fallback_model_id" not in course_columns
    default_columns = {
        row[1] for row in raw.execute("PRAGMA table_info(default_task_assignments)").fetchall()
    }
    assert "fallback_model_id" in default_columns
    rows = {
        requires: (model_id, fallback_id)
        for requires, model_id, fallback_id in raw.execute(
            "SELECT requires, model_id, fallback_model_id FROM default_task_assignments"
        ).fetchall()
    }
    # The migration-seeded rows are the four decision slots, all empty.
    assert set(rows) == {
        "decision:tool-dispatch",
        "decision:boolean-gate",
        "decision:choice",
        "decision:score",
    }
    assert all(value == (None, None) for value in rows.values())
    raw.close()

    command.downgrade(config, "base")
    raw = sqlite3.connect(db_path)
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    raw.close()
    assert "default_task_assignments" not in tables

    command.upgrade(config, "head")
    raw = sqlite3.connect(db_path)
    assert len(raw.execute("SELECT * FROM default_task_assignments").fetchall()) == 4
    raw.close()
