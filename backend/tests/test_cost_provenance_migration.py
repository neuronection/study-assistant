"""Plan 58 P1 migration: float cost/model prices/cap become micros + provenance."""

import json
import sqlite3
import uuid
from pathlib import Path

from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def test_cost_provenance_migration_backfills_and_drops_float_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "cost.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "0031_lecture_sessions")

    now = "2026-11-01 10:00:00+00:00"
    provider_id = uuid.uuid4().hex
    model_id = uuid.uuid4().hex
    interaction_id = uuid.uuid4().hex
    raw = sqlite3.connect(db_path)
    raw.execute(
        "INSERT INTO providers (id, name, type, base_url, keyring_ref, preset_key, "
        "enabled, created_at) VALUES (?, 'OpenAI', 'openai_compatible', "
        "'https://api.openai.com/v1', "
        "'provider:test', 'openai', 1, ?)",
        (provider_id, now),
    )
    raw.execute(
        "INSERT INTO models (id, provider_id, external_id, label, caps, cost_in, cost_out, "
        "enabled, missing, discovered_at, last_seen_at) "
        "VALUES (?, ?, 'gpt-6.1-sol', 'GPT-6.1 Sol', '[\"text\"]', 2.0, 10.0, 1, 0, ?, ?)",
        (model_id, provider_id, now, now),
    )
    raw.execute(
        "INSERT INTO task_assignments (task, model_id, fallback_model_id, params) "
        "VALUES ('chat', ?, NULL, ?)",
        (model_id, json.dumps({"monthly_cap_usd": 2.5})),
    )
    raw.execute(
        "INSERT INTO ai_interactions (id, context_type, task, model, input_tokens, "
        "output_tokens, cost_usd, latency_ms, metadata, metadata_schema_version, created_at) "
        "VALUES (?, 'gateway', 'chat', 'GPT-6.1 Sol', 5, 2, 0.00003, 10, '{}', 1, ?)",
        (interaction_id, now),
    )
    raw.commit()
    raw.close()

    command.upgrade(cfg, "head")

    raw = sqlite3.connect(db_path)
    columns = {row[1] for row in raw.execute("PRAGMA table_info(ai_interactions)")}
    assert "cost_usd" not in columns
    assert {"cost_micros", "usage_source", "price_source", "price_version"} <= columns
    row = raw.execute(
        "SELECT cost_micros, price_source, price_version FROM ai_interactions"
    ).fetchone()
    assert row == (30, "legacy", "pre-contract")
    override = raw.execute(
        "SELECT provider_key, provider_ref, model, input_micros_per_million, "
        "output_micros_per_million FROM ai_price_overrides"
    ).fetchone()
    assert override == ("openai", None, "gpt-6.1-sol", 2_000_000, 10_000_000)
    params = json.loads(
        raw.execute("SELECT params FROM task_assignments WHERE task = 'chat'").fetchone()[0]
    )
    assert params == {"monthly_cap_micros": 2_500_000}
    raw.close()
