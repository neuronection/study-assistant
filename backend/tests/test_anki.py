import io
import zipfile
from typing import Any

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


class QuietGateway(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)
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
            external_id="quiet",
            label="quiet",
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
        return "ok"


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


def make_client() -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-anki-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=QuietGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def add_card(client: TestClient, course_id: int, front: str, back: str) -> None:
    created = client.post(
        "/api/v1/flashcards",
        json={
            "kind": "basic",
            "front_md": front,
            "back_md": back,
            "course_id": course_id,
        },
    )
    assert created.status_code == 201, created.text


def test_anki_export_import_round_trip() -> None:
    client = make_client()
    with client:
        course_id = make_course(client)
        add_card(client, course_id, "Derivative of $x^2$?", "$2x$")
        add_card(client, course_id, "Constant of integration?", "$+C$")

        exported = client.get("/api/v1/flashcards/export-anki")
        assert exported.status_code == 200
        assert exported.headers["content-disposition"].endswith('"flashcards.apkg"')
        package = exported.content
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            assert "collection.anki2" in archive.namelist()
            assert archive.read("media") == b"{}"

        imported = client.post(
            "/api/v1/flashcards/import-anki",
            params={"course_id": course_id},
            files={"file": ("deck.apkg", package, "application/octet-stream")},
        )
        assert imported.status_code == 201, imported.text
        result = imported.json()
        assert result["imported"] == 2
        assert result["skipped"] == 0

        listing = client.get("/api/v1/flashcards").json()
        anki_cards = [card for card in listing if card["source"] == "anki_import"]
        assert len(anki_cards) == 2
        assert {card["kind"] for card in anki_cards} == {"basic"}


def test_anki_import_rejects_non_apkg() -> None:
    client = make_client()
    with client:
        course_id = make_course(client)
        bad = client.post(
            "/api/v1/flashcards/import-anki",
            params={"course_id": course_id},
            files={"file": ("deck.txt", b"not a zip", "text/plain")},
        )
        assert bad.status_code == 422


def test_cloze_detected_on_import() -> None:
    client = make_client()
    with client:
        import sqlite3

        cloze_fields = "The {{c1::power rule}} gives 2x\x1fderivative rules"
        memory = sqlite3.connect(":memory:")
        memory.executescript(
            "CREATE TABLE notes (id integer primary key, flds text, tags text);"
            "CREATE TABLE col (decks text);"
            "INSERT INTO col VALUES ('{\"1\": {\"id\": 1, \"name\": \"Default\"}}');"
            f"INSERT INTO notes VALUES (1, '{cloze_fields}', '');"
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("collection.anki2", memory.serialize())
            archive.writestr("media", "{}")
        memory.close()

        imported = client.post(
            "/api/v1/flashcards/import-anki",
            params={"course_id": make_course(client)},
            files={"file": ("deck.apkg", buffer.getvalue(), "application/octet-stream")},
        )
        assert imported.status_code == 201
        listing = client.get("/api/v1/flashcards").json()
        assert listing[0]["kind"] == "cloze"
