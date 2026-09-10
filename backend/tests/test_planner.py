from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.models import PlanItem


def make_course(client: TestClient, title: str = "Planner course") -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def set_exam(client: TestClient, course_id: int, days_out: int) -> None:
    exam = (date.today() + timedelta(days=days_out)).isoformat()
    patched = client.patch(
        f"/api/v1/courses/{course_id}", json={"exam_date": exam}
    )
    assert patched.status_code == 200, patched.text


def root_node(client: TestClient, course_id: int) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    return int(tree[0]["id"])


def make_nodes(client: TestClient, course_id: int, parent: int, titles: list[str]) -> list[int]:
    ids = []
    for title in titles:
        created = client.post(
            f"/api/v1/courses/{course_id}/nodes",
            json={"course_id": course_id, "parent_id": parent, "title": title},
        )
        assert created.status_code == 201, created.text
        ids.append(int(created.json()["id"]))
    return ids


def plan_items(client: TestClient, course_id: int) -> list[dict[str, Any]]:
    response = client.get(f"/api/v1/courses/{course_id}/plan")
    assert response.status_code == 200
    return list(response.json())


def test_plan_item_crud_and_checkoff(client: TestClient) -> None:
    course_id = make_course(client)
    due = (date.today() + timedelta(days=1)).isoformat()
    created = client.post(
        f"/api/v1/courses/{course_id}/plan",
        json={"title": "Read chapter 1", "due_date": due, "kind": "study"},
    )
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["origin"] == "manual"
    assert item["kind"] == "study"
    assert item["done_at"] is None

    done = client.patch(
        f"/api/v1/courses/{course_id}/plan/{item['id']}", json={"done": True}
    )
    assert done.status_code == 200
    assert done.json()["done_at"] is not None

    undone = client.patch(
        f"/api/v1/courses/{course_id}/plan/{item['id']}", json={"done": False}
    )
    assert undone.json()["done_at"] is None

    deleted = client.delete(f"/api/v1/courses/{course_id}/plan/{item['id']}")
    assert deleted.status_code == 204
    assert plan_items(client, course_id) == []


def test_generate_requires_exam_date(client: TestClient) -> None:
    course_id = make_course(client)
    response = client.post(f"/api/v1/courses/{course_id}/plan/generate")
    assert response.status_code == 422
    assert "exam date" in response.json()["detail"]


def test_generate_rejects_passed_exam(client: TestClient) -> None:
    course_id = make_course(client)
    set_exam(client, course_id, days_out=-3)
    response = client.post(f"/api/v1/courses/{course_id}/plan/generate")
    assert response.status_code == 422
    assert "passed" in response.json()["detail"]


def test_generate_paces_untouched_nodes_and_respects_done_manual(
    client: TestClient,
) -> None:
    course_id = make_course(client)
    set_exam(client, course_id, days_out=21)
    root = root_node(client, course_id)
    node_ids = make_nodes(
        client, course_id, root, ["Limits", "Derivatives", "Integrals"]
    )
    engaged = node_ids[2]

    note = client.post(
        "/api/v1/notes",
        json={
            "course_id": course_id,
            "node_id": engaged,
            "title": "already studied",
            "body_md": "abc",
        },
    )
    assert note.status_code == 201

    manual_due = (date.today() + timedelta(days=2)).isoformat()
    manual = client.post(
        f"/api/v1/courses/{course_id}/plan",
        json={"title": "manual item", "due_date": manual_due},
    )
    manual_id = int(manual.json()["id"])

    first = client.post(f"/api/v1/courses/{course_id}/plan/generate")
    assert first.status_code == 200, first.text
    body = first.json()
    items = body["items"]
    assert body["created"] == len(items)
    assert all(item["origin"] == "draft" for item in items)

    study_items = [item for item in items if item["kind"] == "study"]
    assert study_items, "expected study items"
    assert all("Limits" in item["title"] or "Derivatives" in item["title"] for item in study_items)
    assert not any("Integrals" in item["title"] for item in study_items)

    reviews = [item for item in items if item["kind"] == "review"]
    assert len(reviews) == 3
    milestones = [item for item in items if item["kind"] == "milestone"]
    assert len(milestones) == 1

    check_off = client.patch(
        f"/api/v1/courses/{course_id}/plan/{study_items[0]['id']}",
        json={"done": True},
    )
    assert check_off.status_code == 200

    second = client.post(f"/api/v1/courses/{course_id}/plan/generate")
    assert second.status_code == 200
    after = plan_items(client, course_id)
    kept = [item for item in after if int(item["id"]) == study_items[0]["id"]]
    assert kept and kept[0]["done_at"] is not None
    assert any(item["id"] == manual_id and item["origin"] == "manual" for item in after)


def test_generate_groups_when_more_nodes_than_days(client: TestClient) -> None:
    course_id = make_course(client)
    set_exam(client, course_id, days_out=3)
    root = root_node(client, course_id)
    make_nodes(
        client,
        course_id,
        root,
        ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
    )
    response = client.post(f"/api/v1/courses/{course_id}/plan/generate")
    assert response.status_code == 200
    study_items = [
        item for item in response.json()["items"] if item["kind"] == "study"
    ]
    assert len(study_items) <= 3
    assert any("more" in item["title"] for item in study_items)


def test_generate_biases_weak_concepts(client: TestClient) -> None:
    course_id = make_course(client)
    set_exam(client, course_id, days_out=14)
    root = root_node(client, course_id)
    make_nodes(client, course_id, root, ["Node one", "Node two"])

    from app.domain.models import Activity, Answer, Attempt, Question

    db_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    db = db_factory()
    try:
        db.add(
            Activity(
                profile_id=1, course_id=course_id, type="quiz", title="weak quiz"
            )
        )
        db.commit()
        row = db.scalars(
            select(Activity).where(Activity.course_id == course_id)
        ).first()
        assert row is not None
        question = Question(            activity_id=row.id,
            type="choice",
            stem=[{"type": "text", "md": "2+2?"}],
            options=[{"type": "text", "md": "4"}],
            answer={"index": 0},
            tags=["integration by parts"],
        )
        db.add(question)
        db.flush()
        for correct in (False, False, True):
            attempt = Attempt(activity_id=row.id, mode="practice")
            db.add(attempt)
            db.flush()
            db.add(
                Answer(
                    attempt_id=attempt.id,
                    question_id=question.id,
                    correct=correct,
                )
            )
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/v1/courses/{course_id}/plan/generate")
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert any("Practice: integration by parts" in title for title in titles)


def test_upcoming_strip_across_courses(client: TestClient) -> None:
    course_a = make_course(client, "Course A")
    course_b = make_course(client, "Course B")
    today = date.today()
    for course_id, offset in ((course_a, 0), (course_a, 3), (course_b, 40)):
        client.post(
            f"/api/v1/courses/{course_id}/plan",
            json={
                "title": f"item +{offset}",
                "due_date": (today + timedelta(days=offset)).isoformat(),
            },
        )
    response = client.get("/api/v1/plan/upcoming?days=7")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["course_title"] == "Course A"
    assert items[0]["title"] == "item +0"
    assert items[1]["title"] == "item +3"


def test_course_purge_removes_plan_items(client: TestClient) -> None:
    course_id = make_course(client)
    due = (date.today() + timedelta(days=1)).isoformat()
    created = client.post(
        f"/api/v1/courses/{course_id}/plan",
        json={"title": "doomed", "due_date": due},
    )
    assert created.status_code == 201

    db_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    db = db_factory()
    try:
        assert db.scalars(select(PlanItem.id)).first() is not None
    finally:
        db.close()

    node_id = root_node(client, course_id)
    deleted = client.delete(f"/api/v1/courses/{course_id}?confirmed_backup=true")
    assert deleted.status_code == 200, deleted.text
    _ = node_id

    db = db_factory()
    try:
        assert db.scalars(select(PlanItem.id)).first() is None
    finally:
        db.close()


def _seed_answers(client: TestClient, course_id: int, results: list[bool]) -> None:
    from app.domain.models import Activity, Answer, Attempt, Question

    db_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    db = db_factory()
    try:
        db.add(
            Activity(profile_id=1, course_id=course_id, type="quiz", title="quiz")
        )
        db.commit()
        row = db.scalars(
            select(Activity).where(Activity.course_id == course_id)
        ).first()
        assert row is not None
        question = Question(
            activity_id=row.id,
            type="choice",
            stem=[{"type": "text", "md": "2+2?"}],
            options=[{"type": "text", "md": "4"}],
            answer={"index": 0},
            tags=["integration by parts"],
        )
        db.add(question)
        db.flush()
        for correct in results:
            attempt = Attempt(activity_id=row.id, mode="practice")
            db.add(attempt)
            db.flush()
            db.add(
                Answer(attempt_id=attempt.id, question_id=question.id, correct=correct)
            )
        db.commit()
    finally:
        db.close()


def test_readiness_not_enough_data_gate(client: TestClient) -> None:
    course_id = make_course(client)
    set_exam(client, course_id, days_out=10)
    root = root_node(client, course_id)
    make_nodes(client, course_id, root, ["Node one"])

    status = client.get("/api/v1/analytics/exams").json()
    entry = next(item for item in status if item["course_id"] == course_id)
    assert entry["readiness"] is None
    assert entry["readiness_state"] == "not_enough_data"
    assert entry["trend"] is None


def test_readiness_formula_trend_and_weakest(client: TestClient) -> None:
    course_id = make_course(client)
    set_exam(client, course_id, days_out=10)
    root = root_node(client, course_id)
    node_ids = make_nodes(client, course_id, root, ["Covered", "Untouched"])
    note = client.post(
        "/api/v1/notes",
        json={
            "course_id": course_id,
            "node_id": node_ids[0],
            "title": "notes",
            "body_md": "abc",
        },
    )
    assert note.status_code == 201
    _seed_answers(client, course_id, [False, False, False, False, True, True, True, True])

    status = client.get("/api/v1/analytics/exams").json()
    entry = next(item for item in status if item["course_id"] == course_id)
    assert entry["readiness_state"] == "ok"
    assert entry["trend"] == "improving"
    assert entry["weakest"] == ["integration by parts"]
    coverage = 0.5
    mastery = 0.5
    expected = round(100 * (0.5 * coverage + 0.35 * mastery + 0.15 * 1.0))
    assert entry["readiness"] == expected


def test_generate_biases_first_practice_item_first_day(client: TestClient) -> None:
    course_id = make_course(client)
    set_exam(client, course_id, days_out=14)
    root = root_node(client, course_id)
    make_nodes(client, course_id, root, ["Node one", "Node two"])
    _seed_answers(client, course_id, [False, False, True])

    response = client.post(f"/api/v1/courses/{course_id}/plan/generate")
    assert response.status_code == 200
    practice = [
        item for item in response.json()["items"] if item["kind"] == "practice"
    ]
    assert practice, "expected a practice item"
    first_study = min(
        item["due_date"] for item in response.json()["items"] if item["kind"] == "study"
    )
    assert practice[0]["due_date"] == first_study
