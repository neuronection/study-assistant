import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

REVIEW_JSON = json.dumps(
    {
        "findings": [
            {
                "kind": "gap",
                "title": "No node for Taylor series",
                "detail": "Material mentions Taylor series but no child covers it",
                "suggestion": "Add a child node",
            }
        ]
    }
)

CHEATSHEET_V1 = (
    "# Cheat sheet\n\n"
    "- Power rule: $f'(x) = nx^{n-1}$\n"
    "- Product rule: $(fg)' = f'g + fg'$\n"
    "- Chain rule: $(f \\circ g)' = f'(g(x)) \\cdot g'(x)$\n\n"
    "## Differentiating\n\n"
    "Differentiate term by term. Use the power rule for powers, the product "
    "rule when two functions multiply, and the chain rule for compositions. "
    "For the chain rule, differentiate the outer function and multiply by the "
    "derivative of the inner function, then simplify."
)
CHEATSHEET_V2 = (
    "# Cheat sheet\n\n"
    "- Power rule: $f'(x) = nx^{n-1}$\n"
    "- Product rule: $(fg)' = f'g + fg'$\n"
    "- Chain rule: $(f \\circ g)' = f'(g(x)) \\cdot g'(x)$\n\n"
    "## Differentiating\n\n"
    "Differentiate term by term. Use the power rule for powers, the product "
    "rule when two functions multiply, and the chain rule for compositions. "
    "For the chain rule, differentiate the outer function and multiply by the "
    "derivative of the inner function, then simplify.\n"
    "- Hand addition: the product rule covers quotients via $f \\cdot (1/g)$.\n"
)
CHEATSHEET_V3 = (
    "# Cheat sheet v3\n\n"
    "- Power rule: $f'(x) = nx^{n-1}$\n"
    "- Product rule: $(fg)' = f'g + fg'$\n"
    "- Chain rule: $(f \\circ g)' = f'(g(x)) \\cdot g'(x)$\n\n"
    "## Differentiating\n\n"
    "Differentiate term by term. The power rule handles powers, the chain "
    "rule handles compositions, and the product rule covers products and "
    "quotients. This revision tightens the earlier version, keeps the "
    "quotient tip, and adds the three core rules side by side for reference."
)
COMPOSED_GUIDE = "# Study guide\n\n" + ("Guide body text. " * 60)
COMPOSED_GUIDE_V2 = "# Study guide v2\n\n" + ("Revised guide body. " * 60)


class Scripted(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)
        self.captured: list[list[Message]] = []

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
        self.captured.append(messages)
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


def wait_until(predicate: Any, timeout: float = 5.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def seed_node_with_material(client: TestClient) -> tuple[int, int]:
    course_id = client.post(
        "/api/v1/courses", json={"title": "Calculus"}
    ).json()["id"]
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = tree[0]["id"]
    node = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": "Derivatives"},
    )
    assert node.status_code == 201, node.text
    node_id = node.json()["id"]
    material = client.post(
        "/api/v1/materials/text",
        json={
            "course_id": course_id,
            "filename": "rules.md",
            "content": "Differentiation rules with $f'(x) = nx^{n-1}$ formulas.",
        },
    )
    assert material.status_code == 200, material.text
    material_id = material.json()["material"]["id"]
    linked = client.post(
        f"/api/v1/nodes/{node_id}/materials", json={"material_id": material_id}
    )
    assert linked.status_code in (200, 201), linked.text
    return course_id, node_id


def extraction_versions(client: TestClient, material_id: int) -> list[dict[str, Any]]:
    raw = client.get(f"/api/v1/materials/{material_id}/extractions").json()
    return [dict(entry) for entry in raw]


def test_cheatsheet_compose_persists_and_regenerates_as_new_version(tmp_path: Any) -> None:
    client = make_client([CHEATSHEET_V1, CHEATSHEET_V3], tmp_path)
    with client:
        course_id, node_id = seed_node_with_material(client)

        def compose_sheet(regenerate: bool) -> dict[str, Any]:
            body: dict[str, Any] = {
                "course_id": course_id,
                "node_id": node_id,
                "kind": "cheat_sheet",
                "title": "Cheat sheet",
            }
            if regenerate:
                body["regenerate"] = True
            response = client.post("/api/v1/materials/compose", json=body)
            assert response.status_code == 200, response.text
            body_out = response.json()
            assert isinstance(body_out, dict)
            return body_out

        first = compose_sheet(regenerate=False)
        material_id = first["material"]["id"]
        assert first["material"]["provenance"]["kind"] == "cheat_sheet"

        wait_until(lambda: extraction_versions(client, material_id))
        listed = client.get(f"/api/v1/courses/{course_id}/materials").json()
        assert any(entry["material_id"] == material_id for entry in listed)

        edited = client.patch(
            f"/api/v1/materials/{material_id}/extraction",
            json={"markdown": CHEATSHEET_V2},
        )
        assert edited.status_code == 200, edited.text

        second = compose_sheet(regenerate=True)
        assert second["material"]["id"] == material_id

        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, Scripted)
        prompt = "\n".join(str(message.content) for message in gateway.captured[-1])
        assert "already has a version" in prompt
        assert "quotient" in prompt

        versions = extraction_versions(client, material_id)
        assert len(versions) == 3
        newest = client.get(
            f"/api/v1/materials/{material_id}/extractions/{versions[0]['version']}"
        ).json()
        assert "Cheat sheet v3" in newest["markdown"]

        from app.domain.models import Material as MaterialModel

        with app.state.session_factory() as db:
            sheets = list(
                db.query(MaterialModel).filter(
                    MaterialModel.course_id == course_id,
                    MaterialModel.provenance.is_not(None),
                )
            )
            cheat_sheets = [
                row
                for row in sheets
                if (row.provenance or {}).get("kind") == "cheat_sheet"
            ]
            assert len(cheat_sheets) == 1


def test_review_persists_dated_and_is_excluded_from_retrieval(tmp_path: Any) -> None:
    client = make_client([REVIEW_JSON, CHEATSHEET_V1, REVIEW_JSON], tmp_path)
    with client:
        course_id, node_id = seed_node_with_material(client)

        review = client.post(f"/api/v1/nodes/{node_id}/review")
        assert review.status_code == 200, review.text
        findings = review.json()["findings"]
        assert len(findings) == 1
        assert findings[0]["kind"] == "gap"
        review_material_id = review.json()["material_id"]

        wait_until(lambda: extraction_versions(client, review_material_id))
        report = client.get(
            f"/api/v1/materials/{review_material_id}/extractions/"
            f"{extraction_versions(client, review_material_id)[0]['version']}"
        ).json()["markdown"]
        assert "Taylor series" in report
        assert "Review 20" in client.get(
            f"/api/v1/materials/{review_material_id}"
        ).json()["material"]["title"]

        sheet = client.post(
            "/api/v1/materials/compose",
            json={
                "course_id": course_id,
                "node_id": node_id,
                "kind": "cheat_sheet",
                "title": "Cheat sheet",
            },
        )
        assert sheet.status_code == 200, sheet.text
        sheet_material_id = sheet.json()["material"]["id"]
        wait_until(lambda: extraction_versions(client, sheet_material_id))

        preview = client.post(
            "/api/v1/ai/context/preview",
            json={"course_id": course_id, "node_id": node_id, "query": "rules"},
        )
        assert preview.status_code == 200, preview.text
        rendered = preview.json()["rendered"]
        assert "cheat sheet" in rendered.lower()
        assert "Taylor series" not in rendered

        second_review = client.post(f"/api/v1/nodes/{node_id}/review")
        assert second_review.status_code == 200
        assert second_review.json()["material_id"] == review_material_id

        artifacts = client.get(f"/api/v1/nodes/{node_id}/artifacts").json()
        assert artifacts["cheat_sheet"]["material_id"] == sheet_material_id
        assert artifacts["reviews"][0]["material_id"] == review_material_id


def test_draft_note_finds_existing(tmp_path: Any) -> None:
    client = make_client(
        ["# Draft notes\n\nFirst draft with formulas $x^2$.", REVIEW_JSON], tmp_path
    )
    with client:
        _course_id, node_id = seed_node_with_material(client)

        first = client.post(f"/api/v1/nodes/{node_id}/draft-note")
        assert first.status_code == 200, first.text
        assert first.json()["existing"] is False
        note_id = first.json()["note_id"]

        second = client.post(f"/api/v1/nodes/{node_id}/draft-note")
        assert second.status_code == 200, second.text
        assert second.json()["existing"] is True
        assert second.json()["note_id"] == note_id

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from app.domain.models import Note

            drafts = list(
                db.query(Note).filter(Note.node_id == node_id, Note.tags.is_not(None))
            )
            ai_drafts = [
                note for note in drafts if "ai-draft" in (note.tags or [])
            ]
            assert len(ai_drafts) == 1


def test_compose_one_live_artifact_rule(tmp_path: Any) -> None:
    client = make_client([COMPOSED_GUIDE, COMPOSED_GUIDE_V2, COMPOSED_GUIDE], tmp_path)
    with client:
        course_id, node_id = seed_node_with_material(client)

        first = client.post(
            "/api/v1/materials/compose",
            json={
                "course_id": course_id,
                "node_id": node_id,
                "kind": "study_guide",
                "title": "Derivatives guide",
            },
        )
        assert first.status_code == 200, first.text
        material_id = first.json()["material"]["id"]
        wait_until(lambda: extraction_versions(client, material_id))

        duplicate = client.post(
            "/api/v1/materials/compose",
            json={
                "course_id": course_id,
                "node_id": node_id,
                "kind": "study_guide",
            },
        )
        assert duplicate.status_code == 409
        assert str(material_id) in duplicate.json()["detail"]

        regenerated = client.post(
            "/api/v1/materials/compose",
            json={
                "course_id": course_id,
                "node_id": node_id,
                "kind": "study_guide",
                "regenerate": True,
            },
        )
        assert regenerated.status_code == 200, regenerated.text
        assert regenerated.json()["material"]["id"] == material_id
        assert regenerated.json()["job_id"] is None

        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, Scripted)
        prompt = gateway.captured[-1][-1].content
        assert "already has a version" in prompt

        versions = extraction_versions(client, material_id)
        assert len(versions) == 2

        with app.state.session_factory() as db:
            from app.domain.models import Material as MaterialModel

            guides = list(
                db.query(MaterialModel).filter(
                    MaterialModel.course_id == course_id,
                    MaterialModel.provenance.is_not(None),
                )
            )
            assert len(guides) == 1

        other_scope = client.post(
            "/api/v1/materials/compose",
            json={
                "course_id": course_id,
                "kind": "study_guide",
                "scope": "course",
            },
        )
        assert other_scope.status_code == 200, other_scope.text
        assert other_scope.json()["material"]["id"] != material_id
