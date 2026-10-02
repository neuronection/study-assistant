import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def test_byok_migration_renames_capabilities_and_backfills_preset_key(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "byok.db"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "0063_external_sources")

    raw = sqlite3.connect(db_path)
    now = "2026-09-01 10:00:00+00:00"
    raw.execute(
        "INSERT INTO courses (id, profile_id, title, created_at, updated_at) "
        "VALUES (10, 1, 'C', ?, ?)",
        (now, now),
    )
    raw.execute(
        "INSERT INTO providers (id, name, type, base_url, keyring_ref, enabled, created_at) "
        "VALUES (1, 'OpenAI', 'openai_compatible', 'https://api.openai.com/v1', "
        "'provider:1', 1, ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO models (id, provider_id, external_id, label, caps, enabled, missing, "
        "discovered_at, last_seen_at) VALUES "
        "(100, 1, 'gemini-chat', 'chat', ?, 1, 0, ?, ?), "
        "(101, 1, 'whisper-1', 'whisper', ?, 1, 0, ?, ?), "
        "(102, 1, 'tts-1', 'tts', ?, 1, 0, ?, ?)",
        (
            '["text", "vision", "audio", "tools"]',
            now,
            now,
            '["audio"]',
            now,
            now,
            '["speech"]',
            now,
            now,
        ),
    )
    raw.execute(
        "INSERT INTO default_task_assignments (requires, model_id, fallback_model_id) VALUES "
        "('audio', 101, NULL), ('speech', 102, NULL), ('text', NULL, NULL)"
    )
    raw.execute(
        "INSERT INTO course_default_task_assignments (course_id, requires, model_id, "
        "fallback_model_id) VALUES (10, 'audio', 101, NULL)"
    )
    raw.commit()
    raw.close()

    command.upgrade(alembic_cfg, "0065_identity_core")

    raw = sqlite3.connect(db_path)
    caps = dict(raw.execute("SELECT id, caps FROM models WHERE id IN (100, 101, 102)").fetchall())
    assert caps[100] == '["text", "vision", "stt", "tts", "tools"]'
    assert caps[101] == '["stt", "tts"]'
    assert caps[102] == '["tts"]'
    requires = [
        row[0]
        for row in raw.execute(
            "SELECT requires FROM default_task_assignments ORDER BY requires"
        ).fetchall()
    ]
    assert sorted(requires) == ["stt", "text", "tts"]
    assert (
        raw.execute(
            "SELECT requires FROM default_task_assignments WHERE model_id = 101"
        ).fetchone()[0]
        == "stt"
    )
    assert (
        raw.execute(
            "SELECT requires FROM course_default_task_assignments WHERE model_id = 101"
        ).fetchone()[0]
        == "stt"
    )
    columns = {row[1] for row in raw.execute("PRAGMA table_info(providers)").fetchall()}
    assert "preset_key" in columns
    preset_key = raw.execute("SELECT preset_key FROM providers WHERE id = 1").fetchone()[0]
    assert preset_key is None
    raw.close()

    command.downgrade(alembic_cfg, "0063_external_sources")

    raw = sqlite3.connect(db_path)
    caps = dict(raw.execute("SELECT id, caps FROM models WHERE id IN (100, 101, 102)").fetchall())
    assert caps[100] == '["text", "vision", "audio", "speech", "tools"]'
    assert caps[101] == '["audio", "speech"]'
    assert caps[102] == '["speech"]'
    requires = [
        row[0]
        for row in raw.execute(
            "SELECT requires FROM default_task_assignments ORDER BY requires"
        ).fetchall()
    ]
    assert sorted(requires) == ["audio", "speech", "text"]
    columns = {row[1] for row in raw.execute("PRAGMA table_info(providers)").fetchall()}
    assert "preset_key" not in columns
    raw.close()

    command.upgrade(alembic_cfg, "0065_identity_core")
