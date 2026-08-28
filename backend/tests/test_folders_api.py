import time
from typing import Any

import pytest
from fastapi.testclient import TestClient


def wait_for_ingest(client: TestClient, material_id: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/materials/{material_id}").json()["material"][
            "status"
        ]
        if status == "ready":
            return
        time.sleep(0.05)
    raise AssertionError("material never became ready")


def make_course(client: TestClient, title: str) -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def create_folder(
    client: TestClient, name: str, course_id: int, parent_id: int | None = None
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/folders",
        json={"name": name, "course_id": course_id, "parent_id": parent_id},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def upload(client: TestClient, data: bytes, filename: str, course_id: int) -> int:
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, data, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return int(response.json()["material"]["id"])


def test_create_nested_folders_and_list(client: TestClient) -> None:
    course_id = make_course(client, "Calculus")
    calc = create_folder(client, "Calculus", course_id)
    limits = create_folder(client, "Limits", course_id, calc["id"])
    create_folder(client, "Derivatives", course_id, calc["id"])
    folders = client.get("/api/v1/folders", params={"course_id": course_id}).json()
    paths = sorted(folder["path"] for folder in folders)
    assert paths == ["Calculus", "Calculus/Derivatives", "Calculus/Limits"]
    assert limits["parent_id"] == calc["id"]
    assert all(folder["course_id"] == course_id for folder in folders)


def test_same_path_allowed_across_courses(client: TestClient) -> None:
    first = make_course(client, "One")
    second = make_course(client, "Two")
    create_folder(client, "Lectures", first)
    other = create_folder(client, "Lectures", second)
    assert other["course_id"] == second
    listed = client.get("/api/v1/folders").json()
    assert [folder["path"] for folder in listed].count("Lectures") == 2


def test_duplicate_name_rejected_within_course(client: TestClient) -> None:
    course_id = make_course(client, "Calculus")
    create_folder(client, "Calculus", course_id)
    response = client.post(
        "/api/v1/folders", json={"name": "Calculus", "course_id": course_id}
    )
    assert response.status_code == 422


def test_folder_requires_valid_course(client: TestClient) -> None:
    response = client.post("/api/v1/folders", json={"name": "Orphan", "course_id": 99999})
    assert response.status_code == 422
    missing = client.post("/api/v1/folders", json={"name": "NoCourse"})
    assert missing.status_code == 422


def test_rename_updates_descendant_paths(client: TestClient) -> None:
    course_id = make_course(client, "Math")
    calc = create_folder(client, "Math", course_id)
    create_folder(client, "Limits", course_id, calc["id"])
    response = client.patch(f"/api/v1/folders/{calc['id']}/rename", json={"name": "Calculus"})
    assert response.status_code == 200
    folders = client.get("/api/v1/folders", params={"course_id": course_id}).json()
    assert sorted(folder["path"] for folder in folders) == ["Calculus", "Calculus/Limits"]


def test_move_rejects_own_subtree_and_cross_course(client: TestClient) -> None:
    course_id = make_course(client, "Main")
    root = create_folder(client, "Root", course_id)
    child = create_folder(client, "Child", course_id, root["id"])
    response = client.patch(
        f"/api/v1/folders/{root['id']}/move", json={"parent_id": child["id"]}
    )
    assert response.status_code == 422

    other_course = make_course(client, "Other")
    foreign = create_folder(client, "Foreign", other_course)
    cross = client.patch(
        f"/api/v1/folders/{child['id']}/move", json={"parent_id": foreign["id"]}
    )
    assert cross.status_code == 422
    assert "another course" in cross.json()["detail"]


def test_delete_cascades_subtree(client: TestClient, text_pdf: bytes) -> None:
    course_id = make_course(client, "Semester")
    parent = create_folder(client, "Semester 1", course_id)
    child = create_folder(client, "Week 1", course_id, parent["id"])
    upload_response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id, "folder_id": child["id"]},
        files={"file": ("notes.pdf", text_pdf, "application/pdf")},
    )
    assert upload_response.status_code == 200
    material_id = int(upload_response.json()["material"]["id"])
    wait_for_ingest(client, material_id)

    response = client.delete(f"/api/v1/folders/{child['id']}")
    assert response.status_code == 204

    folders = client.get("/api/v1/folders", params={"course_id": course_id}).json()
    assert [folder["path"] for folder in folders] == ["Semester 1"]
    missing = client.get(f"/api/v1/materials/{material_id}")
    assert missing.status_code == 404


def test_materials_filter_by_folder(client: TestClient, text_pdf: bytes) -> None:
    course_id = make_course(client, "Filter")
    folder = create_folder(client, "OnlyHere", course_id)
    upload_response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id, "folder_id": folder["id"]},
        files={"file": ("a.pdf", text_pdf, "application/pdf")},
    )
    assert upload_response.status_code == 200
    inside = client.get("/api/v1/materials", params={"folder_id": folder["id"]}).json()
    all_materials = client.get(
        "/api/v1/materials", params={"course_id": course_id}
    ).json()
    assert len(all_materials) == 1
    assert [m["id"] for m in inside] == [all_materials[0]["id"]]


@pytest.fixture(scope="module")
def text_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in (
        "Integration techniques",
        "Substitution reverses the chain rule for",
        "antiderivatives and simplifies many integrals.",
    ):
        page.insert_text((72, y), line)
        y += 14
    return bytes(doc.tobytes())
