from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.vocab import StudySessionKind, StudySessionSource
from app.domain.models import StudySession, utcnow
from app.services.platform import metrics
from app.services.platform.profiles import ensure_default_profile


def test_start_heartbeat_end_and_summary(client: TestClient) -> None:
    with client:
        started = client.post(
            "/api/v1/study-sessions",
            json={"kind": "focus", "source": "timer"},
        )
        assert started.status_code == 201, started.text
        row = started.json()
        assert row["kind"] == "focus"
        assert row["source"] == "timer"
        assert row["duration_sec"] == 0

        beat = client.patch(
            f"/api/v1/study-sessions/{row['id']}", json={"action": "heartbeat"}
        )
        assert beat.status_code == 200
        assert beat.json()["duration_sec"] >= 0

        ended = client.patch(
            f"/api/v1/study-sessions/{row['id']}", json={"action": "end"}
        )
        assert ended.status_code == 200
        assert ended.json()["ended_at"] is not None

        summary = client.get("/api/v1/study-sessions/summary", params={"days": 7})
        assert summary.status_code == 200
        body = summary.json()
        today = utcnow().date().isoformat()
        today_entry = next((day for day in body["days"] if day["day"] == today), None)
        assert today_entry is not None
        assert body["today_sec"] == today_entry["total_sec"]
        assert today_entry["by_kind"]["focus"] == today_entry["total_sec"]
        assert body["week_sec"] <= sum(day["total_sec"] for day in body["days"])


def test_resume_window_merges_fragmented_remounts(client: TestClient) -> None:
    with client:
        first = client.post(
            "/api/v1/study-sessions",
            json={
                "kind": "read",
                "source": "auto",
                "course_id": None,
                "entity_ref": "material:12",
            },
        )
        assert first.status_code == 201
        first_id = first.json()["id"]

        resumed = client.post(
            "/api/v1/study-sessions",
            json={"kind": "read", "source": "auto", "entity_ref": "material:12"},
        )
        assert resumed.status_code == 201
        assert resumed.json()["id"] == first_id

        other = client.post(
            "/api/v1/study-sessions",
            json={"kind": "read", "source": "auto", "entity_ref": "material:13"},
        )
        assert other.json()["id"] != first_id

        different_kind = client.post(
            "/api/v1/study-sessions",
            json={"kind": "note", "source": "auto", "entity_ref": "material:12"},
        )
        assert different_kind.json()["id"] != first_id

        manual_never_resumes = client.post(
            "/api/v1/study-sessions",
            json={"kind": "read", "source": "timer", "entity_ref": "material:12"},
        )
        assert manual_never_resumes.json()["id"] != first_id


def test_unknown_kind_rejected(client: TestClient) -> None:
    with client:
        response = client.post(
            "/api/v1/study-sessions", json={"kind": "nonsense", "source": "auto"}
        )
        assert response.status_code == 422


def test_beat_missing_session_404(client: TestClient) -> None:
    with client:
        response = client.patch(
            "/api/v1/study-sessions/9999", json={"action": "end"}
        )
        assert response.status_code == 404


def test_course_purge_removes_sessions(client: TestClient) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Purge me"}).json()["id"]
        )
        started = client.post(
            "/api/v1/study-sessions",
            json={"kind": "quiz", "source": "auto", "course_id": course_id},
        )
        assert started.status_code == 201
        session_id = started.json()["id"]

        deleted = client.delete(
            f"/api/v1/courses/{course_id}", params={"confirmed_backup": True}
        )
        assert deleted.status_code in (200, 204), deleted.text

        beat = client.patch(
            f"/api/v1/study-sessions/{session_id}", json={"action": "end"}
        )
        assert beat.status_code == 404


def test_goal_unit_endpoints(client: TestClient) -> None:
    with client:
        goal = client.put(
            "/api/v1/analytics/goal",
            json={"unit": "minutes", "minutes_per_day": 45},
        )
        assert goal.status_code == 200, goal.text
        assert goal.json() == {
            "unit": "minutes",
            "answers_per_day": 20,
            "minutes_per_day": 45,
        }

        back_compat = client.put("/api/v1/analytics/goal", json={"answers_per_day": 25})
        assert back_compat.status_code == 200
        assert back_compat.json()["unit"] == "answers"
        assert back_compat.json()["answers_per_day"] == 25
        assert back_compat.json()["minutes_per_day"] == 45

        empty = client.put("/api/v1/analytics/goal", json={})
        assert empty.status_code == 422

        overview = client.get("/api/v1/analytics/overview").json()
        assert overview["unit"] == "answers"
        assert overview["answers_per_day"] == 25
        assert overview["minutes_per_day"] == 45
        assert "study_seconds_week" in overview
        assert all("study_seconds" in entry for entry in overview["history"])


def test_streak_accepts_five_minutes_of_session_time() -> None:
    today = utcnow().date()
    day_minus_2 = (today - timedelta(days=2)).isoformat()
    day_minus_1 = (today - timedelta(days=1)).isoformat()
    day_0 = today.isoformat()
    history = [
        {"day": day_minus_2, "answers_n": 0, "cards_reviewed": 0, "study_seconds": 0},
        {"day": day_minus_1, "answers_n": 0, "cards_reviewed": 0, "study_seconds": 299},
        {"day": day_0, "answers_n": 1, "cards_reviewed": 0, "study_seconds": 0},
    ]
    assert metrics.streak(history) == 1
    history[-2]["study_seconds"] = 300
    assert metrics.streak(history) == 2
    history[-1]["answers_n"] = 0
    assert metrics.streak(history) == 1
    history[-1]["study_seconds"] = 900
    assert metrics.streak(history) == 2
    history[-2]["study_seconds"] = 0
    assert metrics.streak(history) == 1


def test_daily_history_and_materialize_fold_session_seconds(
    db_session: Session,
) -> None:
    profile = ensure_default_profile(db_session)
    today = utcnow()
    db_session.add(
        StudySession(
            profile_id=profile.id,
            kind=StudySessionKind.FOCUS.value,
            source=StudySessionSource.TIMER.value,
            started_at=today,
            ended_at=today,
            last_beat=today,
            duration_sec=600,
        )
    )
    db_session.add(
        StudySession(
            profile_id=profile.id,
            kind=StudySessionKind.QUIZ.value,
            source=StudySessionSource.AUTO.value,
            started_at=today - timedelta(days=3),
            ended_at=today - timedelta(days=3),
            last_beat=today - timedelta(days=3),
            duration_sec=120,
        )
    )
    db_session.flush()

    history = metrics.daily_history(db_session, profile.id)
    today_entry = next(
        entry for entry in history if entry["day"] == today.date().isoformat()
    )
    assert today_entry["study_seconds"] == 600
    assert metrics.streak(history) >= 1

    metrics.materialize(db_session, profile.id)
    db_session.flush()
    from app.domain.models import DailyRollup

    rows = db_session.query(DailyRollup).all()
    by_day = {row.day: row for row in rows}
    assert by_day[today.date().isoformat()].study_seconds == 600
    assert by_day[(today - timedelta(days=3)).date().isoformat()].study_seconds == 120

    overview = metrics.overview(db_session, profile.id)
    assert overview["today"]["study_seconds"] == 600
    assert overview["study_seconds_week"] >= 600
