import fitz
from fastapi.testclient import TestClient


def png_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=120, height=80)
    page.draw_rect(page.rect, color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9))
    pixmap = page.get_pixmap()
    return bytes(pixmap.tobytes("png"))


def make_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Diagrams"})
    assert response.status_code == 201
    return str(response.json()["id"])


def make_image(client: TestClient, course_id: str) -> str:
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("diagram.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["material"]["blob_sha"])


def test_diagram_label_round_trip(client: TestClient) -> None:
    course = make_course(client)
    sha = make_image(client, course)
    expected = {
        "kind": "diagram_label",
        "image_sha": sha,
        "hotspots": [
            {"id": "a", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "label": "Nucleus"},
            {"id": "b", "x": 0.5, "y": 0.3, "w": 0.2, "h": 0.2, "label": "Membrane"},
        ],
        "labels": ["Nucleus", "Membrane", "Cytoplasm"],
        "mode": "click",
    }
    created = client.post(
        "/api/v1/exercises",
        json={
            "title": "Cell diagram",
            "kind": "diagram_label",
            "course_id": course,
            "steps": [{"prompt_md": "Label the regions.", "expected": expected}],
        },
    )
    assert created.status_code == 201, created.text
    exercise_id = created.json()["id"]

    steps = client.get(f"/api/v1/exercises/{exercise_id}/steps").json()
    widget = steps[0]["input"]
    assert widget["widget"] == "diagram_label"
    assert widget["image_sha"] == sha
    assert [spot["id"] for spot in widget["hotspots"]] == ["a", "b"]
    assert "label" not in widget["hotspots"][0]
    assert set(widget["labels"]) == {"Nucleus", "Membrane", "Cytoplasm"}

    session = client.post(f"/api/v1/exercises/{exercise_id}/sessions").json()
    correct = client.post(
        f"/api/v1/exercises/sessions/{session['id']}/answer",
        json={
            "response": [
                {"hotspot_id": "a", "label": "Nucleus"},
                {"hotspot_id": "b", "label": "Membrane"},
                {"hotspot_id": None, "label": "Cytoplasm"},
            ]
        },
    )
    assert correct.status_code == 200, correct.text
    assert correct.json()["correct"] is True

    wrong = client.post(
        f"/api/v1/exercises/{exercise_id}/sessions",
    ).json()
    verdict = client.post(
        f"/api/v1/exercises/sessions/{wrong['id']}/answer",
        json={
            "response": [
                {"hotspot_id": "a", "label": "Membrane"},
                {"hotspot_id": "b", "label": "Nucleus"},
            ]
        },
    )
    assert verdict.json()["correct"] is False


def test_diagram_label_rejects_bad_payloads(client: TestClient) -> None:
    course = make_course(client)
    sha = make_image(client, course)
    bad = client.post(
        "/api/v1/exercises",
        json={
            "title": "Bad",
            "kind": "diagram_label",
            "course_id": course,
            "steps": [
                {
                    "prompt_md": "Label.",
                    "expected": {
                        "kind": "diagram_label",
                        "image_sha": sha,
                        "hotspots": [
                            {"id": "a", "x": 0.9, "y": 0.1, "w": 0.4, "h": 0.2, "label": "X"}
                        ],
                    },
                }
            ],
        },
    )
    assert bad.status_code == 422
