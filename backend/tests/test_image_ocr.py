import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.domain.models import MaterialImage
from app.jobs.payloads import ImageOcrPayload
from app.main import create_app

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-bytes"
OCR_MARKDOWN = "Figure 1: the chain rule diagram"


class MaterialImageGateway(LLMGateway):
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
def client(tmp_path: Path) -> Iterator[tuple[TestClient, list[str]]]:
    gateway = MaterialImageGateway([])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway.responses


def test_converted_material_purge_cascades_images(client: tuple[TestClient, list[str]]) -> None:
    test_client, _responses = client
    course_id = test_client.post("/api/v1/courses", json={"title": "Img purge"}).json()["id"]
    upload = test_client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("notes.txt", b"plain text body", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    material_id = upload.json()["material"]["id"]

    app = test_client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as db:
        stored = app.state.blobs.put(PNG_BYTES, mime="image/png", session=db)
        db.add(MaterialImage(material_id=material_id, position=0, blob_sha=stored.sha256))
        db.commit()

    deleted = test_client.delete(f"/api/v1/materials/{material_id}")
    assert deleted.status_code == 204

    with app.state.session_factory() as db:
        from sqlalchemy import select

        assert db.scalars(select(MaterialImage)).all() == []


def test_image_ocr_job_transcribes_and_joins_fts(
    client: tuple[TestClient, list[str]],
) -> None:
    test_client, responses = client
    responses.append(OCR_MARKDOWN)
    course_id = test_client.post("/api/v1/courses", json={"title": "Img ocr"}).json()["id"]
    upload = test_client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("handout.txt", b"handout text about the chain rule", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    material_id = upload.json()["material"]["id"]

    app = test_client.app
    assert isinstance(app, FastAPI)
    from app.domain.models import Material
    from app.jobs.runner import JobRunner

    with app.state.session_factory() as db:
        stored = app.state.blobs.put(PNG_BYTES, mime="image/png", session=db)
        image = MaterialImage(material_id=material_id, position=1, blob_sha=stored.sha256)
        db.add(image)
        db.flush()
        image_id = image.id
        job = JobRunner.enqueue(
            db,
            "image_ocr",
            cast(ImageOcrPayload, {"image_id": image_id, "material_id": material_id}),
        )
        db.commit()
    app.state.jobs.wake()

    deadline = time.monotonic() + 10
    status = None
    while time.monotonic() < deadline:
        with app.state.session_factory() as db:
            db.expire_all()
            row = db.get(MaterialImage, image_id)
            status = db.get(Material, material_id).status
            if row is not None and row.ocr_version >= 1 and row.ocr_job_id is None:
                assert row.ocr_markdown == OCR_MARKDOWN
                break
        time.sleep(0.05)
    else:
        raise AssertionError("image_ocr job never completed")

    del job, status
    search = test_client.get(
        "/api/v1/search", params={"course_id": course_id, "q": "chain rule diagram"}
    )
    assert search.status_code == 200
