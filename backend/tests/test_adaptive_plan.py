from datetime import date, timedelta

from fastapi.testclient import TestClient


def make_course(client: TestClient) -> str:
    exam = (date.today() + timedelta(days=10)).isoformat()
    response = client.post(
        "/api/v1/courses", json={"title": "Adaptive", "exam_date": exam}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_preview_and_commit_week(client: TestClient) -> None:
    course = make_course(client)
    tree = client.get(f"/api/v1/courses/{course}/tree").json()
    node = client.post(
        f"/api/v1/courses/{course}/nodes",
        json={"course_id": course, "parent_id": str(tree[0]["id"]), "title": "Limits"},
    )
    assert node.status_code in (200, 201), node.text
    card = client.post(
        "/api/v1/flashcards",
        json={
            "kind": "card_basic",
            "front_md": "limit card",
            "back_md": "answer",
            "course_id": course,
        },
    )
    assert card.status_code == 201, card.text

    capacity = client.put(
        "/api/v1/plan/capacity",
        json={"minutes": [600] * 7, "blackout_dates": [], "light_week": False},
    )
    assert capacity.status_code == 200, capacity.text
    assert client.get("/api/v1/plan/capacity").json()["minutes"] == [600] * 7

    preview = client.post("/api/v1/plan/week/preview", json={})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert len(body["days"]) == 7
    titles = [item["title"] for day in body["days"] for item in day["items"]]
    assert any(title.startswith("Review") for title in titles)
    assert any(title.startswith("Study") for title in titles)
    assert body["total_minutes"] <= sum(body["capacity_minutes"])

    committed = client.post("/api/v1/plan/week/commit", json={})
    assert committed.status_code == 200, committed.text
    assert committed.json()["created"] >= 1
    plan = client.get(f"/api/v1/courses/{course}/plan").json()
    generated = [row for row in plan if row["origin"] == "generated"]
    assert generated
    assert all(row["due_date"] >= body["start"] for row in generated)

    again = client.post("/api/v1/plan/week/commit", json={})
    assert again.status_code == 200
    plan_again = client.get(f"/api/v1/courses/{course}/plan").json()
    assert len([row for row in plan_again if row["origin"] == "generated"]) == len(generated)


def test_light_week_and_blackout_reduce_capacity(client: TestClient) -> None:
    course = make_course(client)
    tree = client.get(f"/api/v1/courses/{course}/tree").json()
    client.post(
        f"/api/v1/courses/{course}/nodes",
        json={
            "course_id": course,
            "parent_id": str(tree[0]["id"]),
            "title": "Derivatives",
        },
    )
    today = date.today()
    tomorrow = (today + timedelta(days=1)).isoformat()
    client.put(
        "/api/v1/plan/capacity",
        json={
            "minutes": [120] * 7,
            "blackout_dates": [tomorrow],
            "light_week": True,
        },
    )
    body = client.post("/api/v1/plan/week/preview", json={}).json()
    assert body["light_week"] is True
    day_map = {day["day"]: day for day in body["days"]}
    assert day_map[tomorrow]["minutes"] == 0
    assert all(
        day["minutes"] <= 60 for day in body["days"] if day["day"] != tomorrow
    )
