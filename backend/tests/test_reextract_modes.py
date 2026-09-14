import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import fitz
import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, TaskUnassigned
from app.core.config import Settings
from app.core.vocab import (
    EXTRACTION_MODES,
    ExtractionMode,
    MaterialKind,
    applicable_extraction_modes,
)
from app.main import create_app
from app.ocr.gateway_ocr import GatewayOcr


class BlockedFakeGateway(LLMGateway):
    """Fake gateway subclassing LLMGateway with an optional block-and-release call."""

    def __init__(self, response: str, error: Exception | None = None) -> None:
        super().__init__(session_factory=None)
        self.calls: list[list[Message]] = []
        self.response = response
        self.error = error
        self.entered = threading.Event()
        self.release = threading.Event()
        self._armed = False

    def arm(self) -> None:
        self._armed = True
        self.entered.clear()
        self.release.clear()

    def resolve(self, task: str, course_id: int | None = None) -> Any:
        raise TaskUnassigned(task)

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.calls.append(messages)
        if self._armed:
            self.entered.set()
            assert self.release.wait(30), "test never released the gateway"
            self._armed = False
        if self.error is not None:
            raise self.error
        return self.response


@contextmanager
def make_client(gateway: BlockedFakeGateway) -> Iterator[TestClient]:
    tmp = Path("/tmp") / f"ca-reextract-{int(time.time() * 1000) % 10_000_000}"
    settings = Settings(data_dir=tmp, log_level="WARNING")
    app = create_app(settings, gateway=gateway, ocr=GatewayOcr(gateway))
    with TestClient(app) as client:
        yield client


def wait_until(predicate: Callable[[], bool], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(
        f"condition not met within {timeout}s; last state: {predicate()!r}"
    )


def text_pdf(text: str = "Differentiation rules and the chain rule explained.") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return bytes(doc.tobytes())


def make_course(client: TestClient) -> int:
    created = client.post("/api/v1/courses", json={"title": "Modes"})
    assert created.status_code == 201
    return int(created.json()["id"])


def upload_pdf(
    client: TestClient,
    course_id: int,
    data: bytes,
    name: str = "notes.pdf",
) -> dict[str, Any]:
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (name, data, "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    result: dict[str, Any] = upload.json()
    return result


def wait_status(client: TestClient, material_id: int) -> str:
    def settled() -> bool:
        detail = client.get(f"/api/v1/materials/{material_id}")
        return detail.json()["material"]["status"] in ("ready", "failed")

    wait_until(settled)
    detail = client.get(f"/api/v1/materials/{material_id}")
    status = detail.json()["material"]["status"]
    assert isinstance(status, str) and status in ("ready", "failed")
    return status


def test_applicable_extraction_modes_matrix() -> None:
    assert applicable_extraction_modes(MaterialKind.PDF) == (
        ExtractionMode.AUTO,
        ExtractionMode.TEXT,
        ExtractionMode.OCR,
    )
    assert applicable_extraction_modes(MaterialKind.IMAGE) == (
        ExtractionMode.AUTO,
        ExtractionMode.OCR,
    )
    for kind in (
        MaterialKind.MD,
        MaterialKind.TXT,
        MaterialKind.DOCX,
        MaterialKind.PPTX,
        MaterialKind.EPUB,
        MaterialKind.HTML,
        MaterialKind.AUDIO,
        MaterialKind.VIDEO,
        MaterialKind.DOC,
    ):
        assert applicable_extraction_modes(kind) == (ExtractionMode.AUTO,)
    assert EXTRACTION_MODES == ("auto", "text", "ocr")


def test_reingest_forced_ocr_on_text_pdf() -> None:
    gateway = BlockedFakeGateway("```markdown\n# OCR page\n\n$e^{i\\pi} = -1$\n```")
    with make_client(gateway) as client:
        course_id = make_course(client)
        upload = upload_pdf(client, course_id, text_pdf())
        material = upload["material"]
        material_id = material["id"]
        assert wait_status(client, material_id) == "ready"
        assert material["reextract_modes"] == ["auto", "text", "ocr"]
        calls_before = len(gateway.calls)

        reingest = client.post(
            f"/api/v1/materials/{material_id}/reingest", json={"mode": "ocr"}
        )
        assert reingest.status_code == 200, reingest.text

        def settled_ocr() -> bool:
            detail = client.get(f"/api/v1/materials/{material_id}").json()
            extraction = detail.get("extraction")
            return extraction is not None and extraction["extractor"] == "ocr:forced"

        wait_until(settled_ocr)
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        assert detail["material"]["status"] == "ready"
        assert detail["extraction"]["extractor"] == "ocr:forced"
        assert "$e^{i\\pi} = -1$" in detail["extraction"]["markdown"]
        assert len(gateway.calls) >= calls_before + 1


def test_reingest_forced_text_on_text_pdf_is_free() -> None:
    gateway = BlockedFakeGateway("should never be used")
    with make_client(gateway) as client:
        course_id = make_course(client)
        upload = upload_pdf(client, course_id, text_pdf())
        material_id = upload["material"]["id"]
        assert wait_status(client, material_id) == "ready"
        assert len(gateway.calls) == 0

        version = client.get(f"/api/v1/materials/{material_id}").json()["extraction"]["version"]
        reingest = client.post(
            f"/api/v1/materials/{material_id}/reingest", json={"mode": "text"}
        )
        assert reingest.status_code == 200, reingest.text

        def settled_text() -> Callable[[], bool]:
            def check() -> bool:
                detail = client.get(f"/api/v1/materials/{material_id}").json()
                extraction = detail.get("extraction")
                return (
                    extraction is not None
                    and extraction["version"] > version
                    and extraction["extractor"] == "pymupdf:forced"
                )

            return check

        wait_until(settled_text(), timeout=30.0)
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        assert detail["material"]["status"] == "ready"
        assert detail["extraction"]["extractor"] == "pymupdf:forced"
        assert len(gateway.calls) == 0


@pytest.mark.parametrize(
    ("kind", "filename", "body", "mime"),
    [
        ("epub", "book.epub", b"epub-not-really", "application/epub+zip"),
        ("txt", "a.txt", b"plain text", "text/plain"),
    ],
)
def test_reingest_mode_not_applicable_is_422(
    kind: str, filename: str, body: bytes, mime: str
) -> None:
    gateway = BlockedFakeGateway("x")
    with make_client(gateway) as client:
        course_id = make_course(client)
        upload = client.post(
            "/api/v1/materials",
            params={"course_id": course_id},
            files={"file": (filename, body, mime)},
        )
        assert upload.status_code == 200, upload.text
        material_id = upload.json()["material"]["id"]
        wait_status(client, material_id)

        response = client.post(
            f"/api/v1/materials/{material_id}/reingest", json={"mode": "ocr"}
        )
        assert response.status_code == 422
        assert "allowed" in response.json()["detail"]


def test_reingest_unknown_mode_is_422() -> None:
    gateway = BlockedFakeGateway("x")
    with make_client(gateway) as client:
        course_id = make_course(client)
        upload = upload_pdf(client, course_id, text_pdf())
        material_id = upload["material"]["id"]
        response = client.post(
            f"/api/v1/materials/{material_id}/reingest", json={"mode": "smash"}
        )
        assert response.status_code == 422


def test_material_out_exposes_reextract_modes_by_kind() -> None:
    gateway = BlockedFakeGateway("note text")
    with make_client(gateway) as client:
        course_id = make_course(client)
        listing = client.post(
            "/api/v1/materials",
            params={"course_id": course_id},
            files={"file": ("board.png", b"\x89PNG-fake", "image/png")},
        )
        image_id = listing.json()["material"]["id"]
        wait_status(client, image_id)
        detail = client.get(f"/api/v1/materials/{image_id}").json()
        assert detail["material"]["reextract_modes"] == ["auto", "ocr"]


def test_openapi_schema_carries_reingest_options() -> None:
    gateway = BlockedFakeGateway("x")
    with make_client(gateway) as client:
        schema = client.get("/openapi.json").json()
        props = schema["components"]["schemas"]["MaterialOut"]["properties"]
        assert "reextract_modes" in props
        assert props["reextract_modes"]["type"] == "array"
        body_schema = schema["paths"]["/api/v1/materials/{material_id}/reingest"]["post"][
            "requestBody"
        ]["content"]["application/json"]["schema"]
        body_ref = body_schema["anyOf"][0]["$ref"]
        assert body_ref.endswith("ReingestOptionsIn")


def test_forced_ocr_cancels_between_pages() -> None:
    gateway = BlockedFakeGateway("page text")
    with make_client(gateway) as client:
        course_id = make_course(client)
        upload = upload_pdf(client, course_id, text_pdf())
        material_id = upload["material"]["id"]
        assert wait_status(client, material_id) == "ready"

        gateway.arm()
        reingest = client.post(
            f"/api/v1/materials/{material_id}/reingest", json={"mode": "ocr"}
        )
        assert reingest.status_code == 200
        job_id = reingest.json()["job_id"]
        assert gateway.entered.wait(30), "gateway never reached the OCR call"

        from app.jobs.cancellation import clear_cancel, request_cancel

        request_cancel(int(job_id))
        gateway.release.set()

        def job_status() -> str:
            jobs = client.get("/api/v1/jobs").json()
            entry = next(job for job in jobs if job["id"] == int(job_id))
            return str(entry["status"])

        wait_until(lambda: job_status() == "cancelled")
        clear_cancel(int(job_id))
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        assert detail["material"]["status"] != "failed"
