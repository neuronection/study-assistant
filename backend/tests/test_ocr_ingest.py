import contextlib
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import fitz
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, TaskUnassigned
from app.core.config import Settings
from app.main import create_app
from app.ocr.gateway_ocr import GatewayOcr


class FakeGateway(LLMGateway):
    def __init__(self, response: str, error: Exception | None = None) -> None:
        super().__init__(session_factory=None)
        self.response = response
        self.error = error
        self.calls: list[list[Message]] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> Any:
        raise TaskUnassigned(task)

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.response


@contextlib.contextmanager
def make_client(gateway: FakeGateway) -> Iterator[TestClient]:
    tmp = Path(tempfile.mkdtemp(prefix="ca-ocr-"))
    settings = Settings(data_dir=tmp, log_level="WARNING")
    app = create_app(settings, gateway=gateway, ocr=GatewayOcr(gateway))
    with TestClient(app) as client:
        yield client


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def make_course(client: TestClient) -> int:
    created = client.post("/api/v1/courses", json={"title": "OCR"})
    assert created.status_code == 201
    return int(created.json()["id"])


def blank_pdf(pages: int = 2) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    return bytes(doc.tobytes())


def test_scanned_pdf_goes_through_ocr_pipeline() -> None:
    gateway = FakeGateway(
        "```markdown\n# Scanned page\n\nThe **chain rule**: $f'(g(x))g'(x)$\n```"
    )
    with make_client(gateway) as client:
        upload = client.post(
            "/api/v1/materials",
            params={"course_id": make_course(client)},
            files={"file": ("scan.pdf", blank_pdf(2), "application/pdf")},
        )
        assert upload.status_code == 200
        material_id = upload.json()["material"]["id"]
        wait_until(
            lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
            in ("ready", "failed")
        )
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        assert detail["material"]["status"] == "ready"
        assert detail["extraction"]["extractor"] == "ocr"
        assert "# Scanned page" in detail["extraction"]["markdown"]
        assert "$f'(g(x))g'(x)$" in detail["extraction"]["markdown"]
        assert len(gateway.calls) == 2

        search = client.get("/api/v1/search", params={"q": "chain"}).json()
        assert search["hits"]


def test_image_material_uses_ocr() -> None:
    gateway = FakeGateway("whiteboard note: $$\\int x\\,dx = x^2/2 + C$$")
    with make_client(gateway) as client:
        upload = client.post(
            "/api/v1/materials",
            params={"course_id": make_course(client)},
            files={"file": ("board.png", b"\x89PNG-fake", "image/png")},
        )
        material_id = upload.json()["material"]["id"]
        wait_until(
            lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
            in ("ready", "failed")
        )
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        assert detail["material"]["status"] == "ready"
        assert detail["extraction"]["extractor"] == "ocr"
        assert "+ C" in detail["extraction"]["markdown"]


def test_unassigned_ocr_task_fails_material_with_clear_message() -> None:
    gateway = FakeGateway("", error=TaskUnassigned("ocr"))
    with make_client(gateway) as client:
        upload = client.post(
            "/api/v1/materials",
            params={"course_id": make_course(client)},
            files={"file": ("scan.pdf", blank_pdf(1), "application/pdf")},
        )
        material_id = upload.json()["material"]["id"]
        wait_until(
            lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
            == "failed"
        )
        listing = client.get("/api/v1/materials")
        assert listing.status_code == 200
