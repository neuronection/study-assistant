from datetime import timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.domain.models import utcnow
from app.main import create_app


class Scripted(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)
        self.calls: list[Message] = []

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
            caps=["text"],
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.calls = messages
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


def make_client(responses: list[str], tmp: Any) -> TestClient:
    from pathlib import Path

    app = create_app(
        Settings(data_dir=Path(tmp), log_level="WARNING"),
        gateway=Scripted(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def seed_tree(client: TestClient, course_id: int) -> dict[int, int]:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = tree[0]["id"]
    nodes: dict[int, int] = {}
    for title in ("Limits", "Derivatives", "Integrals"):
        created = client.post(
            f"/api/v1/courses/{course_id}/nodes",
            json={"course_id": course_id, "parent_id": root_id, "title": title},
        )
        assert created.status_code == 201, created.text
        nodes[len(nodes) + 1] = created.json()["id"]
    return nodes


def test_exam_date_crud_and_clear(tmp_path: Any) -> None:
    client = make_client([], tmp_path)
    with client:
        course_id = client.post(
            "/api/v1/courses", json={"title": "Calculus"}
        ).json()["id"]

        listed = client.get("/api/v1/courses").json()
        assert listed[0]["exam_date"] is None

        exam_day = (utcnow().date() + timedelta(days=10)).isoformat()
        patched = client.patch(
            f"/api/v1/courses/{course_id}", json={"exam_date": exam_day}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["exam_date"] == exam_day

        cleared = client.patch(f"/api/v1/courses/{course_id}", json={"exam_date": None})
        assert cleared.status_code == 200
        assert cleared.json()["exam_date"] is None

        invalid = client.patch(
            f"/api/v1/courses/{course_id}", json={"exam_date": "not-a-date"}
        )
        assert invalid.status_code == 422


def test_exam_status_pacing_and_most_behind(tmp_path: Any) -> None:
    client = make_client([], tmp_path)
    with client:
        course_id = client.post(
            "/api/v1/courses", json={"title": "Calculus"}
        ).json()["id"]
        nodes = seed_tree(client, course_id)

        empty = client.get("/api/v1/analytics/exams").json()
        assert empty == []

        far = (utcnow().date() + timedelta(days=90)).isoformat()
        client.patch(f"/api/v1/courses/{course_id}", json={"exam_date": far})
        assert client.get("/api/v1/analytics/exams").json() == []

        near = (utcnow().date() + timedelta(days=10)).isoformat()
        client.patch(f"/api/v1/courses/{course_id}", json={"exam_date": near})

        status = client.get("/api/v1/analytics/exams").json()
        assert len(status) == 1
        entry = status[0]
        assert entry["course_id"] == course_id
        assert entry["days_left"] == 10
        assert entry["total_nodes"] == 3
        assert entry["engaged_nodes"] == 0
        assert entry["remaining_nodes"] == 3
        assert entry["nodes_per_day"] == 0.3
        assert entry["on_track"] is True
        assert entry["most_behind_node"]["id"] == nodes[1]

        note = client.post(
            "/api/v1/notes",
            json={
                "title": "Limits notes",
                "body_md": "studied limits",
                "course_id": course_id,
                "node_id": nodes[1],
            },
        )
        assert note.status_code == 201
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from app.domain.models import Activity

            db.add(
                Activity(
                    profile_id=1,
                    course_id=course_id,
                    node_id=nodes[2],
                    type="quiz",
                    title="Derivatives quiz",
                )
            )
            db.commit()

        status = client.get("/api/v1/analytics/exams").json()
        entry = status[0]
        assert entry["engaged_nodes"] == 2
        assert entry["remaining_nodes"] == 1
        assert entry["most_behind_node"]["id"] == nodes[3]
        assert entry["most_behind_node"]["title"] == "Integrals"


FORMULA_SHEET = """# Formula sheet

## Derivatives

The differentiation rules you collected, with one-line reminders for revision.

- Power rule: $f'(x) = nx^{n-1}$ — lower the exponent, then subtract one.
- Chain rule: $(fg)' = f'g + fg'$ — differentiate each factor while holding the other.
- Invented: $e^{i\\pi} = -1$

## Definitions

Fundamental theorem of calculus, linking accumulation and antiderivatives:

$$\\int_a^b f(x)\\,dx = F(b) - F(a)$$

Use it whenever a definite integral matches a known antiderivative pair.
"""


def test_formula_sheet_collects_validates_and_strips(tmp_path: Any) -> None:
    client = make_client([FORMULA_SHEET], tmp_path)
    with client:
        course_id = client.post(
            "/api/v1/courses", json={"title": "Calculus"}
        ).json()["id"]
        nodes = seed_tree(client, course_id)
        node_id = nodes[2]

        note = client.post(
            "/api/v1/notes",
            json={
                "title": "Formulas",
                "body_md": "Rules: $f'(x) = nx^{n-1}$ and $(fg)' = f'g + fg'$ plus 2+2.",
                "course_id": course_id,
                "node_id": node_id,
            },
        )
        assert note.status_code == 201, note.text
        material = client.post(
            "/api/v1/materials/text",
            json={
                "course_id": course_id,
                "filename": "integrals.md",
                "content": "Fundamental theorem $$\\int_a^b f(x)\\,dx = F(b) - F(a)$$",
            },
        )
        assert material.status_code == 200, material.text
        material_id = material.json()["material"]["id"]
        linked = client.post(
            f"/api/v1/nodes/{node_id}/materials", json={"material_id": material_id}
        )
        assert linked.status_code in (200, 201), linked.text

        composed = client.post(
            "/api/v1/materials/compose",
            json={
                "course_id": course_id,
                "kind": "formula_sheet",
                "title": "Calculus formulas",
            },
        )
        assert composed.status_code == 200, composed.text
        body = composed.json()
        assert body["material"]["title"] == "Calculus formulas"
        assert body["material"]["provenance"]["kind"] == "formula_sheet"

        app = client.app
        assert isinstance(app, FastAPI)
        composed_id = body["material"]["id"]
        deadline = __import__("time").monotonic() + 5.0
        markdown: str | None = None
        provenance: dict[str, Any] | None = None
        while __import__("time").monotonic() < deadline:
            detail = client.get(f"/api/v1/materials/{composed_id}").json()
            if detail.get("extraction") is not None:
                markdown = detail["extraction"]["markdown"]
                provenance = detail["material"]["provenance"]
                break
            __import__("time").sleep(0.05)
        assert markdown is not None
        assert "$f'(x) = nx^{n-1}$" in markdown
        assert "$(fg)' = f'g + fg'$" in markdown
        assert "e^{i" not in markdown
        assert provenance is not None
        assert provenance.get("needs_review") is True

        gateway = app.state.gateway
        assert isinstance(gateway, Scripted)
        prompt = gateway.calls[-1].content
        assert "f'(x) = nx^{n-1}" in prompt
        assert "EXACTLY the formulas" in prompt


def test_formula_sheet_without_sources_fails_cleanly(tmp_path: Any) -> None:
    client = make_client([], tmp_path)
    with client:
        course_id = client.post(
            "/api/v1/courses", json={"title": "Empty"}
        ).json()["id"]
        refused = client.post(
            "/api/v1/materials/compose",
            json={"course_id": course_id, "kind": "formula_sheet"},
        )
        assert refused.status_code == 422
        assert "no formulas" in refused.json()["detail"].lower()
