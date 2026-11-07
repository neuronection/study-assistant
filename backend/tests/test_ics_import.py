"""ICS import: parsing, bounded RRULE expansion, planner mapping (plan 85 C)."""

from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.services.study.ics_import import IcsImportError, parse_ics


def _calendar(events: str) -> str:
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n{events}END:VCALENDAR\r\n"


def _event(
    *,
    uid: str,
    summary: str,
    start: str,
    rrule: str | None = None,
    categories: str | None = None,
    location: str | None = None,
) -> str:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTART{start}",
        f"SUMMARY:{summary}",
    ]
    if rrule:
        lines.append(f"RRULE:{rrule}")
    if categories:
        lines.append(f"CATEGORIES:{categories}")
    if location:
        lines.append(f"LOCATION:{location}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines) + "\r\n"


def test_single_event_maps_to_a_planner_day() -> None:
    text = _calendar(
        _event(
            uid="lecture-1",
            summary="Calculus lecture",
            start=";TZID=Europe/Berlin:20260112T100000",
            location="Room 4",
        )
    )
    preview = parse_ics(text, today=date(2026, 1, 10))
    assert preview.total_events == 1
    assert len(preview.events) == 1
    event = preview.events[0]
    assert event.day == date(2026, 1, 12)
    assert event.start is not None and event.start.strftime("%H:%M") == "10:00"
    assert event.location == "Room 4"
    assert preview.exam_candidates == []


def test_weekly_byday_expands_inside_the_window() -> None:
    text = _calendar(
        _event(
            uid="lecture-weekly",
            summary="Linear algebra",
            start=";TZID=UTC:20260105T090000",
            rrule="FREQ=WEEKLY;BYDAY=MO,WE;COUNT=4",
        )
    )
    preview = parse_ics(text, today=date(2026, 1, 1))
    assert [event.day for event in preview.events] == [
        date(2026, 1, 5),
        date(2026, 1, 7),
        date(2026, 1, 12),
        date(2026, 1, 14),
    ]
    assert len({event.uid for event in preview.events}) == 4


def test_until_bounds_daily_expansion() -> None:
    text = _calendar(
        _event(
            uid="daily",
            summary="Daily drill",
            start=";VALUE=DATE:20260101",
            rrule="FREQ=DAILY;UNTIL=20260107",
        )
    )
    preview = parse_ics(text, today=date(2026, 1, 1))
    assert len(preview.events) == 7
    assert preview.events[-1].day == date(2026, 1, 7)


def test_unbounded_rrule_is_capped() -> None:
    text = _calendar(
        _event(
            uid="forever",
            summary="Daily habit",
            start=";VALUE=DATE:20250101",
            rrule="FREQ=DAILY",
        )
    )
    preview = parse_ics(text, today=date(2026, 1, 1))
    assert 0 < len(preview.events) <= 200


def test_exam_looking_events_are_staged_not_committed() -> None:
    text = _calendar(
        _event(
            uid="exam-1",
            summary="Final exam",
            start=";VALUE=DATE:20260120",
            categories="EXAM",
        )
        + _event(uid="lecture-2", summary="Lecture", start=";VALUE=DATE:20260121")
    )
    preview = parse_ics(text, today=date(2026, 1, 1))
    assert [entry.uid for entry in preview.exam_candidates] == ["exam-1"]
    assert len(preview.events) == 2


def test_malformed_calendars_are_typed_errors() -> None:
    with pytest.raises(IcsImportError, match="BEGIN:VCALENDAR"):
        parse_ics("hello")
    with pytest.raises(IcsImportError, match="no VEVENT"):
        parse_ics(_calendar(""))
    with pytest.raises(IcsImportError, match="empty"):
        parse_ics("   ")


def _course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Calculus"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _preview(client: TestClient, course_id: str, text: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/courses/{course_id}/plan/import-ics/preview",
        files={"file": ("timetable.ics", text.encode(), "text/calendar")},
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def test_preview_then_commit_creates_and_updates_plan_items(client: TestClient) -> None:
    day = datetime.now(UTC).date() + timedelta(days=2)
    exam_day = datetime.now(UTC).date() + timedelta(days=9)
    text = _calendar(
        _event(
            uid="lecture-a",
            summary="Calculus lecture",
            start=f";VALUE=DATE:{day.strftime('%Y%m%d')}",
            location="Room 4",
        )
        + _event(
            uid="exam-a",
            summary="Midterm exam",
            start=f";VALUE=DATE:{exam_day.strftime('%Y%m%d')}",
        )
    )
    with client:
        course_id = _course(client)
        preview = _preview(client, course_id, text)
        assert len(preview["events"]) == 2
        assert [entry["uid"] for entry in preview["exam_candidates"]] == ["exam-a"]

        committed = client.post(
            f"/api/v1/courses/{course_id}/plan/import-ics?confirm_exam=false",
            files={"file": ("timetable.ics", text.encode(), "text/calendar")},
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["created"] == 2
        assert committed.json()["exam_date"] is None
        course = client.get(f"/api/v1/courses/{course_id}").json()
        assert course["exam_date"] is None

        again = client.post(
            f"/api/v1/courses/{course_id}/plan/import-ics?confirm_exam=true",
            files={"file": ("timetable.ics", text.encode(), "text/calendar")},
        )
        assert again.status_code == 200, again.text
        assert again.json()["created"] == 0
        assert again.json()["updated"] == 2
        assert again.json()["exam_date"] == exam_day.isoformat()

        items = client.get(f"/api/v1/courses/{course_id}/plan").json()
        assert len(items) == 2
        assert any(item["kind"] == "milestone" for item in items)
        assert any(item["detail"] == "Room 4" for item in items)
