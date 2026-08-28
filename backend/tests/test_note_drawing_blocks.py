import base64
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png"


class Scripted(LLMGateway):
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


def make_client(responses: list[str] | None = None, tmp: Any = None) -> TestClient:
    import tempfile
    from pathlib import Path

    data_dir = Path(tmp) if tmp else Path(tempfile.mkdtemp(prefix="ca-drawblocks-"))
    app = create_app(
        Settings(data_dir=data_dir, log_level="WARNING"),
        gateway=Scripted(responses or []),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def add_drawing(client: TestClient, note_id: int) -> int:
    added = client.post(
        f"/api/v1/notes/{note_id}/drawings",
        json={
            "strokes": [{"points": [[0, 0], [10, 10]], "width": 2, "color": "#1a1a1a"}],
            "png_base64": base64.b64encode(PNG_BYTES).decode(),
            "ocr": False,
        },
    )
    assert added.status_code == 201, added.text
    return int(added.json()["drawings"][-1]["id"])


def set_drawing_ocr(client: TestClient, note_id: int, drawing_id: int, markdown: str) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as session:
        from app.domain.models import NoteDrawing

        drawing = session.get(NoteDrawing, drawing_id)
        assert drawing is not None
        drawing.ocr_markdown = markdown
        drawing.ocr_blocks = [{"type": "text", "md": markdown}]
        drawing.ocr_version = 1
        session.commit()


def test_body_md_round_trip_is_lossless(tmp_path: Any) -> None:
    client = make_client(tmp=tmp_path)
    with client:
        course_id = client.post(
            "/api/v1/courses", json={"title": "Course"}
        ).json()["id"]
        note_id = client.post(
            "/api/v1/notes",
            json={"title": "Lossless", "body_md": "seed", "course_id": course_id},
        ).json()["id"]
        first = add_drawing(client, note_id)
        second = add_drawing(client, note_id)

        cases = [
            "para one\n\npara two\n\n\n\npara three",
            "\n\nleading blank lines\n\nbody",
            "body with trailing\n\n\n",
            "only text\n\nsecond",
            f"text\n\n![drawing](ca-drawing://{first})\n\n![drawing](ca-drawing://{second})",
            f"start\n\n![drawing](ca-drawing://{first})\n\nmid\n\n\n![drawing](ca-drawing://{second})\ntail\n",
        ]
        for body_md in cases:
            patched = client.patch(
                f"/api/v1/notes/{note_id}", json={"body_md": body_md}
            )
            assert patched.status_code == 200, patched.text
            blocks = patched.json()["body"]
            assert _blocks_md(blocks) == body_md

        detail = client.get(f"/api/v1/notes/{note_id}").json()
        assert _blocks_md(detail["body"]) == cases[-1]


def _blocks_md(blocks: object) -> str:
    from app.api.notes import _blocks_md as join

    return join(blocks)  # type: ignore[arg-type]


def test_legacy_stripped_blocks_rejoin_unchanged(tmp_path: Any) -> None:
    from app.api.notes import _blocks_md

    legacy: list[dict[str, Any]] = [
        {"type": "text", "md": "before"},
        {"type": "drawing", "drawing_id": 1},
        {"type": "text", "md": "after"},
    ]
    assert _blocks_md(legacy) == "before\n\n![drawing](ca-drawing://1)\n\nafter"
    assert _blocks_md([{"type": "text", "md": "only"}]) == "only"
    assert _blocks_md(None) == ""


def test_body_md_parses_into_interleaved_blocks(tmp_path: Any) -> None:
    client = make_client(tmp=tmp_path)
    with client:
        course_id = client.post(
            "/api/v1/courses", json={"title": "Course"}
        ).json()["id"]
        note_id = client.post(
            "/api/v1/notes",
            json={"title": "Derivations", "body_md": "start", "course_id": course_id},
        ).json()["id"]
        drawing_id = add_drawing(client, note_id)

        patched = client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": f"before\n\n![drawing](ca-drawing://{drawing_id})\n\nafter"},
        )
        assert patched.status_code == 200, patched.text
        body = patched.json()["body"]
        assert body == [
            {"type": "text", "md": "before\n\n"},
            {"type": "drawing", "drawing_id": drawing_id},
            {"type": "text", "md": "\n\nafter"},
        ]

        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) == 1
        detail = client.get(f"/api/v1/notes/{note_id}/versions/{versions[0]['version_id']}")
        assert detail.json()["body_md"] == "start"

        restored = client.post(
            f"/api/v1/notes/{note_id}/restore",
            json={"version_id": versions[0]["version_id"]},
        )
        assert restored.status_code == 200
        assert restored.json()["body"] == [{"type": "text", "md": "start"}]

        unknown = client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": "![drawing](ca-drawing://999)"},
        )
        assert unknown.status_code == 422
        assert "999" in unknown.json()["detail"]

        still_there = client.get(f"/api/v1/notes/{note_id}").json()
        assert still_there["body"] == [{"type": "text", "md": "start"}]


def test_context_resolver_renders_drawings_in_position(tmp_path: Any) -> None:
    client = make_client(tmp=tmp_path)
    with client:
        course_id = client.post(
            "/api/v1/courses", json={"title": "Course"}
        ).json()["id"]
        note_id = client.post(
            "/api/v1/notes",
            json={"title": "Sketches", "body_md": "intro", "course_id": course_id},
        ).json()["id"]
        inline_id = add_drawing(client, note_id)
        card_id = add_drawing(client, note_id)
        set_drawing_ocr(client, note_id, inline_id, "$f'(x) = 2x$")
        set_drawing_ocr(client, note_id, card_id, "unreferenced note")

        patched = client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": f"intro\n\n![drawing](ca-drawing://{inline_id})\n\noutro"},
        )
        assert patched.status_code == 200

        preview = client.post(
            "/api/v1/ai/context/preview",
            json={"course_id": course_id, "note_ids": [note_id]},
        )
        assert preview.status_code == 200, preview.text
        rendered = preview.json()["rendered"]
        assert "intro" in rendered
        assert "f'(x) = 2x" in rendered
        assert "outro" in rendered
        assert "unreferenced note" in rendered
        assert rendered.index("intro") < rendered.index("f'(x) = 2x")
        assert rendered.index("f'(x) = 2x") < rendered.index("outro")


def test_search_includes_inline_drawing_refs_harmlessly(tmp_path: Any) -> None:
    client = make_client(tmp=tmp_path)
    with client:
        course_id = client.post(
            "/api/v1/courses", json={"title": "Course"}
        ).json()["id"]
        note_id = client.post(
            "/api/v1/notes",
            json={"title": "Notes", "body_md": "plain", "course_id": course_id},
        ).json()["id"]
        drawing_id = add_drawing(client, note_id)
        patched = client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": f"text\n\n![drawing](ca-drawing://{drawing_id})"},
        )
        assert patched.status_code == 200
        hits = client.get("/api/v1/notes", params={"q": "text"})
        assert [note["id"] for note in hits.json()["items"]] == [note_id]
