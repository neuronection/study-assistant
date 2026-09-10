import time
from collections.abc import Callable
from typing import Any
from weakref import WeakKeyDictionary

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel, TaskUnassigned
from app.core.config import Settings
from app.main import create_app


class UnassignedGateway(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        raise TaskUnassigned(task)

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        raise TaskUnassigned(task)


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]]:
        self.calls.append(texts)
        return (
            "fake-embedding-model",
            [[1.0, 0.0] if "substitution" in text.lower() else [0.0, 1.0] for text in texts],
        )


class FakeDescriber:
    def __init__(self) -> None:
        self.called = False

    def describe(
        self,
        title: str,
        markdown: str,
        course_id: int | None = None,
    ) -> dict[str, Any] | None:
        self.called = True
        return {
            "summary": "Covers u-substitution as the inverse of the chain rule.",
            "topics": ["integration", "chain rule"],
            "key_terms": ["u-substitution", "antiderivative"],
            "difficulty": 3,
        }


def make_client(
    embedder: Any | None = None, describer: Any | None = None
) -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-edit-"))
    settings = Settings(data_dir=tmp, log_level="WARNING")
    app = create_app(
        settings,
        gateway=UnassignedGateway(),
        embedder=embedder,
        describer=describer,
    )
    return TestClient(app)


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


_COURSES: WeakKeyDictionary[TestClient, int] = WeakKeyDictionary()


def course_for(client: TestClient) -> int:
    if client not in _COURSES:
        created = client.post("/api/v1/courses", json={"title": "Edits"})
        assert created.status_code == 201
        _COURSES[client] = int(created.json()["id"])
    return _COURSES[client]


def upload_txt(client: TestClient, content: bytes, filename: str) -> int:
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_for(client)},
        files={"file": (filename, content, "text/plain")},
    )
    assert upload.status_code == 200
    material_id: int = upload.json()["material"]["id"]
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )
    return material_id


CONTENT = (
    "Integration by substitution\n\nSubstitution reverses the chain rule "
    "for antiderivatives and simplifies many integrals."
)


def test_edit_extraction_creates_version_and_updates_search(client: TestClient) -> None:
    material_id = upload_txt(client, CONTENT.encode(), "integr.txt")
    detail = client.get(f"/api/v1/materials/{material_id}").json()
    assert detail["extraction"]["version"] == 1

    edited = client.patch(
        f"/api/v1/materials/{material_id}/extraction",
        json={"markdown": "Quantum tunneling effect explained with barriers"},
    )
    assert edited.status_code == 200
    assert edited.json()["version"] == 2

    detail = client.get(f"/api/v1/materials/{material_id}").json()
    assert detail["extraction"]["version"] == 2
    assert "Quantum tunneling" in detail["extraction"]["markdown"]

    found_quantum = client.get("/api/v1/search", params={"q": "tunneling"}).json()
    assert [hit["material_id"] for hit in found_quantum["hits"]] == [material_id]
    found_old = client.get("/api/v1/search", params={"q": "substitution"}).json()
    assert found_old["hits"] == []

    empty = client.patch(
        f"/api/v1/materials/{material_id}/extraction", json={"markdown": "  "}
    )
    assert empty.status_code == 422


def test_blob_endpoint_serves_original(client: TestClient) -> None:
    material_id = upload_txt(client, CONTENT.encode(), "integr.txt")
    detail = client.get(f"/api/v1/materials/{material_id}").json()
    sha = detail["material"]["blob_sha"]
    assert sha is not None

    response = client.get(f"/api/v1/blobs/{sha}")
    assert response.status_code == 200
    assert response.content == CONTENT.encode()
    assert response.headers["content-disposition"] == "inline"

    assert client.get("/api/v1/blobs/not-a-sha").status_code == 422
    assert client.get(f"/api/v1/blobs/{'0' * 64}").status_code == 404


def test_hybrid_search_uses_vectors_when_fts_misses() -> None:
    embedder = FakeEmbedder()
    with make_client(embedder=embedder) as client:
        material_id = upload_txt(client, CONTENT.encode(), "integr.txt")
        wait_until(lambda: len(embedder.calls) >= 1)

        fts_miss = client.get("/api/v1/search", params={"q": "reverse chain technique"}).json()
        assert fts_miss["hits"]
        assert fts_miss["hits"][0]["material_id"] == material_id
        assert fts_miss["hits"][0]["score"] is not None


def test_postprocess_fills_index_card_via_describer() -> None:
    describer = FakeDescriber()
    with make_client(describer=describer) as client:
        material_id = upload_txt(client, CONTENT.encode(), "integr.txt")
        wait_until(
            lambda: (
                client.get(f"/api/v1/materials/{material_id}").json()["index_card"] or {}
            ).get("summary")
            is not None,
            timeout=20.0,
        )
        card = client.get(f"/api/v1/materials/{material_id}").json()["index_card"]
        assert "substitution" in card["summary"]
        assert card["topics"] == ["integration", "chain rule"]
        assert card["difficulty"] == 3
