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
    "$schema": "saq/v1",
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

        inbox = client.post("/api/v1/quiz/inbox/probe.caq.json/import", params={"dry_run": "false"})
        assert inbox.status_code == 422


def test_baseline_course_columns_are_required(tmp_path: Path) -> None:
    """Study content belongs to a course (ADR-040).

    The legacy orphan backfill that lived in `0020` is folded into the
    squashed baseline (plan 81 F): the columns are NOT NULL from the first
    revision and cascade with their course, so the orphan state the old
    migration repaired cannot be created.
    """
    db_path = tmp_path / "baseline.db"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")

    raw = sqlite3.connect(db_path)
    for table in ("notes", "activities", "exercises"):
        columns = {row[1]: row for row in raw.execute(f"PRAGMA table_info({table})")}
        assert columns["course_id"][3] == 1, table
        fks = {(row[2], row[3], row[6]) for row in raw.execute(f"PRAGMA foreign_key_list({table})")}
        assert ("courses", "course_id", "CASCADE") in fks, table
    raw.close()
