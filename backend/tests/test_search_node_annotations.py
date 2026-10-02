from typing import Any

from fastapi.testclient import TestClient
from fitz import open as fitz_open

FILLER = (
    "This document exists so the extractor keeps its native text layer. "
    "It carries no further meaning for the assertions below."
)


def make_text_pdf(lines: list[str]) -> bytes:
    doc = fitz_open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 14
    data: bytes = doc.tobytes()
    doc.close()
    return data


def make_course(client: TestClient, title: str) -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def root_node_id(client: TestClient, course_id: int) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    return int(tree[0]["id"])


def add_node(client: TestClient, course_id: int, title: str) -> int:
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"title": title, "course_id": course_id, "parent_id": root_node_id(client, course_id)},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def upload_pdf(client: TestClient, lines: list[str], filename: str, course_id: int) -> int:
    content = [*lines, FILLER]
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, make_text_pdf(content), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    material_id = int(response.json()["material"]["id"])
    deadline_hits = 0
    while deadline_hits < 600:
        status = client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        if status == "ready":
            return material_id
        deadline_hits += 1
    raise AssertionError(f"material {material_id} never became ready")


def assign(client: TestClient, node_id: int, material_id: int) -> None:
    response = client.post(f"/api/v1/nodes/{node_id}/materials", json={"material_id": material_id})
    assert response.status_code == 201, response.text


def first_hit(client: TestClient, q: str, course_id: int) -> dict[str, Any]:
    search = client.get("/api/v1/search", params={"q": q, "course_id": course_id}).json()
    assert search["hits"], f"no hits for {q!r}"
    hit: dict[str, Any] = search["hits"][0]
    return hit


def test_search_hit_annotates_node_placements(client: TestClient) -> None:
    course_id = make_course(client, "Calculus")
    material_id = upload_pdf(
        client, ["Fourier Series", "Decomposition of periodic signals."], "a.pdf", course_id
    )
    node_id = add_node(client, course_id, "Series")
    assign(client, node_id, material_id)

    hit = first_hit(client, "Fourier", course_id)
    assert hit["nodes"] == [
        {
            "course_id": course_id,
            "node_id": node_id,
            "node_title": "Series",
        }
    ]


def test_search_hit_without_placements_has_empty_nodes(client: TestClient) -> None:
    course_id = make_course(client, "Algebra")
    upload_pdf(
        client, ["Gaussian Elimination", "Row reduction of linear systems."], "b.pdf", course_id
    )

    hit = first_hit(client, "Gaussian", course_id)
    assert hit["nodes"] == []


def test_search_hit_placements_are_ordered_and_capped_at_five(client: TestClient) -> None:
    course_id = make_course(client, "Geometry")
    material_id = upload_pdf(
        client, ["Pythagorean Theorem", "Right triangle relations."], "c.pdf", course_id
    )
    node_ids = [add_node(client, course_id, f"Chapter {index}") for index in range(6)]
    for node_id in node_ids:
        assign(client, node_id, material_id)

    hit = first_hit(client, "Pythagorean", course_id)
    assert [row["node_id"] for row in hit["nodes"]] == node_ids[:5]
    assert all(row["course_id"] == course_id for row in hit["nodes"])
    assert [row["node_title"] for row in hit["nodes"]] == [f"Chapter {index}" for index in range(5)]
