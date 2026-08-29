import base64
import json
import threading
import time
from datetime import UTC
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ProviderError, ResolvedModel
from app.core.config import Settings
from app.main import create_app

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-bytes"
OCR_MARKDOWN = "Differentiate $f(x) = x^2$:\n\n$$f'(x) = 2x$$"


class NotesGateway(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)
        self.calls: list[list[Message]] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="notes-model",
            label="notes-model",
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
        self.calls.append(messages)
        return self.responses.pop(0)


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


def make_client(
    responses: list[str], gateway: LLMGateway | None = None
) -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-notes-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway or NotesGateway(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def create_note(client: TestClient, title: str = "Derivatives", body: str = "") -> int:
    created = client.post(
        "/api/v1/notes",
        json={
            "title": title,
            "body_md": body,
            "course_id": make_course(client),
        },
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def wait_drawing_ocr(
    client: TestClient, note_id: int, min_version: int = 1
) -> dict[str, Any]:
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        detail: dict[str, Any] = client.get(f"/api/v1/notes/{note_id}").json()
        drawing: dict[str, Any] = detail["drawings"][0]
        if drawing["ocr_version"] >= min_version and drawing["ocr_markdown"]:
            return drawing
        time.sleep(0.05)
    raise AssertionError("drawing OCR did not finish")


def wait_failed_drawing_job(client: TestClient) -> dict[str, Any]:
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        jobs: list[dict[str, Any]] = client.get(
            "/api/v1/jobs", params={"type": "drawing_ocr"}
        ).json()
        failed = [job for job in jobs if job["status"] == "failed"]
        if failed:
            return failed[0]
        time.sleep(0.05)
    raise AssertionError("drawing OCR job never failed")


def add_drawing(client: TestClient, note_id: int, ocr: bool = True) -> Any:
    return client.post(
        f"/api/v1/notes/{note_id}/drawings",
        json={
            "strokes": [{"points": [[0, 0], [10, 10]], "width": 2}],
            "png_base64": base64.b64encode(PNG_BYTES).decode(),
            "ocr": ocr,
        },
    )


def test_note_crud_and_search() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Chain rule", "The chain rule: $(fg)' = f'g + fg'$")
        listing = client.get("/api/v1/notes", params={"q": "chain"})
        assert listing.status_code == 200
        assert [note["id"] for note in listing.json()["items"]] == [note_id]

        missing = client.get("/api/v1/notes", params={"q": "integral"})
        assert missing.json()["items"] == []

        typo = client.get("/api/v1/notes", params={"q": "chaen rule"})
        assert [note["id"] for note in typo.json()["items"]] == [note_id]

        updated = client.patch(
            f"/api/v1/notes/{note_id}", json={"pinned": True, "title": "Chain rule!"}
        )
        assert updated.status_code == 200
        assert updated.json()["pinned"] is True

        detail = client.get(f"/api/v1/notes/{note_id}")
        assert detail.json()["body"][0]["md"].startswith("The chain rule")

        deleted = client.delete(f"/api/v1/notes/{note_id}")
        assert deleted.status_code == 200
        assert client.get(f"/api/v1/notes/{note_id}").status_code == 404


def test_update_note_base_updated_at_guard() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Limits", "base body")
        first = client.get(f"/api/v1/notes/{note_id}").json()
        stale_base = first["updated_at"]

        ok = client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": "second body", "base_updated_at": stale_base},
        )
        assert ok.status_code == 200, ok.text
        fresh_base = ok.json()["updated_at"]
        assert fresh_base != stale_base

        conflict = client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": "third body", "base_updated_at": stale_base},
        )
        assert conflict.status_code == 409

        replay = client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": "third body", "base_updated_at": fresh_base},
        )
        assert replay.status_code == 200

        unguarded = client.patch(
            f"/api/v1/notes/{note_id}", json={"body_md": "force body"}
        )
        assert unguarded.status_code == 200
        assert client.get(f"/api/v1/notes/{note_id}").json()["body"][0]["md"] == (
            "force body"
        )

        bad = client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": "x", "base_updated_at": "not-a-date"},
        )
        assert bad.status_code == 422


def _backdate_latest_version(client: TestClient, note_id: int, minutes: int) -> None:
    from datetime import datetime, timedelta

    from app.domain.models import NoteVersion

    assert isinstance(client.app, FastAPI)
    with client.app.state.session_factory() as session:
        latest = (
            session.query(NoteVersion)
            .filter(NoteVersion.note_id == note_id)
            .order_by(NoteVersion.id.desc())
            .first()
        )
        assert latest is not None
        latest.created_at = datetime.now(UTC) - timedelta(minutes=minutes)
        session.commit()


def test_note_versions_coalesce_and_force() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Limits", "v0 body")

        first_patch = client.patch(
            f"/api/v1/notes/{note_id}", json={"body_md": "v1 body"}
        )
        assert first_patch.status_code == 200
        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) == 1
        assert versions[0]["cause"] == "autosave-coalesced"

        client.patch(f"/api/v1/notes/{note_id}", json={"body_md": "v2 body"})
        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) == 1

        _backdate_latest_version(client, note_id, minutes=15)
        client.patch(f"/api/v1/notes/{note_id}", json={"body_md": "v3 body"})
        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) == 2

        client.patch(
            f"/api/v1/notes/{note_id}", json={"body_md": "v4 body", "force_version": True}
        )
        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) == 3
        assert versions[0]["cause"] == "manual"

        title_only = client.patch(f"/api/v1/notes/{note_id}", json={"title": "Renamed"})
        assert title_only.status_code == 200
        assert len(client.get(f"/api/v1/notes/{note_id}/versions").json()) == 3


def test_note_version_restore_round_trip() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Series", "good body")
        client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": "bad body", "force_version": True},
        )
        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) == 1
        good_version = versions[0]["version_id"]

        detail = client.get(f"/api/v1/notes/{note_id}/versions/{good_version}")
        assert detail.status_code == 200
        assert detail.json()["body_md"] == "good body"

        missing = client.get(f"/api/v1/notes/{note_id}/versions/99999")
        assert missing.status_code == 404

        restored = client.post(
            f"/api/v1/notes/{note_id}/restore", json={"version_id": good_version}
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["body"][0]["md"] == "good body"

        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) == 2
        assert versions[0]["cause"] == "restore"

        bad_restore = client.post(
            f"/api/v1/notes/{note_id}/restore", json={"version_id": 99999}
        )
        assert bad_restore.status_code == 404


def test_note_versions_capped_at_50_and_cascade_on_delete() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Cap", "seed")
        for index in range(55):
            patched = client.patch(
                f"/api/v1/notes/{note_id}",
                json={"body_md": f"body {index}", "force_version": True},
            )
            assert patched.status_code == 200
        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) == 50
        assert versions[0]["title"] == "Cap"

        client.delete(f"/api/v1/notes/{note_id}")
        assert isinstance(client.app, FastAPI)
        with client.app.state.session_factory() as session:
            from sqlalchemy import select

            from app.domain.models import NoteVersion

            remaining = list(
                session.scalars(
                    select(NoteVersion).where(NoteVersion.note_id == note_id)
                )
            )
        assert remaining == []


def test_drawing_save_is_immediate_and_pending_state_serialized() -> None:
    class BlockingGateway(NotesGateway):
        def __init__(self, responses: list[str]) -> None:
            super().__init__(responses)
            self.started = threading.Event()
            self.release = threading.Event()

        def generate(
            self,
            task: str,
            messages: list[Message],
            model: Any = None,
            course_id: int | None = None,
        ) -> str:
            self.started.set()
            if not self.release.wait(timeout=10.0):
                raise AssertionError("gateway was never released")
            return super().generate(task, messages, model=model, course_id=course_id)

    gateway = BlockingGateway([OCR_MARKDOWN])
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-block-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    client = TestClient(app)
    with client:
        note_id = create_note(client, "Pending")
        added = add_drawing(client, note_id)
        assert added.status_code == 201, added.text
        drawing = added.json()["drawings"][0]
        assert drawing["ocr_version"] == 0
        assert drawing["ocr_markdown"] is None
        assert gateway.started.wait(timeout=5.0), "OCR job never started"

        detail = client.get(f"/api/v1/notes/{note_id}").json()
        pending = detail["drawings"][0]
        assert pending["ocr_markdown"] is None
        assert pending["ocr_job_id"] == drawing["ocr_job_id"]
        assert pending["ocr_job_id"] is not None

        conflict = client.post(f"/api/v1/notes/{note_id}/drawings/{drawing['id']}/reocr")
        assert conflict.status_code == 409

        gateway.release.set()
        finished = wait_drawing_ocr(client, note_id, 1)
        assert "2x" in finished["ocr_markdown"]

        settled = client.get(f"/api/v1/notes/{note_id}").json()["drawings"][0]
        assert settled["ocr_job_id"] is None

        reocr = client.post(f"/api/v1/notes/{note_id}/drawings/{drawing['id']}/reocr")
        assert reocr.status_code == 200, reocr.text
        assert reocr.json()["drawings"][0]["ocr_job_id"] is not None


def test_drawing_ocr_failure_is_a_retriable_job_not_a_502() -> None:
    class FailingGateway(NotesGateway):
        def generate(
            self,
            task: str,
            messages: list[Message],
            model: Any = None,
            course_id: int | None = None,
        ) -> str:
            resolved = ResolvedModel(
                provider_id=1,
                provider_type="openai_compatible",
                base_url="http://localhost/v1",
                external_id="m",
                label="m",
                caps=["text", "vision"],
                api_key=None,
            )
            raise ProviderError(resolved, "vision provider down")

    client = make_client([], gateway=FailingGateway([]))
    with client:
        note_id = create_note(client, "Fail")
        added = add_drawing(client, note_id)
        assert added.status_code == 201, added.text

        job = wait_failed_drawing_job(client)
        assert job["retriable"] is True
        assert "vision provider down" in job["error"]

        detail = client.get(f"/api/v1/notes/{note_id}").json()
        drawing = detail["drawings"][0]
        assert drawing["ocr_markdown"] is None
        assert drawing["ocr_job_id"] is None


def test_drawing_ocr_transcribes_and_is_searchable() -> None:
    client = make_client([OCR_MARKDOWN])
    with client:
        note_id = create_note(client, "Whiteboard")
        added = add_drawing(client, note_id)
        assert added.status_code == 201, added.text
        drawing = added.json()["drawings"][0]
        assert drawing["ocr_version"] == 0
        assert drawing["ocr_markdown"] is None

        finished = wait_drawing_ocr(client, note_id)
        assert "2x" in finished["ocr_markdown"]
        assert finished["ocr_job_id"] is None

        hits = client.get("/api/v1/notes", params={"q": "2x"})
        assert all(entry["tags"] == [] for entry in hits.json()["items"])
        assert [note["id"] for note in hits.json()["items"]] == [note_id]

        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, NotesGateway)
        user_message = gateway.calls[0][1]
        assert isinstance(user_message.content, list)
        assert any(getattr(part, "data", None) == PNG_BYTES for part in user_message.content)


def test_reocr_bumps_version() -> None:
    client = make_client([OCR_MARKDOWN, "Second pass $3x$"])
    with client:
        note_id = create_note(client, "Board")
        add_drawing(client, note_id)
        wait_drawing_ocr(client, note_id, 1)

        reocr = client.post(f"/api/v1/notes/{note_id}/drawings/1/reocr")
        assert reocr.status_code == 200, reocr.text
        drawing = wait_drawing_ocr(client, note_id, 2)
        assert "3x" in drawing["ocr_markdown"]


def test_update_drawing_replaces_strokes_and_reruns_ocr() -> None:
    client = make_client([OCR_MARKDOWN, "Edited pass $5x$"])
    with client:
        note_id = create_note(client, "Board")
        add_drawing(client, note_id)
        wait_drawing_ocr(client, note_id, 1)

        edited_png = PNG_BYTES + b"-edited"
        updated = client.put(
            f"/api/v1/notes/{note_id}/drawings/1",
            json={
                "strokes": [{"points": [[1, 1], [9, 9]], "width": 4}],
                "png_base64": base64.b64encode(edited_png).decode(),
                "ocr": True,
            },
        )
        assert updated.status_code == 200, updated.text
        drawing = updated.json()["drawings"][0]
        assert drawing["png_sha"] != "old"
        assert drawing["strokes"][0]["width"] == 4
        assert drawing["strokes"][0]["points"] == [[1, 1], [9, 9]]

        finished = wait_drawing_ocr(client, note_id, 2)
        assert "5x" in finished["ocr_markdown"]

        hits = client.get("/api/v1/notes", params={"q": "5x"})
        assert [note["id"] for note in hits.json()["items"]] == [note_id]


def test_update_drawing_without_ocr_clears_stale_text() -> None:
    client = make_client([OCR_MARKDOWN])
    with client:
        note_id = create_note(client, "Board")
        add_drawing(client, note_id)
        wait_drawing_ocr(client, note_id, 1)

        updated = client.put(
            f"/api/v1/notes/{note_id}/drawings/1",
            json={
                "strokes": [{"points": [[2, 2]], "width": 2}],
                "png_base64": base64.b64encode(PNG_BYTES).decode(),
                "ocr": False,
            },
        )
        assert updated.status_code == 200, updated.text
        drawing = updated.json()["drawings"][0]
        assert drawing["ocr_version"] == 0
        assert drawing["ocr_markdown"] is None

        hits = client.get("/api/v1/notes", params={"q": "2x"})
        assert hits.json()["items"] == []


def test_drawing_view_box_round_trip() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Board")
        created = client.post(
            f"/api/v1/notes/{note_id}/drawings",
            json={
                "strokes": [{"points": [[0, 0]], "width": 2}],
                "png_base64": base64.b64encode(PNG_BYTES).decode(),
                "ocr": False,
                "view": {"x": -12.5, "y": 40, "width": 300, "height": 160},
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["drawings"][0]["view"] == {
            "x": -12.5,
            "y": 40.0,
            "width": 300.0,
            "height": 160.0,
        }

        cleared = client.put(
            f"/api/v1/notes/{note_id}/drawings/1",
            json={
                "strokes": [{"points": [[0, 0]], "width": 2}],
                "png_base64": base64.b64encode(PNG_BYTES).decode(),
                "ocr": False,
            },
        )
        assert cleared.status_code == 200
        assert cleared.json()["drawings"][0]["view"] is None


def test_drawing_view_box_rejects_invalid() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Board")
        bad = client.post(
            f"/api/v1/notes/{note_id}/drawings",
            json={
                "strokes": [{"points": [[0, 0]], "width": 2}],
                "png_base64": base64.b64encode(PNG_BYTES).decode(),
                "ocr": False,
                "view": {"x": 0, "y": 0, "width": 0, "height": 10},
            },
        )
        assert bad.status_code == 422


def test_update_drawing_unknown_ids_rejected() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Board")
        client.post(
            f"/api/v1/notes/{note_id}/drawings",
            json={
                "strokes": [{"points": [[0, 0]], "width": 2}],
                "png_base64": base64.b64encode(PNG_BYTES).decode(),
                "ocr": False,
            },
        )
        payload = {
            "strokes": [{"points": [[0, 0]], "width": 2}],
            "png_base64": base64.b64encode(PNG_BYTES).decode(),
            "ocr": False,
        }
        missing_drawing = client.put(
            f"/api/v1/notes/{note_id}/drawings/99", json=payload
        )
        assert missing_drawing.status_code == 404
        missing_note = client.put("/api/v1/notes/99/drawings/1", json=payload)
        assert missing_note.status_code == 404
        bad_png = client.put(
            f"/api/v1/notes/{note_id}/drawings/1",
            json={
                "strokes": [{"points": [[0, 0]], "width": 2}],
                "png_base64": "!!!not-base64!!!",
                "ocr": False,
            },
        )
        assert bad_png.status_code == 422


def test_drawing_without_ocr_stored_cleanly() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Sketch only")
        added = client.post(
            f"/api/v1/notes/{note_id}/drawings",
            json={
                "strokes": [{"points": [[0, 0]], "width": 2}],
                "png_base64": base64.b64encode(PNG_BYTES).decode(),
                "ocr": False,
            },
        )
        assert added.status_code == 201
        drawing = added.json()["drawings"][0]
        assert drawing["ocr_version"] == 0
        assert drawing["ocr_markdown"] is None


def test_invalid_png_rejected() -> None:
    client: TestClient = make_client([])
    with client:
        note_id = create_note(client)
        added = client.post(
            f"/api/v1/notes/{note_id}/drawings",
            json={"strokes": [{"points": [[0, 0]]}], "png_base64": "!!!not-base64!!!"},
        )
        assert added.status_code == 422


def test_delete_drawing_removes_drawing_and_strips_inline_refs() -> None:
    client = make_client([OCR_MARKDOWN])
    with client:
        note_id = create_note(client, "Board")
        drawing_id = client.post(
            f"/api/v1/notes/{note_id}/drawings",
            json={
                "strokes": [{"points": [[0, 0]], "width": 2}],
                "png_base64": base64.b64encode(PNG_BYTES).decode(),
            },
        ).json()["drawings"][0]["id"]
        patched = client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": f"before\n\n![drawing](ca-drawing://{drawing_id})\n\nafter"},
        )
        assert patched.status_code == 200

        deleted = client.delete(f"/api/v1/notes/{note_id}/drawings/{drawing_id}")
        assert deleted.status_code == 200, deleted.text
        body = deleted.json()
        assert body["drawings"] == []
        assert body["body"] == [
            {"type": "text", "md": "before\n\n"},
            {"type": "text", "md": "\n\nafter"},
        ]

        hits = client.get("/api/v1/notes", params={"q": "2x"})
        assert hits.json()["items"] == []

        re_save = client.patch(
            f"/api/v1/notes/{note_id}", json={"body_md": "before\n\nafter"}
        )
        assert re_save.status_code == 200


def test_delete_drawing_unknown_ids_rejected() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Board")
        missing_drawing = client.delete(f"/api/v1/notes/{note_id}/drawings/99")
        assert missing_drawing.status_code == 404
        missing_note = client.delete("/api/v1/notes/99/drawings/1")
        assert missing_note.status_code == 404


def test_delete_drawing_unreferenced_drawing_dropped_from_search() -> None:
    client = make_client([OCR_MARKDOWN])
    with client:
        note_id = create_note(client, "Scratch")
        add_drawing(client, note_id)
        wait_drawing_ocr(client, note_id, 1)

        before = client.get("/api/v1/notes", params={"q": "2x"}).json()["items"]
        assert [note["id"] for note in before] == [note_id]

        deleted = client.delete(f"/api/v1/notes/{note_id}/drawings/1")
        assert deleted.status_code == 200
        assert deleted.json()["drawings"] == []

        after = client.get("/api/v1/notes", params={"q": "2x"}).json()["items"]
        assert after == []


def test_flashcards_from_note_share_search_text() -> None:
    client = make_client(
        [
            json.dumps(
                {
                    "cards": [
                        {
                            "kind": "basic",
                            "front_md": "State the chain rule.",
                            "back_md": "$(fg)' = f'g + fg'$",
                        }
                    ]
                }
            )
        ]
    )
    with client:
        note_id = create_note(client, "Rules", "The chain rule combines derivatives.")
        generated = client.post(
            "/api/v1/flashcards/generate",
            json={
                "source": "note",
                "note_id": note_id,
                "count": 1,
                "course_id": make_course(client),
            },
        )
        assert generated.status_code == 201, generated.text
        cards = generated.json()
        assert len(cards) == 1
        assert cards[0]["kind"] == "basic"
        assert cards[0]["source"] == "note"
        assert cards[0]["source_ref"] == f"note:{note_id}"

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            rows = db.execute(
                text("SELECT context_type FROM ai_interactions WHERE context_type = 'flashcards'")
            ).all()
        assert len(rows) == 1


def test_compose_note_creates_placed_note() -> None:
    client = make_client(
        [
            "# Limits\n\nThe limit of $f(x)$ as $x\\to a$ is $L$ if for every "
            "$\\epsilon>0$ there is a $\\delta>0$ such that "
            "$|f(x)-L|<\\epsilon$ whenever $0<|x-a|<\\delta$."
        ]
    )
    with client:
        course_id = make_course(client)
        composed = client.post(
            "/api/v1/notes/compose",
            json={
                "course_id": course_id,
                "title": "Limits note",
                "instructions": "epsilon-delta definition",
            },
        )
        assert composed.status_code == 201, composed.text
        body = composed.json()
        assert body["title"] == "Limits note"
        assert body["course_id"] == course_id
        assert body["node_id"] is not None
        assert "epsilon" in body["body"][0]["md"].lower()

        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        prompt = "\n".join(str(message.content) for message in gateway.calls[-1])
        assert "epsilon-delta definition" in prompt


def test_compose_note_rejects_missing_course() -> None:
    client = make_client([])
    with client:
        composed = client.post(
            "/api/v1/notes/compose", json={"course_id": 9999, "title": "X"}
        )
        assert composed.status_code == 422
