import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, FastAPI]]:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            config_dir=tmp_path / "config",
            spa_dist=tmp_path / "no-spa",
            log_level="WARNING",
        )
    )
    with TestClient(app) as test_client:
        yield test_client, app


def make_course(client: TestClient, title: str) -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def fake_transport(html: str) -> httpx.BaseTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    return httpx.MockTransport(handler)


def test_import_url_creates_provenance_material(
    client: tuple[TestClient, FastAPI], monkeypatch: pytest.MonkeyPatch
) -> None:
    test_client, app = client
    course_id = make_course(test_client, "Web course")
    html = "<h1>Bayes rule</h1><p>Body text.</p>"
    app.state.search_transport = fake_transport(html)

    imported = test_client.post(
        "/api/v1/materials/import-url",
        json={"course_id": course_id, "url": "https://example.com/wiki/bayes"},
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["deduped"] is False
    material = body["material"]
    assert material["provenance"]["source"] == "web"
    assert material["provenance"]["url"] == "https://example.com/wiki/bayes"
    assert material["filename"].startswith("example.com")

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if (
            test_client.get(f"/api/v1/materials/{material['id']}").json()["material"]["status"]
            == "ready"
        ):
            break
    assert (
        test_client.get(f"/api/v1/materials/{material['id']}").json()["material"]["status"]
        == "ready"
    )
    extraction = test_client.get(f"/api/v1/materials/{material['id']}/extractions").json()
    assert extraction


def test_import_url_rejects_bad_input(client: tuple[TestClient, FastAPI]) -> None:
    test_client, _app = client
    course_id = make_course(test_client, "Web course 2")
    not_url = test_client.post(
        "/api/v1/materials/import-url",
        json={"course_id": course_id, "url": "ftp://example.com/x"},
    )
    assert not_url.status_code == 422


def test_import_url_reports_fetch_failure(
    client: tuple[TestClient, FastAPI], monkeypatch: pytest.MonkeyPatch
) -> None:
    test_client, app = client
    course_id = make_course(test_client, "Web course 3")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope", headers={"content-type": "text/html"})

    app.state.search_transport = httpx.MockTransport(handler)
    failed = test_client.post(
        "/api/v1/materials/import-url",
        json={"course_id": course_id, "url": "https://example.com/missing"},
    )
    assert failed.status_code == 422
    assert "404" in failed.json()["detail"]
