from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.domain.models import (
    Answer,
    Attempt,
    ChatMessage,
    ExerciseStep,
    Question,
    ReviewLog,
)
from app.main import create_app


class Scripted(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="m",
            label="m",
            caps=["text", "vision"],
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        return "ok"


class NoAI:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None

    def describe(
        self,
        title: str,
        markdown: str,
        course_id: int | None = None,
    ) -> dict[str, Any] | None:
        return None


def make_client(tmp: Any) -> TestClient:
    import tempfile
    from pathlib import Path

    data_dir = Path(tempfile.mkdtemp(prefix="ca-trash-"))
    app = create_app(
        Settings(data_dir=data_dir, log_level="WARNING"),
        gateway=Scripted(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Course"}).json()["id"])


def test_note_delete_and_restore_round_trip() -> None:
    import tempfile

    client = make_client(tempfile.mkdtemp())
    with client:
        course_id = make_course(client)
        note_id = client.post(
            "/api/v1/notes",
            json={"title": "Trashed note", "body_md": "body", "course_id": course_id},
        ).json()["id"]
        import base64

        client.post(
            f"/api/v1/notes/{note_id}/drawings",
            json={
                "strokes": [{"points": [[0, 0], [5, 5]], "width": 2}],
                "png_base64": base64.b64encode(b"png-bytes").decode(),
                "ocr": False,
            },
        )
        client.patch(
            f"/api/v1/notes/{note_id}", json={"body_md": "v2", "force_version": True}
        )

        deleted = client.delete(f"/api/v1/notes/{note_id}")
        assert deleted.status_code == 200, deleted.text
        item_id = deleted.json()["deleted_item_id"]
        assert client.get(f"/api/v1/notes/{note_id}").status_code == 404

        trash_list = client.get("/api/v1/deleted-items").json()
        assert [entry["id"] for entry in trash_list] == [item_id]
        assert trash_list[0]["entity_type"] == "note"
        assert trash_list[0]["title"] == "Trashed note"

        restored = client.post(f"/api/v1/deleted-items/{item_id}/restore")
        assert restored.status_code == 200, restored.text
        assert restored.json()["entity_type"] == "note"

        detail = client.get(f"/api/v1/notes/{note_id}").json()
        assert detail["body"][0]["md"] == "v2"
        assert len(detail["drawings"]) == 1
        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) >= 1

        assert client.get("/api/v1/deleted-items").json() == []


def test_quiz_delete_and_restore_with_attempts() -> None:
    import tempfile

    from app.domain.models import Activity, Mistake

    client = make_client(tempfile.mkdtemp())
    with client:
        course_id = make_course(client)
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            activity = Activity(
                profile_id=1, course_id=course_id, type="quiz", title="Trash quiz"
            )
            db.add(activity)
            db.flush()
            question = Question(
                activity_id=activity.id,
                type="choice",
                stem=[{"type": "text", "md": "1+1?"}],
                options=[{"type": "text", "md": "2"}],
                answer={"index": 0},
            )
            db.add(question)
            db.flush()
            attempt = Attempt(activity_id=activity.id, mode="practice")
            db.add(attempt)
            db.flush()
            db.add(
                Answer(
                    attempt_id=attempt.id, question_id=question.id, correct=False
                )
            )
            db.add(Mistake(profile_id=1, question_id=question.id))
            db.commit()
            activity_id = activity.id

        deleted = client.delete(f"/api/v1/quiz/activities/{activity_id}")
        assert deleted.status_code == 200
        item_id = deleted.json()["deleted_item_id"]
        with app.state.session_factory() as db:
            assert db.query(Question).count() == 0
            assert db.query(Answer).count() == 0
            assert db.query(Attempt).count() == 0
            assert db.query(Mistake).count() == 0

        restored = client.post(f"/api/v1/deleted-items/{item_id}/restore")
        assert restored.status_code == 200, restored.text

        with app.state.session_factory() as db:
            assert db.get(Activity, activity_id) is not None
            assert db.query(Question).count() == 1
            assert db.query(Answer).count() == 1
            assert db.query(Attempt).count() == 1
            assert db.query(Mistake).count() == 1


def test_exercise_delete_and_restore_with_review_log() -> None:
    import tempfile

    from app.domain.models import Exercise

    client = make_client(tempfile.mkdtemp())
    with client:
        course_id = make_course(client)
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            exercise = Exercise(
                profile_id=1, course_id=course_id, title="Trashed exercise"
            )
            db.add(exercise)
            db.flush()
            db.add(
                ExerciseStep(
                    exercise_id=exercise.id,
                    order_idx=0,
                    prompt=[{"type": "text", "md": "Solve"}],
                    expected={"answer": "42"},
                )
            )
            db.add(
                ReviewLog(
                    card_id=exercise.id, rating=3, interval_days=1, elapsed_days=0
                )
            )
            db.commit()
            exercise_id = exercise.id

        deleted = client.delete(f"/api/v1/exercises/{exercise_id}")
        assert deleted.status_code == 200
        item_id = deleted.json()["deleted_item_id"]
        with app.state.session_factory() as db:
            assert db.query(ExerciseStep).count() == 0
            assert db.query(ReviewLog).count() == 0

        restored = client.post(f"/api/v1/deleted-items/{item_id}/restore")
        assert restored.status_code == 200, restored.text
        with app.state.session_factory() as db:
            assert db.get(Exercise, exercise_id) is not None
            assert db.query(ExerciseStep).count() == 1
            assert db.query(ReviewLog).count() == 1
        detail = client.get(f"/api/v1/exercises/{exercise_id}").json()
        assert detail["title"] == "Trashed exercise"


def test_chat_delete_and_restore_with_messages() -> None:
    import tempfile

    from app.domain.models import ChatSession

    client = make_client(tempfile.mkdtemp())
    with client:
        course_id = make_course(client)
        session_id = client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id, "title": "Tutoring"}
        ).json()["id"]

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            db.add(
                ChatMessage(
                    session_id=session_id,
                    role="user",
                    blocks=[{"type": "text", "md": "hello"}],
                )
            )
            db.commit()

        deleted = client.delete(f"/api/v1/chat/sessions/{session_id}")
        assert deleted.status_code == 200
        item_id = deleted.json()["deleted_item_id"]
        with app.state.session_factory() as db:
            assert db.query(ChatMessage).count() == 0

        restored = client.post(f"/api/v1/deleted-items/{item_id}/restore")
        assert restored.status_code == 200
        with app.state.session_factory() as db:
            assert db.get(ChatSession, session_id) is not None
            assert db.query(ChatMessage).count() == 1


def test_trash_expiry_purges_old_items() -> None:
    import tempfile

    from app.domain.models import DeletedItem
    from app.services.platform.trash import purge_expired, snapshot

    client = make_client(tempfile.mkdtemp())
    with client:
        course_id = make_course(client)
        note_id = client.post(
            "/api/v1/notes",
            json={"title": "Expired", "body_md": "x", "course_id": course_id},
        ).json()["id"]

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            item_id = snapshot(db, "note", note_id, "Expired", 1)
            item = db.get(DeletedItem, item_id)
            assert item is not None
            item.purge_after = datetime.now(UTC) - timedelta(days=1)
            db.commit()

            client.delete(f"/api/v1/notes/{note_id}")

            assert purge_expired(db) >= 1
            assert db.get(DeletedItem, item_id) is None


def test_course_delete_requires_confirmed_backup() -> None:
    import tempfile

    client = make_client(tempfile.mkdtemp())
    with client:
        course_id = make_course(client)
        refused = client.delete(f"/api/v1/courses/{course_id}")
        assert refused.status_code == 409

        deleted = client.delete(
            f"/api/v1/courses/{course_id}", params={"confirmed_backup": True}
        )
        assert deleted.status_code == 200
        assert client.get("/api/v1/courses").json() == []


def test_trash_purge_one_endpoint() -> None:
    import tempfile

    client = make_client(tempfile.mkdtemp())
    with client:
        course_id = make_course(client)
        note_id = client.post(
            "/api/v1/notes",
            json={"title": "Gone", "body_md": "x", "course_id": course_id},
        ).json()["id"]
        deleted = client.delete(f"/api/v1/notes/{note_id}")
        item_id = deleted.json()["deleted_item_id"]

        purged = client.delete(f"/api/v1/deleted-items/{item_id}")
        assert purged.status_code == 204
        assert client.get("/api/v1/deleted-items").json() == []
        assert client.get(f"/api/v1/notes/{note_id}").status_code == 404
