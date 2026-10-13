import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command

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


def test_migration_0069_adds_decision_transport_and_seeds_slots(tmp_path: Path) -> None:
    db_path = tmp_path / "decision.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "0068_rename_legacy_ca_schemes")

    raw = sqlite3.connect(db_path)
    now = "2026-09-01 10:00:00+00:00"
    raw.execute(
        "INSERT INTO providers (id, name, type, base_url, keyring_ref, enabled, created_at) "
        "VALUES (1, 'TypeSafe', 'decision', 'https://api.typesafe.ai', 'provider:1', 1, ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO models (id, provider_id, external_id, label, caps, enabled, missing, "
        "discovered_at, last_seen_at) VALUES (100, 1, 'jev-latest', 'Jev', "
        "'[\"decision\"]', 1, 0, ?, ?)",
        (now, now),
    )
    raw.commit()
    raw.close()

    command.upgrade(cfg, "head")

    raw = sqlite3.connect(db_path)
    columns = {row[1] for row in raw.execute("PRAGMA table_info(models)").fetchall()}
    assert "decision_transport" in columns
    transport = raw.execute("SELECT decision_transport FROM models WHERE id = 100").fetchone()[0]
    assert transport is None
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

    command.downgrade(cfg, "0068_rename_legacy_ca_schemes")

    raw = sqlite3.connect(db_path)
    columns = {row[1] for row in raw.execute("PRAGMA table_info(models)").fetchall()}
    assert "decision_transport" not in columns
    requires = {
        row[0] for row in raw.execute("SELECT requires FROM default_task_assignments").fetchall()
    }
    assert not (set(_DECISION_SLOTS) & requires)
    raw.close()

    command.upgrade(cfg, "head")
    raw = sqlite3.connect(db_path)
    slots = {
        row[0]
        for row in raw.execute(
            "SELECT requires FROM default_task_assignments WHERE requires LIKE 'decision:%'"
        ).fetchall()
    }
    assert slots == set(_DECISION_SLOTS)
    raw.close()


def test_migration_0069_upgrade_is_idempotent_on_seeded_slots(tmp_path: Path) -> None:
    db_path = tmp_path / "decision-idem.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "0068_rename_legacy_ca_schemes")

    raw = sqlite3.connect(db_path)
    raw.execute(
        "INSERT INTO default_task_assignments (requires, model_id, fallback_model_id) "
        "VALUES ('decision:score', NULL, NULL)"
    )
    raw.commit()
    raw.close()

    command.upgrade(cfg, "head")

    raw = sqlite3.connect(db_path)
    rows = raw.execute(
        "SELECT requires, model_id FROM default_task_assignments WHERE requires = 'decision:score'"
    ).fetchall()
    assert rows == [("decision:score", None)]
    raw.close()
