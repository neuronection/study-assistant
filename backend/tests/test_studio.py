from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.models import Extraction


def make_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Biology"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def make_source(client: TestClient, course_id: str, markdown: str) -> str:
    response = client.post(
        "/api/v1/materials/text",
        json={"course_id": course_id, "filename": "chapter.md", "content": markdown},
    )
    assert response.status_code == 200, response.text
    material_id = str(response.json()["material"]["id"])
    settings = client.app.state.settings  # type: ignore[attr-defined]
    engine = create_engine(f"sqlite:///{settings.db_path}")
    with sessionmaker(bind=engine)() as session:
        session.add(
            Extraction(
                material_id=material_id,
                version=1,
                extractor="text",
                blocks=[{"type": "text", "md": markdown}],
                markdown=markdown,
            )
        )
        session.commit()
    engine.dispose()
    return material_id


def test_create_slide_deck_from_material(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        source_id = make_source(
            client,
            course_id,
            "# Cell biology\n\nCells store genetic information.\n\n"
            "## Membranes\n\nA lipid bilayer controls what enters.\n\n"
            "## Energy\n\nMitochondria produce ATP.",
        )
        created = client.post(
            "/api/v1/studio/artifacts",
            json={"material_id": source_id, "kind": "slide_deck", "title": "Cell deck"},
        )
        assert created.status_code == 201, created.text
        artifact = created.json()
        cast(dict[str, Any], artifact)
        assert artifact["kind"] == "slide_deck"
        assert artifact["source_material_id"] == source_id
        assert artifact["material_id"] is not None
        slides = artifact["spec"]["slides"]
        assert slides[0]["layout"] == "title"
        assert any(slide["title"] == "Membranes" for slide in slides)
        assert any("lipid bilayer" in bullet for slide in slides for bullet in slide["bullets"])

        listing = client.get("/api/v1/studio/artifacts", params={"course_id": course_id})
        assert listing.status_code == 200
        assert [row["id"] for row in listing.json()] == [artifact["id"]]

        detail = client.get(f"/api/v1/studio/artifacts/{artifact['id']}")
        assert detail.status_code == 200
        assert detail.json()["material_id"] == artifact["material_id"]

        markdown = client.get(f"/api/v1/studio/artifacts/{artifact['id']}/markdown")
        assert markdown.status_code == 200
        assert "## Membranes" in markdown.json()["markdown"]


def test_handout_and_spec_editing(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        source_id = make_source(client, course_id, "# Formulas\n\n$E = mc^2$")
        created = client.post(
            "/api/v1/studio/artifacts",
            json={"material_id": source_id, "kind": "handout"},
        )
        assert created.status_code == 201, created.text
        artifact = created.json()
        assert artifact["kind"] == "handout"

        updated = client.patch(
            f"/api/v1/studio/artifacts/{artifact['id']}",
            json={
                "title": "Formula handout",
                "spec": {
                    "kind": "handout",
                    "title": "Formula handout",
                    "theme": "tokens",
                    "slides": [
                        {"layout": "title", "title": "Formula handout"},
                        {
                            "layout": "bullets",
                            "title": "Key formulas",
                            "bullets": ["$E = mc^2$"],
                        },
                    ],
                },
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["title"] == "Formula handout"
        assert updated.json()["spec"]["slides"][1]["bullets"] == ["$E = mc^2$"]

        bad = client.patch(
            f"/api/v1/studio/artifacts/{artifact['id']}",
            json={"spec": {"kind": "handout", "title": "Bad", "slides": []}},
        )
        assert bad.status_code == 422


def test_delete_artifact_keeps_generated_material(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        source_id = make_source(client, course_id, "# One\n\nA paragraph.")
        artifact = client.post(
            "/api/v1/studio/artifacts",
            json={"material_id": source_id, "kind": "slide_deck"},
        ).json()
        material_id = artifact["material_id"]

        deleted = client.delete(f"/api/v1/studio/artifacts/{artifact['id']}")
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/studio/artifacts/{artifact['id']}").status_code == 404
        assert client.get(f"/api/v1/materials/{material_id}").status_code == 200


def test_artifact_rejects_a_source_from_another_profile(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        make_source(client, course_id, "# One\n\nText.")
        missing = client.post(
            "/api/v1/studio/artifacts",
            json={"material_id": "missing", "kind": "slide_deck"},
        )
        assert missing.status_code == 404
