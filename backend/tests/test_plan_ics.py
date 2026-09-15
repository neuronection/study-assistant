from datetime import timedelta

from fastapi.testclient import TestClient

from app.domain.models import PlanItem, utcnow


def make_course(client: TestClient, title: str) -> int:
    return int(client.post("/api/v1/courses", json={"title": title}).json()["id"])


def make_item(
    client: TestClient,
    course_id: int,
    title: str,
    due_date: str,
    detail: str | None = None,
) -> int:
    created = client.post(
        f"/api/v1/courses/{course_id}/plan",
        json={"title": title, "due_date": due_date, **({"detail": detail} if detail else {})},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def test_ics_round_trip_crlf_uids_and_exam(client: TestClient) -> None:
    with client:
        course_id = make_course(client, "Calculus I")
        item_id = make_item(client, course_id, "Practice: chain rule", "2026-09-16")
        client.patch(
            f"/api/v1/courses/{course_id}", json={"exam_date": "2026-09-30"}
        )

        response = client.get(f"/api/v1/courses/{course_id}/plan.ics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/calendar")
        assert "attachment" in response.headers.get("content-disposition", "")

        body = response.text
        lines = body.split("\r\n")
        assert lines[-1] == ""
        assert lines[0] == "BEGIN:VCALENDAR"
        assert lines[-2] == "END:VCALENDAR"
        assert "VERSION:2.0" in lines
        assert "X-WR-CALNAME:Calculus I" in lines
        assert "UID:planitem-1@studyassistant.local" in lines
        assert "DTSTART;VALUE=DATE:20260916" in lines
        assert "DTEND;VALUE=DATE:20260917" in lines
        assert "STATUS:CONFIRMED" in lines
        assert "SUMMARY:Practice: chain rule" in lines
        assert "UID:exam-1@studyassistant.local" in lines
        assert "DTSTART;VALUE=DATE:20260930" in lines
        assert "SUMMARY:Exam: Calculus I" in lines
        assert len([line for line in lines if line == "BEGIN:VEVENT"]) == 2
        assert item_id > 0


def test_ics_escapes_specials_and_folds_long_lines(client: TestClient) -> None:
    with client:
        course_id = make_course(client, "Titles, with; specials")
        make_item(
            client,
            course_id,
            "Drill: x, y; and z, " + "very long tail " * 8,
            "2026-09-16",
        )

        body = client.get(f"/api/v1/courses/{course_id}/plan.ics").text
        assert "X-WR-CALNAME:Titles\\, with\\; specials" in body
        assert "SUMMARY:Drill: x\\, y\\; and z\\," in body
        for line in body.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75, line
        continuation = [line for line in body.split("\r\n") if line.startswith(" ")]
        assert continuation, "long summary must fold"


def test_ics_done_items_only_within_week(client: TestClient) -> None:
    with client:
        course_id = make_course(client, "Calculus")
        done_id = make_item(client, course_id, "already done", "2026-09-10")
        open_id = make_item(client, course_id, "still open", "2026-09-20")

        done = client.patch(
            f"/api/v1/courses/{course_id}/plan/{done_id}", json={"done": True}
        )
        assert done.status_code == 200

        body = client.get(f"/api/v1/courses/{course_id}/plan.ics").text
        assert f"UID:planitem-{done_id}@studyassistant.local" in body
        assert f"UID:planitem-{open_id}@studyassistant.local" in body
        done_block = body.split(f"UID:planitem-{done_id}@studyassistant.local")[1]
        assert "STATUS:CANCELLED" in done_block.split("END:VEVENT")[0]

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        settings = client.app.state.settings  # type: ignore[attr-defined]
        engine = create_engine(f"sqlite:///{settings.db_path}")
        with sessionmaker(bind=engine)() as session:
            item = session.get(PlanItem, done_id)
            assert item is not None
            item.done_at = utcnow() - timedelta(days=10)
            session.commit()
        engine.dispose()

        aged = client.get(f"/api/v1/courses/{course_id}/plan.ics").text
        assert f"UID:planitem-{done_id}@studyassistant.local" not in aged
        assert f"UID:planitem-{open_id}@studyassistant.local" in aged


def test_ics_missing_course_404(client: TestClient) -> None:
    with client:
        assert client.get("/api/v1/courses/9999/plan.ics").status_code == 404
