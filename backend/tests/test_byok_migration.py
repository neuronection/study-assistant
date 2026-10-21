"""BYOK capability vocabulary at the squashed baseline (plan 81 F).

The 0064 `audio`/`speech` → `stt`/`tts` rewrite is history: the baseline
only ever has the final vocabulary, so this pins the shape and the
baseline round-trip instead of replaying a lower revision.
"""

import sqlite3
import uuid
from pathlib import Path

from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return alembic_cfg


def _uid() -> str:
    return uuid.uuid4().hex


def test_baseline_byok_shape_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "byok.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "head")

    now = "2026-09-01 10:00:00+00:00"
    provider_id = _uid()
    model_id = _uid()
    raw = sqlite3.connect(db_path)
    columns = {row[1] for row in raw.execute("PRAGMA table_info(providers)")}
    assert "preset_key" in columns

    raw.execute(
        "INSERT INTO providers (id, name, type, base_url, keyring_ref, enabled, created_at) "
        "VALUES (?, 'OpenAI', 'openai_compatible', 'https://api.openai.com/v1', "
        "'provider:test', 1, ?)",
        (provider_id, now),
    )
    raw.execute(
        "INSERT INTO models (id, provider_id, external_id, label, caps, enabled, missing, "
        "discovered_at, last_seen_at) VALUES (?, ?, 'gemini-chat', 'chat', ?, 1, 0, ?, ?)",
        (model_id, provider_id, '["text", "stt", "tts"]', now, now),
    )
    for slot in ("text", "stt", "tts"):
        raw.execute(
            "INSERT INTO default_task_assignments (requires, model_id, fallback_model_id) "
            "VALUES (?, ?, NULL)",
            (slot, model_id),
        )
    raw.commit()

    caps = raw.execute("SELECT caps FROM models WHERE id = ?", (model_id,)).fetchone()[0]
    assert caps == '["text", "stt", "tts"]'
    requires = {
        row[0] for row in raw.execute("SELECT requires FROM default_task_assignments").fetchall()
    }
    assert {"stt", "tts", "text"} <= requires
    raw.close()

    command.downgrade(cfg, "base")
    raw = sqlite3.connect(db_path)
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "providers" not in tables
    assert "models" not in tables
    raw.close()

    command.upgrade(cfg, "head")
    raw = sqlite3.connect(db_path)
    assert "preset_key" in {
        row[1] for row in raw.execute("PRAGMA table_info(providers)").fetchall()
    }
    assert raw.execute("SELECT COUNT(*) FROM models").fetchone()[0] == 0
    raw.close()
