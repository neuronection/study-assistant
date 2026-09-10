from pathlib import Path

from alembic.config import Config

from alembic import command


def _run_migrations(db_path: Path, target: str | None = None) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, target or "head")


def test_migration_links_legacy_messages_into_a_branch_chain(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy.db"
    _run_migrations(db_path, "0043_course_default_task_assignments")

    import sqlite3

    raw = sqlite3.connect(db_path)
    now = "2026-08-27 09:00:00+00:00"
    raw.execute(
        "INSERT INTO profiles (id, name, created_at) VALUES (1, 'p', ?)", (now,)
    )
    raw.execute(
        "INSERT INTO chat_sessions (id, profile_id, public_id, title, created_at) "
        "VALUES (5, 1, 'legacy-5', 'legacy', ?)",
        (now,),
    )
    for index, role in enumerate(["user", "assistant", "user", "assistant"]):
        raw.execute(
            "INSERT INTO chat_messages (id, session_id, role, blocks, created_at) "
            f"VALUES ({10 + index}, 5, '{role}', '[{{\"type\":\"text\",\"md\":\"m{index}\"}}]', ?)",
            (now,),
        )
    raw.commit()
    raw.close()

    _run_migrations(db_path)

    check = sqlite3.connect(db_path)
    try:
        parents = {
            row[0]: row[1]
            for row in check.execute(
                "SELECT id, parent_id FROM chat_messages"
            ).fetchall()
        }
        children = {
            row[0]: row[1]
            for row in check.execute(
                "SELECT id, active_child_id FROM chat_messages"
            ).fetchall()
        }
        root = check.execute(
            "SELECT active_root_id FROM chat_sessions WHERE id = 5"
        ).fetchone()[0]
    finally:
        check.close()

    assert parents == {10: None, 11: 10, 12: 11, 13: 12}
    assert children == {10: 11, 11: 12, 12: 13, 13: None}
    assert root == 10


def test_branch_columns_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "head.db"
    _run_migrations(db_path)

    import sqlite3

    raw = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]
            for row in raw.execute("PRAGMA table_info(chat_messages)").fetchall()
        }
        session_columns = {
            row[1]
            for row in raw.execute("PRAGMA table_info(chat_sessions)").fetchall()
        }
    finally:
        raw.close()
    assert {"parent_id", "active_child_id"} <= columns
    assert "active_root_id" in session_columns
