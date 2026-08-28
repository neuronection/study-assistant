import json
import sqlite3
from pathlib import Path
from typing import Any

from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alembic import command
from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

CARDS_JSON = json.dumps(
    {
        "cards": [
            {
                "kind": "basic",
                "front_md": "Power rule: derivative of $x^n$?",
                "back_md": "$nx^{n-1}$",
            },
            {
                "kind": "cloze",
                "front_md": "The {{c1::product rule}} differentiates a product",
                "back_md": "$(fg)' = f'g + fg'$",
            },
            {
                "kind": "reverse",
                "front_md": "$nx^{n-1}$",
                "back_md": "Power rule",
            },
        ]
    }
)


class CardGateway(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://probe",
            external_id="probe",
            label="probe",
            caps=["text"],
            api_key="k",
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        return self.responses.pop(0)


def make_client(tmp_path: Path, responses: list[str]) -> TestClient:
    app: FastAPI = create_app(Settings(data_dir=tmp_path, log_level="WARNING"))
    app.state.gateway = CardGateway(responses)
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])


def test_migration_0026_folds_flashcards_into_exercises(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "0025_material_provenance")

    raw = sqlite3.connect(db_path)
    now = "2026-08-20 10:00:00+00:00"
    raw.execute(
        "INSERT INTO profiles (id, name, created_at) VALUES (1, 'legacy', ?)", (now,)
    )
    raw.execute(
        "INSERT INTO courses (id, profile_id, title, created_at, updated_at) "
        "VALUES (7, 1, 'Legacy course', ?, ?)",
        (now, now),
    )
    raw.execute(
        "INSERT INTO tree_nodes (id, course_id, parent_id, title, depth, is_root, "
        "path, sort_path, order_idx, created_at) "
        "VALUES (70, 7, NULL, 'Legacy course', 0, 1, '/70/', '/70/', 0, ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO flashcards (id, profile_id, course_id, node_id, kind, front, back, "
        "source, source_ref, created_at) VALUES "
        "(41, 1, 7, 70, 'basic', ?, ?, 'manual', NULL, ?)",
        (
            json.dumps([{"type": "text", "md": "What is $d/dx\\, x^2$?"}]),
            json.dumps([{"type": "text", "md": "$2x$"}]),
            now,
        ),
    )
    raw.execute(
        "INSERT INTO flashcards (id, profile_id, course_id, node_id, kind, front, back, "
        "source, source_ref, created_at) VALUES "
        "(42, 1, 7, 70, 'cloze', ?, ?, 'anki_import', 'Deck A', ?)",
        (
            json.dumps([{"type": "text", "md": "The {{c1::chain}} rule"}]),
            json.dumps([{"type": "text", "md": "outer inner'"}]),
            now,
        ),
    )
    raw.execute(
        "INSERT INTO exercises (id, profile_id, course_id, node_id, title, created_at) "
        "VALUES (99, 1, 7, 70, 'Plain multi-step', ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO exercise_steps (id, exercise_id, order_idx, prompt, expected) "
        "VALUES (990, 99, 0, ?, ?)",
        (
            json.dumps([{"type": "text", "md": "Differentiate $x^2$."}]),
            json.dumps({"value": "2x"}),
        ),
    )
    raw.execute(
        "INSERT INTO fsrs_states (id, card_id, state, stability, difficulty, reps, "
        "lapses, due_at, last_review_at) VALUES "
        "(500, 41, 'review', 12.5, 5.0, 4, 1, '2026-09-01 10:00:00+00:00', ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO review_log (id, card_id, rating, interval_days, elapsed_days, "
        "reviewed_at) VALUES (600, 41, 3, 10.0, 10.0, ?)",
        (now,),
    )
    raw.commit()
    raw.close()

    command.upgrade(alembic_cfg, "head")

    raw = sqlite3.connect(db_path)
    cur = raw.cursor()
    assert cur.execute("SELECT version_num FROM alembic_version").fetchone()[
        0
    ] == "0046_drawing_view_box"
    assert (
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='flashcards'"
        ).fetchone()
        is None
    )

    _kind, title, deck, created_from = cur.execute(
        "SELECT kind, title, deck_ref, created_from FROM exercises "
        "WHERE profile_id = 1 AND kind = 'card_basic'"
    ).fetchone()
    assert title.startswith("What is")
    assert deck is None
    assert json.loads(created_from) == {"source": "manual", "source_ref": None}

    cloze_created_from = cur.execute(
        "SELECT created_from FROM exercises WHERE kind = 'card_cloze'"
    ).fetchone()[0]
    assert json.loads(cloze_created_from) == {
        "source": "anki_import",
        "source_ref": "Deck A",
    }

    prompt, expected = cur.execute(
        "SELECT prompt, expected FROM exercise_steps WHERE order_idx = 0 AND "
        "exercise_id = (SELECT id FROM exercises WHERE kind = 'card_basic')"
    ).fetchone()
    assert json.loads(prompt) == [{"type": "text", "md": "What is $d/dx\\, x^2$?"}]
    assert json.loads(expected)["back"] == [{"type": "text", "md": "$2x$"}]

    state, stability, due = cur.execute(
        "SELECT state, stability, due_at FROM fsrs_states WHERE card_id = "
        "(SELECT id FROM exercises WHERE kind = 'card_basic')"
    ).fetchone()
    assert state == "review"
    assert stability == 12.5
    assert due.startswith("2026-09-01")

    logs = cur.execute(
        "SELECT rating FROM review_log WHERE card_id = "
        "(SELECT id FROM exercises WHERE kind = 'card_basic')"
    ).fetchall()
    assert [row[0] for row in logs] == [3]

    plain_kind, plain_steps = cur.execute(
        "SELECT kind, (SELECT COUNT(*) FROM exercise_steps s "
        "WHERE s.exercise_id = e.id) FROM exercises e WHERE id = 99"
    ).fetchone()
    assert plain_kind == "multi_step"
    assert plain_steps == 1

    fk = cur.execute("PRAGMA foreign_key_list(fsrs_states)").fetchall()
    assert any(row[2] == "exercises" for row in fk)
    raw.close()


def test_card_api_round_trip_on_new_schema(tmp_path: Path) -> None:
    client = make_client(tmp_path, [])
    course_id = make_course(client)

    created = client.post(
        "/api/v1/flashcards",
        json={
            "kind": "basic",
            "front_md": "Power rule for $x^n$?",
            "back_md": "$nx^{n-1}$",
            "course_id": course_id,
        },
    )
    assert created.status_code == 201, created.text
    card = created.json()
    card_id = card["id"]
    assert card["kind"] == "basic"
    assert card["source"] == "manual"

    review = client.post(f"/api/v1/flashcards/{card_id}/review", json={"rating": 3})
    assert review.status_code == 200, review.text
    assert review.json()["state"] in ("learning", "review")

    listed = client.get(f"/api/v1/flashcards?course_id={course_id}").json()
    assert [entry["id"] for entry in listed] == [card_id]
    assert listed[0]["state"] in ("learning", "review")

    due = client.get(f"/api/v1/flashcards/due?course_id={course_id}").json()
    assert all(entry["id"] != card_id for entry in due)

    exercises = client.get(f"/api/v1/exercises?course_id={course_id}").json()
    assert exercises == []

    exported = client.get(f"/api/v1/flashcards/export-anki?course_id={course_id}")
    assert exported.status_code == 200
    assert len(exported.content) > 1000

    deleted = client.delete(f"/api/v1/flashcards/{card_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/flashcards?course_id={course_id}").json() == []


def test_migration_downgrade_restores_flashcards(tmp_path: Path) -> None:
    db_path = tmp_path / "down.db"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")

    raw = sqlite3.connect(db_path)
    now = "2026-08-20 10:00:00+00:00"
    raw.execute(
        "INSERT INTO profiles (id, name, created_at) VALUES (1, 'p', ?)", (now,)
    )
    raw.execute(
        "INSERT INTO courses (id, profile_id, title, created_at, updated_at) "
        "VALUES (7, 1, 'C', ?, ?)",
        (now, now),
    )
    raw.execute(
        "INSERT INTO exercises (id, profile_id, course_id, title, kind, deck_ref, "
        "created_from, created_at) VALUES "
        "(50, 1, 7, 'Round trip', 'card_basic', NULL, ?, ?)",
        (json.dumps({"source": "manual", "source_ref": None}), now),
    )
    raw.execute(
        "INSERT INTO exercise_steps (exercise_id, order_idx, prompt, expected) "
        "VALUES (50, 0, ?, ?)",
        (
            json.dumps([{"type": "text", "md": "front"}]),
            json.dumps({"kind": "card_basic", "back": [{"type": "text", "md": "back"}]}),
        ),
    )
    raw.commit()
    raw.close()

    command.downgrade(alembic_cfg, "0025_material_provenance")

    raw = sqlite3.connect(db_path)
    cur = raw.cursor()
    row = cur.execute(
        "SELECT kind, front, back, source FROM flashcards WHERE id = 50"
    ).fetchone()
    assert row[0] == "basic"
    assert json.loads(row[1]) == [{"type": "text", "md": "front"}]
    assert json.loads(row[2]) == [{"type": "text", "md": "back"}]
    assert row[3] == "manual"
    fk = cur.execute("PRAGMA foreign_key_list(fsrs_states)").fetchall()
    assert any(entry[2] == "flashcards" for entry in fk)
    raw.close()
