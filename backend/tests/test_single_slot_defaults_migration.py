"""ADR-0037 migration 0070 — capability defaults go single-slot.

No-backwards-compatibility (owner directive): the fallback values on
capability rows are retired outright; decision kind override rows keep
theirs verbatim (the column stays — it is theirs). The course-default
table's fallback corner is dropped, guardedly: fresh rebuilds under the
new ORM never create it.
"""

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return alembic_cfg


def test_migration_0070_retores_capability_defaults_keeps_kinds(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "defaults.db"
    cfg = _cfg(db_path)
    # Pre-0037 wire schema: 0069 with the course fallback column present.
    command.upgrade(cfg, "0069_decision_transport")
    raw = sqlite3.connect(db_path)
    # Simulate the historical 0069 state for the course table (its corner
    # is metadata-driven on rebuilds; the column predates 0037).
    raw.execute("ALTER TABLE course_default_task_assignments ADD COLUMN fallback_model_id INTEGER")
    now = "2026-09-01 10:00:00+00:00"
    raw.execute(
        "INSERT INTO providers (id, name, type, base_url, keyring_ref, enabled, created_at) "
        "VALUES (1, 'P', 'openai_compatible', 'https://x/v1', 'provider:1', 1, ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO models (id, provider_id, external_id, label, caps, enabled, missing, "
        "discovered_at, last_seen_at) VALUES (10, 1, 'm-a', 'A', '[\"text\"]', 1, 0, ?, ?)",
        (now, now),
    )
    raw.execute(
        "INSERT INTO models (id, provider_id, external_id, label, caps, enabled, missing, "
        "discovered_at, last_seen_at) VALUES (11, 1, 'm-b', 'B', '[\"text\"]', 1, 0, ?, ?)",
        (now, now),
    )
    raw.execute(
        "INSERT INTO default_task_assignments (requires, model_id, fallback_model_id) "
        "VALUES ('text', 10, 11)"  # capability default → fallback retired
    )
    raw.execute(
        "UPDATE default_task_assignments SET model_id = 11, fallback_model_id = 10 "
        "WHERE requires = 'decision:score'"  # kind override keeps it verbatim
    )
    raw.commit()
    raw.close()

    command.upgrade(cfg, "head")

    raw = sqlite3.connect(db_path)
    rows = {
        requires: (model_id, fallback_id)
        for requires, model_id, fallback_id in raw.execute(
            "SELECT requires, model_id, fallback_model_id FROM default_task_assignments"
        ).fetchall()
    }
    assert rows["text"] == (10, None), "capability default fallback retired"
    assert rows["decision:score"] == (11, 10), "kind override fallback kept verbatim"
    course_columns = {
        row[1]
        for row in raw.execute("PRAGMA table_info(course_default_task_assignments)").fetchall()
    }
    assert "fallback_model_id" not in course_columns
    raw.close()


def test_migration_0070_is_fresh_rebuild_safe(tmp_path: Path) -> None:
    """A full rebuild under the new ORM re-creates 0066's course table
    without the fallback corner (metadata-driven); 0070 must not crash on
    a corner it never created."""
    db_path = tmp_path / "fresh.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "head")
    raw = sqlite3.connect(db_path)
    columns = {
        row[1]
        for row in raw.execute("PRAGMA table_info(course_default_task_assignments)").fetchall()
    }
    assert "fallback_model_id" not in columns
    rows = {
        requires: (model_id, fallback_id)
        for requires, model_id, fallback_id in raw.execute(
            "SELECT requires, model_id, fallback_model_id FROM default_task_assignments"
        ).fetchall()
    }
    # Only the kind slots are migration-seeded; capability rows seed at
    # boot (seed_default_task_assignments).
    assert set(rows) == {
        "decision:tool-dispatch",
        "decision:boolean-gate",
        "decision:choice",
        "decision:score",
    }
    assert all(value == (None, None) for value in rows.values())
    raw.close()
