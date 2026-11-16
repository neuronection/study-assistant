import time
from collections.abc import Callable
from typing import cast

import fitz
from fastapi.testclient import TestClient


def make_pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 14
    return bytes(doc.tobytes())


def wait_until(predicate: Callable[[], bool], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def ready_material(client: TestClient) -> tuple[str, str]:
    course = client.post("/api/v1/courses", json={"title": "Anchors"})
    assert course.status_code == 201
    course_id = str(course.json()["id"])
    pdf = make_pdf(
        [
            "The Chain Rule",
            "The chain rule states that the derivative of a composite function",
            "equals the outer derivative times the inner derivative.",
        ]
    )
    uploaded = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("chain-rule.pdf", pdf, "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    material_id = str(uploaded.json()["material"]["id"])
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"][
            "status"
        ]
        == "ready"
    )
    detail = client.get(f"/api/v1/materials/{material_id}").json()
    extraction = detail["extraction"]
    assert extraction is not None
    return material_id, cast(str, extraction["markdown"])


def test_highlight_create_list_patch_and_delete(client: TestClient) -> None:
    material_id, _markdown = ready_material(client)
    created = client.post(
        f"/api/v1/materials/{material_id}/anchors",
        json={
            "anchor_kind": "text_range",
            "quote": "derivative of a composite function",
            "color": "yellow",
        },
    )
    assert created.status_code == 201, created.text
    anchor = created.json()
    assert anchor["anchor_kind"] == "text_range"
    assert anchor["material_id"] == material_id
    assert anchor["orphaned"] is False
    assert anchor["payload"]["end"] > anchor["payload"]["start"]
    assert anchor["payload"]["occurrence"] == 0

    listed = client.get(f"/api/v1/materials/{material_id}/anchors")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [anchor["id"]]

    patched = client.patch(
        f"/api/v1/anchors/{anchor['id']}",
        json={"note_md": "This is the key step.", "color": "green"},
    )
    assert patched.status_code == 200
    assert patched.json()["note_md"] == "This is the key step."
    assert patched.json()["color"] == "green"

    cleared = client.patch(f"/api/v1/anchors/{anchor['id']}", json={"note_md": None})
    assert cleared.status_code == 200
    assert cleared.json()["note_md"] == ""

    removed = client.delete(f"/api/v1/anchors/{anchor['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/v1/materials/{material_id}/anchors").json() == []


def test_reanchor_updates_offsets_and_orphans_a_removed_quote(client: TestClient) -> None:
    material_id, markdown = ready_material(client)
    created = client.post(
        f"/api/v1/materials/{material_id}/anchors",
        json={
            "anchor_kind": "text_range",
            "quote": "outer derivative times the inner derivative",
        },
    )
    assert created.status_code == 201, created.text
    anchor = created.json()
    original_start = anchor["payload"]["start"]

    shifted = client.patch(
        f"/api/v1/materials/{material_id}/extraction",
        json={"markdown": "Preface paragraph.\n\n" + markdown},
    )
    assert shifted.status_code == 200, shifted.text
    after = client.get(f"/api/v1/materials/{material_id}/anchors").json()[0]
    assert after["orphaned"] is False
    assert after["payload"]["start"] > original_start

    lost = client.patch(
        f"/api/v1/materials/{material_id}/extraction",
        json={"markdown": "The chain rule is gone from this version."},
    )
    assert lost.status_code == 200, lost.text
    orphaned = client.get(f"/api/v1/materials/{material_id}/anchors").json()[0]
    assert orphaned["orphaned"] is True
    assert orphaned["quote"] == "outer derivative times the inner derivative"


def test_payload_validation_rejects_bad_quads_and_unknown_kinds(client: TestClient) -> None:
    material_id, _markdown = ready_material(client)
    bad_quad = client.post(
        f"/api/v1/materials/{material_id}/anchors",
        json={
            "anchor_kind": "pdf_quad",
            "page": 1,
            "payload": {"page": 1, "x": 0.9, "y": 0.1, "w": 0.4, "h": 0.2},
        },
    )
    assert bad_quad.status_code == 422

    good_quad = client.post(
        f"/api/v1/materials/{material_id}/anchors",
        json={
            "anchor_kind": "pdf_quad",
            "page": 1,
            "payload": {"page": 1, "x": 0.1, "y": 0.1, "w": 0.4, "h": 0.2},
        },
    )
    assert good_quad.status_code == 201, good_quad.text
    assert good_quad.json()["page"] == 1

    unknown = client.post(
        f"/api/v1/materials/{material_id}/anchors",
        json={"anchor_kind": "nope", "payload": {}},
    )
    assert unknown.status_code == 422

    missing_quote = client.post(
        f"/api/v1/materials/{material_id}/anchors",
        json={"anchor_kind": "text_range", "payload": {}},
    )
    assert missing_quote.status_code == 422


def test_highlight_quote_must_exist_in_the_current_extraction(client: TestClient) -> None:
    material_id, _markdown = ready_material(client)
    response = client.post(
        f"/api/v1/materials/{material_id}/anchors",
        json={"anchor_kind": "text_range", "quote": "not in this document"},
    )
    assert response.status_code == 422


def test_reingest_reanchors_to_the_new_extraction_version(client: TestClient) -> None:
    material_id, _markdown = ready_material(client)
    created = client.post(
        f"/api/v1/materials/{material_id}/anchors",
        json={"anchor_kind": "text_range", "quote": "The Chain Rule"},
    )
    assert created.status_code == 201, created.text
    old_version = created.json()["payload"]["version_id"]

    reingested = client.post(
        f"/api/v1/materials/{material_id}/reingest", json={"mode": "text"}
    )
    assert reingested.status_code == 200, reingested.text

    def extraction_version() -> int:
        detail = client.get(f"/api/v1/materials/{material_id}").json()
        extraction = detail["extraction"]
        return cast(int, extraction["version"]) if extraction is not None else 0

    wait_until(lambda: extraction_version() >= 2)
    detail = client.get(f"/api/v1/materials/{material_id}").json()
    anchor = client.get(f"/api/v1/materials/{material_id}/anchors").json()[0]
    assert anchor["orphaned"] is False
    assert anchor["payload"]["version_id"] == detail["extraction"]["id"]
    assert anchor["payload"]["version_id"] != old_version
