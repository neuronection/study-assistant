import json

from fastapi import FastAPI
from sqlalchemy import select
from test_exgen_api import _create_manual_exercise, make_client, make_course

from app.domain.models import StepAttempt


def exercise_with_widget() -> str:
    payload = {
        "title": "Read the chart",
        "context_md": "Use the chart.",
        "difficulty": 2,
        "steps": [
            {
                "prompt_md": "Read the maximum value.",
                "expected_kind": "numeric",
                "expected_value": "5",
                "widgets": [
                    {
                        "type": "widget",
                        "widget": "chart",
                        "id": "w1",
                        "props": {"plotly": {"data": [{"y": [1, 5, 3]}]}},
                    }
                ],
            }
        ],
    }
    return json.dumps(payload)


def test_exgen_emits_widget_block_into_step_prompt() -> None:
    client = make_client([exercise_with_widget()])
    with client:
        created = client.post(
            "/api/v1/exercises/generate",
            json={"course_id": make_course(client), "topic": "graphs", "step_count": 1},
        )
        assert created.status_code == 201, created.text
        steps = client.get(f"/api/v1/exercises/{created.json()['id']}/steps").json()
        assert len(steps) == 1
        widgets = [block for block in steps[0]["prompt"] if block.get("type") == "widget"]
        assert len(widgets) == 1
        assert widgets[0]["widget"] == "chart"
        assert widgets[0]["id"] == "w1"


def test_exgen_rejects_invalid_widget() -> None:
    bad = {
        "title": "Bad widget",
        "context_md": "",
        "difficulty": 2,
        "steps": [
            {
                "prompt_md": "Do something.",
                "expected_kind": "numeric",
                "expected_value": "1",
                "widgets": [{"type": "widget", "widget": "hologram", "id": "w1", "props": {}}],
            }
        ],
    }
    client = make_client([json.dumps(bad), json.dumps(bad), json.dumps(bad)])
    with client:
        created = client.post(
            "/api/v1/exercises/generate",
            json={"course_id": make_course(client), "topic": "x", "step_count": 1},
        )
        assert created.status_code == 422
        assert "unknown widget" in created.json()["detail"]


def test_submit_answer_records_widget_state() -> None:
    client = make_client([])
    with client:
        exercise_id = _create_manual_exercise(client)
        session = client.post(
            f"/api/v1/exercises/{exercise_id}/sessions", json={}
        ).json()
        response = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer",
            json={"response": "2x", "state": {"w1": {"checked": ["factor"]}}},
        )
        assert response.status_code == 200, response.text
        app = client.app
        assert isinstance(app, FastAPI)
        db = app.state.session_factory()
        try:
            attempt = db.scalars(
                select(StepAttempt).where(StepAttempt.session_id == session["id"])
            ).first()
            assert attempt is not None
            assert attempt.state == {"w1": {"checked": ["factor"]}}
        finally:
            db.close()
