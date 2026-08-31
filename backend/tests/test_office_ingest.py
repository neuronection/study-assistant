import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "convert"

PENGUIN_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
IMAGE_OCR_TEXT = "Figure 1: unit circle diagram"


class ConvertGateway(LLMGateway):
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


@pytest.fixture
def convert_client(tmp_path: Path) -> Iterator[tuple[TestClient, list[str]]]:
    gateway = ConvertGateway([])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway.responses


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Office"}).json()["id"])


def wait_ready(client: TestClient, material_id: int) -> dict[str, Any]:
    detail: dict[str, Any] = {}
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        status = detail["material"]["status"]
        if status == "ready":
            return detail
        assert status != "failed", detail
        time.sleep(0.05)
    raise AssertionError("material never became ready")


def upload(client: TestClient, course_id: int, filename: str, data: bytes) -> int:
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, data)},
    )
    assert response.status_code == 200, response.text
    return int(response.json()["material"]["id"])


def test_docx_ingests_via_converter(convert_client: tuple[TestClient, list[str]]) -> None:
    client, _responses = convert_client
    course_id = make_course(client)
    material_id = upload(
        client, course_id, "handout.docx", (FIXTURES / "handout.docx").read_bytes()
    )
    detail = wait_ready(client, material_id)
    markdown = detail["extraction"]["markdown"]
    assert "# Integration Techniques" in markdown
    assert "Substitution and integration by parts" in markdown
    assert detail["material"]["provenance"]["source"] == "converted"
    assert detail["material"]["provenance"]["converter"] == "docx"

    search = client.get("/api/v1/search", params={"course_id": course_id, "q": "workhorses"})
    assert search.status_code == 200
    assert any(hit["material_id"] == material_id for hit in search.json()["hits"])


def test_pptx_slides_notes_and_order(convert_client: tuple[TestClient, list[str]]) -> None:
    client, _responses = convert_client
    course_id = make_course(client)
    material_id = upload(
        client, course_id, "deck.pptx", (FIXTURES / "deck.pptx").read_bytes()
    )
    detail = wait_ready(client, material_id)
    markdown = detail["extraction"]["markdown"]
    assert "## Slide 1 — The Chain Rule" in markdown
    assert "f(g(x))" in markdown
    assert "> Emphasize the inner derivative." in markdown
    assert detail["material"]["provenance"]["converter"] == "pptx"


def test_epub_spine_order_and_chapters(
    convert_client: tuple[TestClient, list[str]],
) -> None:
    client, _responses = convert_client
    course_id = make_course(client)
    material_id = upload(
        client, course_id, "book.epub", (FIXTURES / "book.epub").read_bytes()
    )
    detail = wait_ready(client, material_id)
    markdown = detail["extraction"]["markdown"]
    assert "# Limits" in markdown
    assert "function approaches" in markdown
    assert detail["material"]["provenance"]["converter"] == "epub"


def test_html_material_converts_with_table_and_math_placeholder(
    convert_client: tuple[TestClient, list[str]],
) -> None:
    client, _responses = convert_client
    course_id = make_course(client)
    material_id = upload(
        client, course_id, "lecture.html", (FIXTURES / "lecture.html").read_bytes()
    )
    detail = wait_ready(client, material_id)
    markdown = detail["extraction"]["markdown"]
    assert "# Derivatives" in markdown
    assert "| Function | Derivative |" in markdown
    assert "[math-block]" in markdown
    assert detail["material"]["provenance"]["converter"] == "html"


def test_html_data_uri_images_become_ocr_jobs(
    convert_client: tuple[TestClient, list[str]],
) -> None:
    client, responses = convert_client
    responses.append(IMAGE_OCR_TEXT)
    course_id = make_course(client)
    html = f"<html><body><h1>Trig</h1><img src=\"{PENGUIN_PNG}\" alt=\"unit circle\"></body></html>"
    material_id = upload(client, course_id, "trig.html", html.encode("utf-8"))
    detail = wait_ready(client, material_id)
    markdown = detail["extraction"]["markdown"]
    assert "ca-image://" in markdown
    assert len(detail["images"]) == 1
    image = detail["images"][0]

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        refreshed = client.get(f"/api/v1/materials/{material_id}").json()
        current = refreshed["images"][0]
        if current["ocr_version"] >= 1 and current["ocr_job_id"] is None:
            assert current["ocr_markdown"] == IMAGE_OCR_TEXT
            break
        time.sleep(0.05)
    else:
        raise AssertionError("image_ocr never completed for the embedded image")

    search = client.get("/api/v1/search", params={"course_id": course_id, "q": "unit circle"})
    assert any(hit["material_id"] == material_id for hit in search.json()["hits"])
    del image
