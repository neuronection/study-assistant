import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, make_course

from app.core.config import Settings
from app.domain.models import Job
from app.main import create_app


class BrokenGateway(ScriptedGateway):
    def generate(
        self,
        task: str,
        messages: Any,
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.calls.append(messages)
        raise RuntimeError("provider offline")


@fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, FastAPI, list[dict[str, Any]]]]:
    gateway = BrokenGateway([])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    events: list[dict[str, Any]] = []
    original = app.state.bus.publish_threadsafe

    def record(topic: str, payload: dict[str, Any]) -> None:
        if topic.startswith("chat:"):
            events.append(payload)
        original(topic, payload)

    app.state.bus.publish_threadsafe = record
    with TestClient(app) as test_client:
        yield test_client, app, events


def wait_for_condition(condition: Any, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError("condition never met")


def test_failed_turn_emits_turn_error_and_fails_job(
    client: tuple[TestClient, FastAPI, list[dict[str, Any]]],
) -> None:
    test_client, app, events = client
    with test_client:
        course_id = make_course(test_client)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        sent = test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "hi"},
        )
        assert sent.status_code == 200
        job_id = sent.json()["job_id"]
        wait_for_condition(lambda: any(e.get("type") == "turn_error" for e in events))
        db = app.state.session_factory()
        try:

            def job_failed() -> bool:
                db.expire_all()
                job = db.get(Job, job_id)
                return job is not None and job.status == "failed"

            wait_for_condition(job_failed)
            job = db.get(Job, job_id)
            assert job is not None
            assert "provider offline" in (job.error or "")
        finally:
            db.close()
        messages = test_client.get(
            f"/api/v1/chat/sessions/{session['id']}/messages"
        ).json()
        assert [m["role"] for m in messages] == ["user"]
        error_event = next(e for e in events if e.get("type") == "turn_error")
        assert error_event["detail"] == "provider offline"
