from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.models import Activity, Concept, Question


def make_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Calculus"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def make_bank(client: TestClient, course_id: str, count: int = 5) -> str:
    questions = [
        {
            "type": "text",
            "stem_md": f"Differentiate x^{index}.",
            "answer": {"value": "2x"},
            "explanation_md": "power rule",
            "concepts": [f"derivative-{index}"],
            "difficulty": 2,
            "expected_time_sec": 60,
        }
        for index in range(1, count + 1)
    ]
    imported = client.post(
        "/api/v1/quiz/import",
        params={"course_id": course_id, "dry_run": False},
        json={"title": "Bank", "questions": questions},
    )
    assert imported.status_code == 200, imported.text
    return str(imported.json()["activity"]["id"])


def paper_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Calculus mock",
        "duration_min": 90,
        "instructions_md": "Answer all questions.",
        "sections": [
            {"title": "Short answers", "marks": 10, "count": 3, "types": ["text"]},
            {"title": "Long answers", "marks": 20, "count": 2, "types": ["text"]},
        ],
    }
    body.update(overrides)
    return body


def make_paper(client: TestClient, course_id: str, **overrides: Any) -> dict[str, Any]:
    response = client.post(f"/api/v1/courses/{course_id}/papers", json=paper_body(**overrides))
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def activity_questions(client: TestClient, activity_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/api/v1/quiz/activities/{activity_id}/questions")
    assert response.status_code == 200, response.text
    return cast(list[dict[str, Any]], response.json())


def test_create_paper_snapshots_bank_questions(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        make_bank(client, course_id)

        paper = make_paper(
            client,
            course_id,
            grade_bands=[{"label": "A", "min": 90}, {"label": "B", "min": 70}],
        )

        assert paper["title"] == "Calculus mock"
        assert paper["duration_min"] == 90
        assert paper["total_marks"] == 30
        assert paper["source"] == "bank"
        assert paper["attempt_count"] == 0
        assert paper["latest_attempt_id"] is None
        assert paper["latest_percent"] is None
        assert [section["title"] for section in paper["sections"]] == [
            "Short answers",
            "Long answers",
        ]
        assert [section["marks"] for section in paper["sections"]] == [10, 20]
        assert [section["count"] for section in paper["sections"]] == [3, 2]

        questions = activity_questions(client, paper["activity_id"])
        assert len(questions) == 5
        assert {question["type"] for question in questions} == {"text"}

        listing = client.get(f"/api/v1/courses/{course_id}/papers")
        assert listing.status_code == 200
        assert [row["id"] for row in listing.json()] == [paper["id"]]

        detail = client.get(f"/api/v1/papers/{paper['id']}")
        assert detail.status_code == 200
        assert detail.json()["activity_id"] == paper["activity_id"]


def test_assembly_is_deterministic_for_the_same_blueprint(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        make_bank(client, course_id)
        first = make_paper(client, course_id)
        second = make_paper(client, course_id)

        def stems(activity_id: str) -> list[str]:
            return [
                question["stem"][0]["md"] for question in activity_questions(client, activity_id)
            ]

        assert stems(first["activity_id"]) == stems(second["activity_id"])

        reshuffled = make_paper(client, course_id, title="Calculus mock", seed=123)
        assert stems(reshuffled["activity_id"]) != stems(first["activity_id"])


def test_invalid_blueprints_are_rejected_without_leaving_rows(
    client: TestClient,
) -> None:
    with client:
        course_id = make_course(client)
        make_bank(client, course_id)

        too_many = client.post(
            f"/api/v1/courses/{course_id}/papers",
            json=paper_body(
                sections=[{"title": "All", "marks": 100, "count": 9, "types": ["text"]}]
            ),
        )
        assert too_many.status_code == 422
        assert "only 5 available" in too_many.json()["detail"]

        marks_short = client.post(
            f"/api/v1/courses/{course_id}/papers",
            json=paper_body(sections=[{"title": "All", "marks": 2, "count": 3, "types": ["text"]}]),
        )
        assert marks_short.status_code == 422
        assert "one mark per question" in marks_short.json()["detail"]

        unknown_type = client.post(
            f"/api/v1/courses/{course_id}/papers",
            json=paper_body(
                sections=[{"title": "All", "marks": 10, "count": 1, "types": ["unknown"]}]
            ),
        )
        assert unknown_type.status_code == 422
        assert "unknown question types" in unknown_type.json()["detail"]

        assert client.get(f"/api/v1/courses/{course_id}/papers").json() == []


def test_exam_attempt_report_uses_marks_and_grade_bands(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        make_bank(client, course_id)
        paper = make_paper(
            client,
            course_id,
            grade_bands=[
                {"label": "A", "min": 90},
                {"label": "B", "min": 80},
                {"label": "C", "min": 70},
                {"label": "D", "min": 60},
            ],
        )
        activity_id = paper["activity_id"]

        started = client.post(
            f"/api/v1/quiz/activities/{activity_id}/attempts", params={"mode": "exam"}
        )
        assert started.status_code == 201, started.text
        attempt = started.json()
        assert attempt["mode"] == "exam"
        assert attempt["deadline_at"] is not None

        questions = activity_questions(client, activity_id)
        for index, question in enumerate(questions):
            answer = "2x" if index != 4 else "wrong"
            graded = client.post(
                f"/api/v1/quiz/attempts/{attempt['id']}/answers",
                json={"question_id": question["id"], "response": answer},
            )
            assert graded.status_code == 200, graded.text
            body = graded.json()
            assert body["deferred"] is True
            assert body["correct"] is False
            assert body["partial_credit"] == 0.0
            assert body["feedback"] == []
            assert body["explanation"] == []

        hint = client.post(
            f"/api/v1/quiz/attempts/{attempt['id']}/questions/{questions[0]['id']}/hint",
            json={"level": 1},
        )
        assert hint.status_code == 422
        assert hint.json()["detail"] == "help is disabled in exam mode"

        finished = client.post(f"/api/v1/quiz/attempts/{attempt['id']}/finish")
        assert finished.status_code == 200, finished.text

        report = client.get(f"/api/v1/papers/{paper['id']}/report")
        assert report.status_code == 200, report.text
        payload = report.json()
        assert payload["attempt_id"] == attempt["id"]
        assert payload["earned"] == 20.0
        assert payload["total"] == 30
        assert payload["percent"] == 0.6667
        assert payload["grade"] == "D"
        assert payload["answered"] == 5
        assert payload["question_count"] == 5
        assert [section["earned"] for section in payload["sections"]] == [10.0, 10.0]

        listing = client.get(f"/api/v1/courses/{course_id}/papers").json()
        assert listing[0]["attempt_count"] == 1
        assert listing[0]["latest_attempt_id"] == attempt["id"]
        assert listing[0]["latest_percent"] == 0.6667


def test_report_attributes_lost_marks_to_concepts(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        make_bank(client, course_id)
        settings = client.app.state.settings  # type: ignore[attr-defined]
        engine = create_engine(f"sqlite:///{settings.db_path}")
        with sessionmaker(bind=engine)() as session:
            concept = Concept(course_id=course_id, name="Derivatives")
            session.add(concept)
            session.flush()
            bank_questions = list(
                session.scalars(
                    select(Question)
                    .join(Activity, Activity.id == Question.activity_id)
                    .where(Activity.course_id == course_id)
                    .order_by(Question.id)
                )
            )
            for question in bank_questions[:3]:
                question.concept_ids = [concept.id]
            session.commit()
        engine.dispose()

        paper = make_paper(client, course_id)
        started = client.post(
            f"/api/v1/quiz/activities/{paper['activity_id']}/attempts",
            params={"mode": "exam"},
        ).json()
        questions = activity_questions(client, paper["activity_id"])
        for paper_question in questions:
            client.post(
                f"/api/v1/quiz/attempts/{started['id']}/answers",
                json={"question_id": paper_question["id"], "response": "wrong"},
            )
        client.post(f"/api/v1/quiz/attempts/{started['id']}/finish")

        report = client.get(f"/api/v1/papers/{paper['id']}/report").json()
        assert report["earned"] == 0.0
        assert len(report["topics"]) == 1
        topic = report["topics"][0]
        assert topic["name"] == "Derivatives"
        assert topic["lost"] == topic["marks"]
        assert topic["marks"] > 0


def test_report_rejects_an_unknown_finished_attempt(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        make_bank(client, course_id)
        paper = make_paper(client, course_id)

        missing = client.get(
            f"/api/v1/papers/{paper['id']}/report", params={"attempt_id": "missing"}
        )
        assert missing.status_code == 404


def test_delete_paper_deletes_its_activity(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        make_bank(client, course_id)
        paper = make_paper(client, course_id)

        deleted = client.delete(f"/api/v1/papers/{paper['id']}")
        assert deleted.status_code == 204

        assert client.get(f"/api/v1/papers/{paper['id']}").status_code == 404
        assert client.get(f"/api/v1/quiz/activities/{paper['activity_id']}").status_code == 404
        assert client.get(f"/api/v1/courses/{course_id}/papers").json() == []
