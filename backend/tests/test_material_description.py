from typing import Any

from fastapi.testclient import TestClient


def make_course(client: TestClient, title: str = "Descriptions") -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def create_text(
    client: TestClient,
    course_id: int,
    *,
    description: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "course_id": course_id,
        "filename": "notes.md",
        "content": "# Notes\n\nbody",
    }
    if description is not None:
        body["description"] = description
    response = client.post("/api/v1/materials/text", json=body)
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_create_text_material_with_description(client: TestClient) -> None:
    course_id = make_course(client)
    body = create_text(client, course_id, description="Chain rule summary sheet")
    assert body["material"]["description"] == "Chain rule summary sheet"
    detail = client.get(f"/api/v1/materials/{body['material']['id']}")
    assert detail.json()["material"]["description"] == "Chain rule summary sheet"


def test_create_text_material_without_description_is_null(client: TestClient) -> None:
    course_id = make_course(client)
    body = create_text(client, course_id)
    assert body["material"]["description"] is None


def test_patch_sets_and_clears_description(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = create_text(client, course_id)["material"]["id"]

    set_result = client.patch(
        f"/api/v1/materials/{material_id}", json={"description": "Chapter 3 recap"}
    )
    assert set_result.status_code == 200
    assert set_result.json()["description"] == "Chapter 3 recap"

    cleared = client.patch(
        f"/api/v1/materials/{material_id}", json={"description": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["description"] is None


def test_patch_description_normalizes_whitespace(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = create_text(client, course_id)["material"]["id"]

    blank = client.patch(
        f"/api/v1/materials/{material_id}", json={"description": "   "}
    )
    assert blank.status_code == 200
    assert blank.json()["description"] is None


def test_patch_title_only_keeps_description(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = create_text(client, course_id, description="kept")["material"]["id"]

    renamed = client.patch(
        f"/api/v1/materials/{material_id}",
        json={"title": "Renamed notes", "description": "kept"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed notes"
    assert renamed.json()["description"] == "kept"


def test_patch_with_no_fields_is_unprocessable(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = create_text(client, course_id)["material"]["id"]

    empty = client.patch(f"/api/v1/materials/{material_id}", json={})
    assert empty.status_code == 422


def test_patch_description_rejects_too_long(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = create_text(client, course_id)["material"]["id"]

    long = client.patch(
        f"/api/v1/materials/{material_id}", json={"description": "x" * 2001}
    )
    assert long.status_code == 422
