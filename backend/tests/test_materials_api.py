import time
from collections.abc import Callable
from typing import Any

import fitz
import pytest
from fastapi.testclient import TestClient


def make_text_pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 14
    return bytes(doc.tobytes())


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


@pytest.fixture
def text_pdf() -> bytes:
    return make_text_pdf(
        [
            "The Chain Rule",
            "The chain rule states that the derivative of a composite",
            "function f(g(x)) equals f'(g(x)) g'(x). It is fundamental",
            "for differentiating nested expressions in calculus.",
        ]
    )


def make_course(client: TestClient, title: str = "Materials") -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def upload(
    client: TestClient, data: bytes, filename: str, course_id: int
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, data, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_upload_pdf_ingests_to_ready_and_searchable(client: TestClient, text_pdf: bytes) -> None:
    course_id = make_course(client)
    body = upload(client, text_pdf, "chain-rule.pdf", course_id)
    material_id = body["material"]["id"]
    assert body["deduped"] is False
    assert body["job_id"] is not None

    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )

    detail = client.get(f"/api/v1/materials/{material_id}").json()
    extraction = detail["extraction"]
    assert extraction is not None
    assert extraction["extractor"] == "pymupdf"
    assert "composite" in extraction["markdown"]
    assert detail["index_card"]["reading_minutes"] is not None

    search = client.get("/api/v1/search", params={"q": "composite"}).json()
    assert [hit["material_id"] for hit in search["hits"]] == [material_id]
    assert search["hits"][0]["snippet"]


def test_reupload_same_file_is_deduped(client: TestClient, text_pdf: bytes) -> None:
    course_id = make_course(client)
    first = upload(client, text_pdf, "chain-rule.pdf", course_id)
    second = upload(client, text_pdf, "chain-rule-renamed.pdf", course_id)
    assert second["deduped"] is True
    assert second["material"]["id"] == first["material"]["id"]
    assert second["job_id"] is None


def test_list_materials_scoped_to_profile(client: TestClient, text_pdf: bytes) -> None:
    course_id = make_course(client)
    upload(client, text_pdf, "one.pdf", course_id)
    upload(
        client,
        make_text_pdf(["Limits describe the behavior of functions."]),
        "two.pdf",
        course_id,
    )
    listing = client.get("/api/v1/materials").json()
    assert len(listing) == 2


def test_missing_material_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/materials/99999").status_code == 404


def test_empty_upload_rejected(client: TestClient) -> None:
    course_id = make_course(client)
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 422


def test_upload_requires_course(client: TestClient, text_pdf: bytes) -> None:
    response = client.post(
        "/api/v1/materials",
        files={"file": ("orphan.pdf", text_pdf, "application/pdf")},
    )
    assert response.status_code == 422


def test_upload_rejects_other_profile_course(client: TestClient, text_pdf: bytes) -> None:
    response = client.post(
        "/api/v1/materials",
        params={"course_id": 99999},
        files={"file": ("foreign.pdf", text_pdf, "application/pdf")},
    )
    assert response.status_code == 422
    assert "course not found" in response.json()["detail"]


def test_same_file_two_courses_two_materials(client: TestClient, text_pdf: bytes) -> None:
    first_course = make_course(client, "One")
    second_course = make_course(client, "Two")
    first = upload(client, text_pdf, "shared.pdf", first_course)
    second = upload(client, text_pdf, "shared.pdf", second_course)
    assert first["material"]["id"] != second["material"]["id"]
    assert second["deduped"] is False


def test_scanned_pdf_fails_with_clear_ocr_message(client: TestClient) -> None:
    course_id = make_course(client)
    doc = fitz.open()
    doc.new_page()
    blank_pdf = doc.tobytes()
    body = upload(client, blank_pdf, "scan.pdf", course_id)
    material_id = body["material"]["id"]
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "failed"
    )
    detail = client.get(f"/api/v1/materials/{material_id}").json()
    assert detail["extraction"] is None


def test_txt_material_ingests_native(client: TestClient) -> None:
    course_id = make_course(client)
    body = upload(client, b"integration by parts\n\nuse u substitution", "notes.txt", course_id)
    material_id = body["material"]["id"]
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )
    detail = client.get(f"/api/v1/materials/{material_id}").json()
    assert detail["extraction"]["extractor"] == "native"
    search = client.get("/api/v1/search", params={"q": "substitution"}).json()
    assert search["hits"]


def test_extraction_to_blocks_keeps_fences_whole() -> None:
    from app.services.materials import extraction_to_blocks

    markdown = (
        "# Partial fractions\n\n"
        "```mermaid\n"
        "flowchart TD\n\n"
        "    A[x^3 + 1] --> B[(x + 1)(x^2 - x + 1)]\n"
        "```\n\n"
        "after the diagram\n\n\n"
        "```python\nx = 1\n```\n"
    )
    blocks = extraction_to_blocks(markdown)
    assert blocks == [
        {"type": "text", "md": "# Partial fractions"},
        {
            "type": "text",
            "md": (
                "```mermaid\nflowchart TD\n\n"
                "    A[x^3 + 1] --> B[(x + 1)(x^2 - x + 1)]\n```"
            ),
        },
        {"type": "text", "md": "after the diagram"},
        {"type": "text", "md": "```python\nx = 1\n```"},
    ]


def test_extraction_to_blocks_plain_split_unchanged() -> None:
    from app.services.materials import extraction_to_blocks

    assert extraction_to_blocks("a\n\nb\n\n\nc") == [
        {"type": "text", "md": "a"},
        {"type": "text", "md": "b"},
        {"type": "text", "md": "c"},
    ]
