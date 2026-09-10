import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel, TaskUnassigned
from app.core.config import Settings
from app.main import create_app

REVIEW_JSON = json.dumps(
    {
        "findings": [
            {
                "kind": "coverage",
                "title": "Chain rule section has no material",
                "detail": "The section teaches the chain rule but nothing is assigned",
                "suggestion": "Assign the chain-rule notes",
            },
            {"kind": "nonsense", "title": "dropped", "detail": "", "suggestion": ""},
            {
                "kind": "gap",
                "title": "No section for implicit differentiation",
                "detail": None,
                "suggestion": None,
            },
        ]
    }
)

DRAFT_MD = "## Chain rule\n\n- Differentiate outer, then inner\n"


class FakeGateway(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)
        self.calls: list[list[Message]] = []

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
        self.calls.append(messages)
        system = " ".join(
            message.content
            for message in messages
            if message.role == "system" and isinstance(message.content, str)
        )
        if "course organizer" in system:
            return REVIEW_JSON
        if "study notes" in system:
            return DRAFT_MD
        raise AssertionError(f"unexpected prompt: {system[:80]}")


@pytest.fixture
def organizer_client() -> Iterator[tuple[TestClient, FakeGateway]]:
    import tempfile
    from pathlib import Path

    gateway = FakeGateway()
    tmp = Path(tempfile.mkdtemp(prefix="ca-org-"))
    app = create_app(Settings(data_dir=tmp, log_level="WARNING"), gateway=gateway)
    with TestClient(app) as client:
        yield client, gateway


def setup_course(client: TestClient) -> tuple[int, int, int, int]:
    course = client.post("/api/v1/courses", json={"title": "Organized"}).json()
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course["id"]},
        files={"file": ("m.txt", b"chain rule material", "text/plain")},
    ).json()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/materials/{upload['material']['id']}").json()[
            "material"
        ]["status"]
        if status == "ready":
            break
        time.sleep(0.05)
    root = client.get(f"/api/v1/courses/{course['id']}/tree").json()[0]
    chapter = client.post(
        f"/api/v1/courses/{course['id']}/nodes",
        json={"course_id": course["id"], "parent_id": root["id"], "title": "Derivatives"},
    ).json()
    section = client.post(
        f"/api/v1/courses/{course['id']}/nodes",
        json={"course_id": course["id"], "parent_id": chapter["id"], "title": "Chain rule"},
    ).json()
    return course["id"], chapter["id"], section["id"], upload["material"]["id"]


def test_chapter_review_validates_findings(
    organizer_client: tuple[TestClient, FakeGateway],
) -> None:
    client, gateway = organizer_client
    _course, chapter_id, _section, _material = setup_course(client)

    review = client.post(f"/api/v1/nodes/{chapter_id}/review")
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["node_title"] == "Derivatives"
    kinds = [finding["kind"] for finding in body["findings"]]
    assert kinds == ["coverage", "gap"]
    assert body["findings"][0]["suggestion"] == "Assign the chain-rule notes"
    prompt = " ".join(
        message.content
        for message in gateway.calls[0]
        if isinstance(message.content, str)
    )
    assert "Chain rule" in prompt

    missing = client.post("/api/v1/nodes/99999/review")
    assert missing.status_code == 404


def test_draft_note_creates_placed_tagged_note(
    organizer_client: tuple[TestClient, FakeGateway],
) -> None:
    client, _gateway = organizer_client
    course_id, _chapter_id, section_id, material_id = setup_course(client)
    client.post(f"/api/v1/nodes/{section_id}/materials", json={"material_id": material_id})

    draft = client.post(f"/api/v1/nodes/{section_id}/draft-note")
    assert draft.status_code == 200, draft.text
    note_id = draft.json()["note_id"]
    assert "Chain rule" in draft.json()["markdown"]

    notes = client.get("/api/v1/notes", params={"course_id": course_id}).json()
    created = next(
        (entry for entry in notes["items"] if entry["id"] == note_id), None
    )
    assert created is not None
    assert created["node_id"] == section_id
    assert created["tags"] == ["ai-draft"]
    assert "AI draft" in created["title"]

    empty_section = client.post("/api/v1/nodes/99999/draft-note")
    assert empty_section.status_code == 404
