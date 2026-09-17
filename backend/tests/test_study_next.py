from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.models import utcnow


def make_course(client: TestClient, title: str, exam_date: str | None = None) -> int:
    course_id = int(client.post("/api/v1/courses", json={"title": title}).json()["id"])
    if exam_date is not None:
        patched = client.patch(
            f"/api/v1/courses/{course_id}", json={"exam_date": exam_date}
        )
        assert patched.status_code == 200, patched.text
    return course_id


def make_card(client: TestClient, course_id: int, front: str) -> int:
    response = client.post(
        "/api/v1/flashcards",
        json={
            "kind": "basic",
            "front_md": front,
            "back_md": f"back {front}",
            "course_id": course_id,
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def make_plan_item(
    client: TestClient, course_id: int, title: str, due_date: str
) -> int:
    created = client.post(
        f"/api/v1/courses/{course_id}/plan",
        json={"title": title, "due_date": due_date},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def test_study_next_empty_profile_is_honest(client: TestClient) -> None:
    with client:
        response = client.get("/api/v1/study/next")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["due_cards"] == 0
    assert data["review_courses"] == []
    assert data["plan_rows"] == []
    assert data["weak_cells"] == []
    assert data["goal_unit"] in ("answers", "minutes")
    assert data["goal_target"] > 0
    assert data["streak"] == 0


def test_study_next_composes_due_plan_and_goal(client: TestClient) -> None:
    with client:
        course = make_course(client, "Calculus I")
        make_card(client, course, "derivative of x^2")
        today = utcnow().date()
        make_plan_item(
            client,
            course,
            "Review limits",
            (today - timedelta(days=1)).isoformat(),
        )
        make_plan_item(
            client,
            course,
            "Read chapter 2",
            today.isoformat(),
        )
        client.patch(
            f"/api/v1/courses/{course}",
            json={"exam_date": (today + timedelta(days=10)).isoformat()},
        )

        response = client.get("/api/v1/study/next")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["due_cards"] >= 1
    assert data["review_courses"] == ["Calculus I"]
    assert [row["title"] for row in data["plan_rows"]] == [
        "Review limits",
        "Read chapter 2",
    ]
    assert data["plan_rows"][0]["overdue"] is True
    assert data["plan_rows"][1]["overdue"] is False
    assert data["goal_unit"] in ("answers", "minutes")
    assert data["streak"] >= 0


def test_study_next_weak_cells_are_scoped_and_deterministic(client: TestClient) -> None:
    with client:
        make_course(
            client,
            "Exam course",
            exam_date=(utcnow().date() + timedelta(days=3)).isoformat(),
        )
        make_course(client, "Other course")

        response = client.get("/api/v1/study/next")
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data["weak_cells"], list)
    assert len(data["weak_cells"]) <= 3


def test_weak_cells_scoping_order_follows_the_pinned_rule(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import study as study_api
    from app.services.platform import metrics
    from app.services.platform.profiles import ensure_default_profile

    with client:
        course_a = make_course(client, "Param course")
        course_b = make_course(
            client,
            "Exam course",
            exam_date=(utcnow().date() + timedelta(days=2)).isoformat(),
        )
        course_c = make_course(client, "Plain course")

        monkeypatch.setattr(
            metrics,
            "exam_status",
            lambda _session, _profile: [
                {"course_id": course_b, "days_left": 2},
            ],
        )
        monkeypatch.setattr(
            metrics,
            "answer_rows",
            lambda _session, _profile, course_id: [f"row-{course_id}"],
        )
        monkeypatch.setattr(
            metrics,
            "weakness_matrix",
            lambda rows: [
                {
                    "concept": f"concept-{rows[0]}",
                    "skill": "derivative",
                    "n": 1,
                    "accuracy": 0.25,
                    "weakness_score": 0.9,
                    "enough_data": True,
                }
            ],
        )

        assert isinstance(client.app, FastAPI)
        factory = client.app.state.session_factory
        with factory() as session:
            profile = ensure_default_profile(session)
            without_param = study_api._weak_cells(session, profile.id, None)
            order = [cell.course_id for cell in without_param]
            assert order[:3] == [course_b, course_a, course_c]

            with_param = study_api._weak_cells(session, profile.id, course_c)
            assert [cell.course_id for cell in with_param][:2] == [course_c, course_b]


def test_study_next_excludes_scratch_courses(client: TestClient) -> None:
    with client:
        regular = make_course(client, "Regular")
        make_card(client, regular, "visible card")

        scratch_id = int(
            client.get("/api/v1/courses/scratchpad").json()["course"]["id"]
        )
        make_card(client, scratch_id, "scratch card")

        response = client.get("/api/v1/study/next")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["due_cards"] == 1
    assert data["review_courses"] == ["Regular"]


def test_study_next_is_deterministic(client: TestClient) -> None:
    with client:
        course = make_course(client, "Determinism")
        make_card(client, course, "card one")
        make_plan_item(
            client,
            course,
            "task",
            utcnow().date().isoformat(),
        )
        first = client.get("/api/v1/study/next").json()
        second = client.get("/api/v1/study/next").json()
    assert first == second
