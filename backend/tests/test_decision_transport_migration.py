"""Decision transport + seeded slots at the squashed baseline (plan 81 F).

0069's column add and slot seeding are folded into the baseline. This
pins the final shape, the seeded rows, and the baseline round-trip.
"""

import sqlite3
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.ai.providers import seed_default_task_assignments

_DECISION_SLOTS = (
    "decision:tool-dispatch",
    "decision:boolean-gate",
    "decision:choice",
    "decision:score",
)


def _cfg(db_path: Path) -> Config:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return alembic_cfg


def test_baseline_seeds_decision_slots(tmp_path: Path) -> None:
    db_path = tmp_path / "decision.db"
    command.upgrade(_cfg(db_path), "head")

    raw = sqlite3.connect(db_path)
    columns = {row[1] for row in raw.execute("PRAGMA table_info(models)").fetchall()}
    assert "decision_transport" in columns
    requires = {
        row[0] for row in raw.execute("SELECT requires FROM default_task_assignments").fetchall()
    }
    assert set(_DECISION_SLOTS) <= requires
    for slot in _DECISION_SLOTS:
        model_id, fallback = raw.execute(
            "SELECT model_id, fallback_model_id FROM default_task_assignments WHERE requires = ?",
            (slot,),
        ).fetchone()
        assert model_id is None and fallback is None
    raw.close()

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with Session(engine) as session:
            seed_default_task_assignments(session)
            session.commit()
    finally:
        engine.dispose()

    raw = sqlite3.connect(db_path)
    counts = dict(
        raw.execute(
            "SELECT requires, COUNT(*) FROM default_task_assignments "
            "WHERE requires LIKE 'decision:%' GROUP BY requires"
        ).fetchall()
    )
    raw.close()
    assert counts == dict.fromkeys(_DECISION_SLOTS, 1)


def test_baseline_round_trip_drops_and_reseeds_the_slots(tmp_path: Path) -> None:
    db_path = tmp_path / "decision-round-trip.db"
    config = _cfg(db_path)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    raw = sqlite3.connect(db_path)
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    raw.close()
    assert "models" not in tables
    assert "default_task_assignments" not in tables

    command.upgrade(config, "head")
    raw = sqlite3.connect(db_path)
    slots = {
        row[0]
        for row in raw.execute(
            "SELECT requires FROM default_task_assignments WHERE requires LIKE 'decision:%'"
        ).fetchall()
    }
    raw.close()
    assert slots == set(_DECISION_SLOTS)
