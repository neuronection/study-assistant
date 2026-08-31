import sqlite3
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app.core.config import Settings
from app.main import create_app

CAQ_DOC: dict[str, Any] = {
    "$schema": "caq/v1",
    "title": "Probe",
    "questions": [
        {
            "id": "q1",
            "type": "truefalse",
            "stem_md": "probe",
            "answer": True,
            "explanation_md": "ok",
            "concepts": ["probe"],
            "skill": "conceptual",
            "bloom": "remember",
            "difficulty": 1,
            "expected_time_sec": 30,
        }
    ],
}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(Settings(data_dir=tmp_path, log_level="WARNING"))
    return TestClient(app)


def test_study_content_creation_requires_course(client: TestClient) -> None:
    with client:
        urls = [
            "/api/v1/notes",
            "/api/v1/quiz/generate",
            "/api/v1/quiz/import",
            "/api/v1/exercises",
            "/api/v1/exercises/generate",
            "/api/v1/exercises/drills",
            "/api/v1/flashcards",
            "/api/v1/flashcards/generate",
        ]
        for url in urls:
            response = client.post(url, params={"dry_run": "false"}, json={"title": "x"})
            assert response.status_code == 422, f"{url} accepted without course_id"

        inbox = client.post(
            "/api/v1/quiz/inbox/probe.caq.json/import", params={"dry_run": "false"}
        )
        assert inbox.status_code == 422


def test_migration_0020_moves_orphans_to_unsorted(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "0019_tree_nodes")

    raw = sqlite3.connect(db_path)
    now = "2026-08-19 10:00:00+00:00"
    raw.execute(
        "INSERT INTO profiles (id, name, created_at) VALUES (1, 'legacy', ?)", (now,)
    )
    raw.execute(
        "INSERT INTO notes (id, profile_id, course_id, owner_type, title, body, "
        "search_text, pinned, created_at, updated_at) "
        "VALUES (10, 1, NULL, 'standalone', 'orphan note', '[]', '', 0, ?, ?)",
        (now, now),
    )
    raw.execute(
        "INSERT INTO activities (id, profile_id, course_id, type, title, created_at) "
        "VALUES (20, 1, NULL, 'quiz', 'orphan quiz', ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO exercises (id, profile_id, course_id, title, created_at) "
        "VALUES (30, 1, NULL, 'orphan exercise', ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO flashcards (id, profile_id, course_id, kind, front, back, source, created_at) "
        "VALUES (40, 1, NULL, 'basic', '[]', '[]', 'manual', ?)",
        (now,),
    )
    raw.commit()
    raw.close()

    command.upgrade(alembic_cfg, "head")

    raw = sqlite3.connect(db_path)
    cur = raw.cursor()
    assert cur.execute("SELECT version_num FROM alembic_version").fetchone()[
        0
    ] == "0048_material_images"
    unsorted_id, root_id = cur.execute(
        "SELECT c.id, r.id FROM courses c JOIN tree_nodes r "
        "ON r.course_id = c.id AND r.is_root = 1 "
        "WHERE c.profile_id = 1 AND c.title = 'Unsorted'"
    ).fetchone()
    for table, row_id in (
        ("notes", 10),
        ("activities", 20),
        ("exercises", 30),
    ):
        course_id, node_id = cur.execute(
            f"SELECT course_id, node_id FROM {table} WHERE id = {row_id}"
        ).fetchone()
        assert course_id == unsorted_id, table
        assert node_id == root_id, table
        notnull = {
            row[1]: row[3] for row in cur.execute(f"PRAGMA table_info({table})")
        }
        assert notnull["course_id"] == 1, table
    raw.close()
