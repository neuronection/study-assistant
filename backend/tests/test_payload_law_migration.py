"""Migration 0074 moves known-shape JSON state into columns/tables (plan 81 D).

The round-trip is pinned from the pre-0074 shape: seed proposals, a pending
quiz card and a drawing view at 0073, upgrade, assert the typed state, then
downgrade and assert the documents are restored.
"""

import json
import sqlite3
import uuid
from pathlib import Path

from alembic.config import Config

from alembic import command


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _uid() -> str:
    return str(uuid.uuid4())


NOW = "2026-10-21 10:00:00"


def _seed_old_shape(db_path: Path) -> dict[str, str]:
    ids = {
        "user": _uid(),
        "profile": _uid(),
        "course": _uid(),
        "node": _uid(),
        "chat_session": _uid(),
        "message": _uid(),
        "proposal": _uid(),
        "material": _uid(),
        "drawing": _uid(),
    }
    payload = {
        "note_id": "n1",
        "new_body_md": "beta",
        "text_edits": [{"op": "replace", "find": "alpha", "text": "beta"}],
        "original_md": "alpha",
        "target_kind": "note",
        "target_name": "N",
        "target_node_id": ids["node"],
        "target_node_path": ["C", "root"],
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO users (id, email, full_name, is_active, is_admin, "
            "failed_login_attempts, token_version, created_at, updated_at) "
            "VALUES (?, 'payload@test.local', '', 1, 0, 0, 1, ?, ?)",
            (ids["user"], NOW, NOW),
        )
        connection.execute(
            "INSERT INTO profiles (id, user_id, name, is_default, created_at, updated_at) "
            "VALUES (?, ?, 'p', 1, ?, ?)",
            (ids["profile"], ids["user"], NOW, NOW),
        )
        connection.execute(
            "INSERT INTO courses (id, profile_id, title, origin, hidden, created_at, updated_at) "
            "VALUES (?, ?, 'C', 'manual', 0, ?, ?)",
            (ids["course"], ids["profile"], NOW, NOW),
        )
        connection.execute(
            "INSERT INTO tree_nodes (id, course_id, title, order_idx, depth, path, "
            "sort_path, is_root, created_at) VALUES (?, ?, 'root', 0, 0, '/', '/', 1, ?)",
            (ids["node"], ids["course"], NOW),
        )
        connection.execute(
            "INSERT INTO chat_sessions (id, profile_id, course_id, node_id, title, "
            "public_id, quizme, quiz_pending, created_at) "
            "VALUES (?, ?, ?, ?, 'S', ?, 1, ?, ?)",
            (
                ids["chat_session"],
                ids["profile"],
                ids["course"],
                ids["node"],
                _uid(),
                json.dumps(
                    {
                        "question": "2+2?",
                        "choices": ["3", "4"],
                        "expected_index": 1,
                        "accept": ["four"],
                        "awaiting_answer": True,
                    }
                ),
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO chat_messages (id, session_id, role, blocks, created_at) "
            "VALUES (?, ?, 'assistant', ?, ?)",
            (ids["message"], ids["chat_session"], json.dumps([{"type": "text", "md": "hi"}]), NOW),
        )
        connection.execute(
            "INSERT INTO chat_proposals (id, message_id, action, payload, status, result, "
            "created_at) VALUES (?, ?, 'edit_note', ?, 'proposed', ?, ?)",
            (
                ids["proposal"],
                ids["message"],
                json.dumps(payload),
                json.dumps({"note_id": "n1"}),
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO materials (id, profile_id, course_id, kind, title, filename, "
            "status, starred, created_at) VALUES (?, ?, ?, 'md', 'M', 'm.md', 'ready', 0, ?)",
            (ids["material"], ids["profile"], ids["course"], NOW),
        )
        connection.execute(
            "INSERT INTO material_drawings (id, material_id, strokes, view, ocr_version, "
            "created_at) VALUES (?, ?, ?, ?, 0, ?)",
            (
                ids["drawing"],
                ids["material"],
                json.dumps([{"points": [[0, 0], [1, 1]], "width": 2}]),
                json.dumps({"x": 1.0, "y": 2.0, "width": 300.0, "height": 200.0}),
                NOW,
            ),
        )
        connection.commit()
    return ids


def test_upgrade_types_the_state_and_downgrade_restores_the_documents(tmp_path: Path) -> None:
    db_path = tmp_path / "payload.db"
    command.upgrade(_cfg(db_path), "head")
    command.downgrade(_cfg(db_path), "0073_uuid_identity")
    ids = _seed_old_shape(db_path)

    command.upgrade(_cfg(db_path), "head")
    with sqlite3.connect(db_path) as connection:
        proposal = connection.execute(
            "SELECT target_kind, target_name, target_node_id, target_node_path, "
            "original_md, payload FROM chat_proposals WHERE id = ?",
            (ids["proposal"],),
        ).fetchone()
        assert proposal[0] == "note"
        assert proposal[1] == "N"
        assert proposal[2] == ids["node"]
        assert json.loads(proposal[3]) == ["C", "root"]
        assert proposal[4] == "alpha"
        document = json.loads(proposal[5])
        assert document == {"note_id": "n1", "new_body_md": "beta"}

        anchors = connection.execute(
            "SELECT position, op, find_text, text FROM chat_proposal_anchors WHERE proposal_id = ?",
            (ids["proposal"],),
        ).fetchall()
        assert anchors == [(0, "replace", "alpha", "beta")]

        quiz = connection.execute(
            "SELECT question, choices, expected_index, accept, awaiting_answer "
            "FROM chat_quiz_pendings WHERE session_id = ?",
            (ids["chat_session"],),
        ).fetchone()
        assert quiz[0] == "2+2?"
        assert json.loads(quiz[1]) == ["3", "4"]
        assert quiz[2] == 1
        assert json.loads(quiz[3]) == ["four"]
        assert quiz[4] == 1

        view = connection.execute(
            "SELECT view_x, view_y, view_width, view_height FROM material_drawings WHERE id = ?",
            (ids["drawing"],),
        ).fetchone()
        assert view == (1.0, 2.0, 300.0, 200.0)

        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(chat_sessions)").fetchall()
        }
        assert "quiz_pending" not in columns
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(material_drawings)").fetchall()
        }
        assert "view" not in columns

    command.downgrade(_cfg(db_path), "0073_uuid_identity")
    with sqlite3.connect(db_path) as connection:
        restored = json.loads(
            connection.execute(
                "SELECT payload FROM chat_proposals WHERE id = ?", (ids["proposal"],)
            ).fetchone()[0]
        )
        assert restored["original_md"] == "alpha"
        assert restored["target_kind"] == "note"
        assert restored["target_node_path"] == ["C", "root"]
        assert restored["text_edits"] == [{"op": "replace", "find": "alpha", "text": "beta"}]

        pending = json.loads(
            connection.execute(
                "SELECT quiz_pending FROM chat_sessions WHERE id = ?", (ids["chat_session"],)
            ).fetchone()[0]
        )
        assert pending["question"] == "2+2?"
        assert pending["expected_index"] == 1
        assert pending["accept"] == ["four"]

        view = json.loads(
            connection.execute(
                "SELECT view FROM material_drawings WHERE id = ?", (ids["drawing"],)
            ).fetchone()[0]
        )
        assert view == {"x": 1.0, "y": 2.0, "width": 300.0, "height": 200.0}

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "chat_proposal_anchors" not in tables
        assert "chat_quiz_pendings" not in tables

    command.upgrade(_cfg(db_path), "head")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0074_payload_law"
        )
