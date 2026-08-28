import base64
from typing import Any

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-bytes"
OCR_MARKDOWN = "Handwritten: $f'(x) = 2x$ and a note about limits"


class MaterialDrawingGateway(LLMGateway):
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

    data_dir = Path(tmp) if tmp else Path(tempfile.mkdtemp(prefix="ca-matdraw-"))
    app = create_app(
        Settings(data_dir=data_dir, log_level="WARNING"),
        gateway=MaterialDrawingGateway(responses or []),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def wait_ready(client: TestClient, material_id: int) -> None:
    import time

    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        if detail["material"]["status"] == "ready":
            return
        time.sleep(0.05)
    raise AssertionError("material did not reach ready")


def create_text_material(client: TestClient, course_id: int) -> int:
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("notes.txt", b"Integration by parts and limits.", "text/plain")},
    )
    assert response.status_code == 200, response.text
    material_id = int(response.json()["material"]["id"])
    wait_ready(client, material_id)
    return material_id


def make_drawing(client: TestClient, material_id: int, ocr: bool = True) -> int:
    response = client.post(
        f"/api/v1/materials/{material_id}/drawings",
        json={
            "strokes": [{"points": [[0, 0], [10, 10]], "width": 2}],
            "png_base64": base64.b64encode(PNG_BYTES).decode(),
            "ocr": ocr,
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["drawings"][-1]["id"])


def test_material_drawing_created_with_ocr_and_searchable() -> None:
    client = make_client([OCR_MARKDOWN])
    with client:
        course_id = client.post("/api/v1/courses", json={"title": "C"}).json()["id"]
        material_id = create_text_material(client, course_id)
        drawing_id = make_drawing(client, material_id)
        assert drawing_id > 0

        detail = client.get(f"/api/v1/materials/{material_id}").json()
        drawing = detail["drawings"][0]
        assert drawing["id"] == drawing_id
        assert drawing["ocr_version"] == 1
        assert "2x" in drawing["ocr_markdown"]

        hits = client.get("/api/v1/search", params={"q": "2x"}).json()["hits"]
        assert [hit["material_id"] for hit in hits] == [material_id]


def test_material_drawing_without_ocr_stored_cleanly_and_update_reruns() -> None:
    client = make_client(["Edited pass $5x$"])
    with client:
        course_id = client.post("/api/v1/courses", json={"title": "C"}).json()["id"]
        material_id = create_text_material(client, course_id)
        make_drawing(client, material_id, ocr=False)
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        drawing = detail["drawings"][0]
        assert drawing["ocr_version"] == 0
        assert drawing["ocr_markdown"] is None

        updated_png = PNG_BYTES + b"-edited"
        updated = client.put(
            f"/api/v1/materials/{material_id}/drawings/{drawing['id']}",
            json={
                "strokes": [{"points": [[1, 1], [9, 9]], "width": 4}],
                "png_base64": base64.b64encode(updated_png).decode(),
                "ocr": True,
            },
        )
        assert updated.status_code == 200, updated.text
        drawing = updated.json()["drawings"][0]
        assert drawing["ocr_version"] == 1
        assert "5x" in drawing["ocr_markdown"]

        hits = client.get("/api/v1/search", params={"q": "5x"}).json()["hits"]
        assert [hit["material_id"] for hit in hits] == [material_id]


def test_material_drawing_view_box_round_trip() -> None:
    client = make_client([])
    with client:
        course_id = client.post("/api/v1/courses", json={"title": "C"}).json()["id"]
        material_id = create_text_material(client, course_id)
        response = client.post(
            f"/api/v1/materials/{material_id}/drawings",
            json={
                "strokes": [{"points": [[0, 0], [10, 10]], "width": 2}],
                "png_base64": base64.b64encode(PNG_BYTES).decode(),
                "ocr": False,
                "view": {"x": 8, "y": -3, "width": 220, "height": 90},
            },
        )
        assert response.status_code == 201, response.text
        drawing = response.json()["drawings"][-1]
        assert drawing["view"] == {
            "x": 8.0,
            "y": -3.0,
            "width": 220.0,
            "height": 90.0,
        }

        updated = client.put(
            f"/api/v1/materials/{material_id}/drawings/{drawing['id']}",
            json={
                "strokes": [{"points": [[0, 0], [10, 10]], "width": 2}],
                "png_base64": base64.b64encode(PNG_BYTES).decode(),
                "ocr": False,
                "view": {"x": 0, "y": 0, "width": 50, "height": 50},
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["drawings"][0]["view"] == {
            "x": 0.0,
            "y": 0.0,
            "width": 50.0,
            "height": 50.0,
        }


def test_material_drawing_reocr_bumps_version() -> None:
    client = make_client([OCR_MARKDOWN, "Second pass $3x$"])
    with client:
        course_id = client.post("/api/v1/courses", json={"title": "C"}).json()["id"]
        material_id = create_text_material(client, course_id)
        drawing_id = make_drawing(client, material_id)
        reocr = client.post(f"/api/v1/materials/{material_id}/drawings/{drawing_id}/reocr")
        assert reocr.status_code == 200, reocr.text
        drawing = reocr.json()["drawings"][0]
        assert drawing["ocr_version"] == 2
        assert "3x" in drawing["ocr_markdown"]


def test_extraction_save_rejects_unknown_drawing_refs() -> None:
    client = make_client([OCR_MARKDOWN])
    with client:
        course_id = client.post("/api/v1/courses", json={"title": "C"}).json()["id"]
        material_id = create_text_material(client, course_id)
        rejected = client.patch(
            f"/api/v1/materials/{material_id}/extraction",
            json={"markdown": "![drawing](ca-drawing://999)"},
        )
        assert rejected.status_code == 422
        assert "999" in rejected.json()["detail"]


def test_delete_drawing_strips_inline_refs_and_search() -> None:
    client = make_client([OCR_MARKDOWN])
    with client:
        course_id = client.post("/api/v1/courses", json={"title": "C"}).json()["id"]
        material_id = create_text_material(client, course_id)
        drawing_id = make_drawing(client, material_id)
        patched = client.patch(
            f"/api/v1/materials/{material_id}/extraction",
            json={"markdown": f"before\n\n![drawing](ca-drawing://{drawing_id})\n\nafter"},
        )
        assert patched.status_code == 200, patched.text
        assert any(
            block.get("type") == "drawing" for block in patched.json()["blocks"]
        )

        deleted = client.delete(f"/api/v1/materials/{material_id}/drawings/{drawing_id}")
        assert deleted.status_code == 200, deleted.text
        body = deleted.json()
        assert body["drawings"] == []
        assert not any(
            block.get("type") == "drawing" for block in body["extraction"]["blocks"]
        )
        assert "ca-drawing://" not in body["extraction"]["markdown"]

        hits = client.get("/api/v1/search", params={"q": "2x"}).json()["hits"]
        assert hits == []


def test_delete_drawing_unknown_ids_rejected() -> None:
    client = make_client([])
    with client:
        course_id = client.post("/api/v1/courses", json={"title": "C"}).json()["id"]
        material_id = create_text_material(client, course_id)
        missing_drawing = client.delete(f"/api/v1/materials/{material_id}/drawings/99")
        assert missing_drawing.status_code == 404
        missing_material = client.delete("/api/v1/materials/99/drawings/1")
        assert missing_material.status_code == 404
        bad_png = client.post(
            f"/api/v1/materials/{material_id}/drawings",
            json={"strokes": [{"points": [[0, 0]]}], "png_base64": "!!!bad!!!"},
        )
        assert bad_png.status_code == 422


def test_derive_copies_drawings_and_remaps_refs(tmp_path: Any) -> None:
    client = make_client([OCR_MARKDOWN])
    with client:
        course_id = client.post("/api/v1/courses", json={"title": "C"}).json()["id"]
        material_id = create_text_material(client, course_id)
        drawing_id = make_drawing(client, material_id)
        patched = client.patch(
            f"/api/v1/materials/{material_id}/extraction",
            json={"markdown": f"intro\n\n![drawing](ca-drawing://{drawing_id})\n\noutro"},
        )
        assert patched.status_code == 200

        derived = client.post(f"/api/v1/materials/{material_id}/derive", json={})
        assert derived.status_code == 201, derived.text
        derived_id = derived.json()["material"]["id"]
        assert derived_id != material_id
        wait_ready(client, derived_id)

        source = client.get(f"/api/v1/materials/{material_id}").json()
        assert len(source["drawings"]) == 1
        assert f"ca-drawing://{drawing_id}" in source["extraction"]["markdown"]

        target = client.get(f"/api/v1/materials/{derived_id}").json()
        assert len(target["drawings"]) == 1
        derived_drawing_id = target["drawings"][0]["id"]
        assert f"ca-drawing://{derived_drawing_id}" in target["extraction"]["markdown"]
        assert "ca-drawing://" not in target["extraction"]["markdown"].replace(
            f"ca-drawing://{derived_drawing_id}", ""
        )
