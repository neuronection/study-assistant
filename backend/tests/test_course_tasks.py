from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway


def create_provider(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/providers",
        json={
            "name": "Test",
            "type": "openai_compatible",
            "base_url": "http://localhost:1/v1",
            "api_key": "k",
        },
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def add_model(client: TestClient, provider_id: int, external_id: str) -> int:
    created = client.post(
        "/api/v1/models",
        json={"provider_id": provider_id, "external_id": external_id, "caps": ["text"]},
    )
    assert created.status_code == 201, created.text
    model_id: int = created.json()["id"]
    return model_id


def create_course(client: TestClient) -> int:
    created = client.post("/api/v1/courses", json={"title": "Analysis I"})
    assert created.status_code == 201, created.text
    course_id: int = created.json()["id"]
    return course_id


def chat_task(body: list[dict[str, Any]], task: str = "chat") -> dict[str, Any]:
    return next(entry for entry in body if entry["task"] == task)


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[tuple[str, str], str] = {}

    monkeypatch.setattr(
        "keyring.get_password",
        lambda service, username: store.get((service, username)),
    )

    def set_password(service: str, username: str, password: str) -> None:
        store[(service, username)] = password

    monkeypatch.setattr("keyring.set_password", set_password)

    monkeypatch.setattr(
        "keyring.delete_password",
        lambda service, username: store.pop((service, username), None),
    )


def test_course_tasks_list_and_override(client: TestClient) -> None:
    provider = create_provider(client)
    global_model = add_model(client, provider["id"], "global-model")
    override_model = add_model(client, provider["id"], "course-model")
    client.put("/api/v1/tasks/chat", json={"model_id": global_model})
    course_id = create_course(client)

    listed = client.get(f"/api/v1/courses/{course_id}/tasks")
    assert listed.status_code == 200, listed.text
    tasks = listed.json()
    assert len(tasks) > 0
    assert {entry["task"] for entry in tasks} >= {"chat", "quizgen"}
    inherited = chat_task(tasks)
    assert inherited["model_id"] is None
    assert inherited["global_model_label"] == "global-model"

    overridden = client.put(
        f"/api/v1/courses/{course_id}/tasks/chat",
        json={"model_id": override_model},
    )
    assert overridden.status_code == 200, overridden.text
    body = overridden.json()
    assert body["model_id"] == override_model
    assert body["model_label"] == "course-model"
    assert body["global_model_label"] == "global-model"

    tasks = client.get(f"/api/v1/courses/{course_id}/tasks").json()
    chat = chat_task(tasks)
    assert chat["model_id"] == override_model
    assert chat["global_model_label"] == "global-model"
    quizgen = chat_task(tasks, "quizgen")
    assert quizgen["model_id"] is None
    assert quizgen["global_model_label"] is None or isinstance(
        quizgen["global_model_label"], str | None
    )

    reset = client.put(
        f"/api/v1/courses/{course_id}/tasks/chat", json={"model_id": None}
    )
    assert reset.status_code == 200
    assert reset.json()["model_id"] is None


def test_course_task_validation_errors(client: TestClient) -> None:
    provider = create_provider(client)
    text_model = add_model(client, provider["id"], "text-model")
    vision_capable = client.post(
        "/api/v1/models",
        json={
            "provider_id": provider["id"],
            "external_id": "vision-model",
            "caps": ["vision"],
        },
    ).json()
    course_id = create_course(client)

    missing_course = client.get("/api/v1/courses/999/tasks")
    assert missing_course.status_code == 404

    unknown_task = client.put(
        f"/api/v1/courses/{course_id}/tasks/nosuch", json={"model_id": None}
    )
    assert unknown_task.status_code == 422

    missing_course_put = client.put(
        "/api/v1/courses/999/tasks/chat", json={"model_id": None}
    )
    assert missing_course_put.status_code == 404

    mismatch = client.put(
        f"/api/v1/courses/{course_id}/tasks/ocr",
        json={"model_id": text_model},
    )
    assert mismatch.status_code == 422
    assert "vision" in mismatch.json()["detail"]

    accepted = client.put(
        f"/api/v1/courses/{course_id}/tasks/ocr",
        json={"model_id": vision_capable["id"]},
    )
    assert accepted.status_code == 200


def test_gateway_resolves_per_course_override(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    factory = app.state.session_factory

    provider = create_provider(client)
    global_model = add_model(client, provider["id"], "global-model")
    override_model = add_model(client, provider["id"], "course-model")
    other_override = add_model(client, provider["id"], "other-course-model")
    fallback_model = add_model(client, provider["id"], "fallback-model")
    client.put(
        "/api/v1/tasks/chat",
        json={"model_id": global_model, "fallback_model_id": fallback_model},
    )
    course_id = create_course(client)
    other_course_id = create_course(client)
    client.put(
        f"/api/v1/courses/{course_id}/tasks/chat", json={"model_id": override_model}
    )
    client.put(
        f"/api/v1/courses/{other_course_id}/tasks/chat",
        json={"fallback_model_id": other_override},
    )

    gateway = LLMGateway(factory)
    resolved = gateway.resolve("chat", course_id)
    assert resolved.external_id == "course-model"
    chain = gateway._resolve_chain("chat", None, course_id)
    assert [entry.external_id for entry in chain] == ["course-model", "fallback-model"]

    global_chain = gateway._resolve_chain("chat", None)
    assert [entry.external_id for entry in global_chain] == [
        "global-model",
        "fallback-model",
    ]

    other_chain = gateway._resolve_chain("chat", None, other_course_id)
    assert [entry.external_id for entry in other_chain] == [
        "global-model",
        "other-course-model",
    ]


def test_gateway_four_level_precedence_chain(client: TestClient) -> None:
    """global default < global task < course default < course task, per slot."""
    app = client.app
    assert isinstance(app, FastAPI)
    factory = app.state.session_factory

    provider = create_provider(client)
    cap_default = add_model(client, provider["id"], "cap-default")
    task_model = add_model(client, provider["id"], "task-global")
    course_default = add_model(client, provider["id"], "course-default")
    course_task = add_model(client, provider["id"], "course-task")
    fb_course_default = add_model(client, provider["id"], "fb-course-default")
    client.put(
        "/api/v1/tasks/defaults/text", json={"model_id": cap_default}
    )
    client.put("/api/v1/tasks/chat", json={"model_id": task_model})
    course_id = create_course(client)

    gateway = LLMGateway(factory)

    chain = gateway._resolve_chain("chat", None, course_id)
    assert [entry.external_id for entry in chain] == ["task-global"]

    set_default = client.put(
        f"/api/v1/courses/{course_id}/tasks/defaults/text",
        json={"model_id": course_default, "fallback_model_id": fb_course_default},
    )
    assert set_default.status_code == 200, set_default.text
    body = set_default.json()
    assert body["model_label"] == "course-default"
    assert body["global_model_label"] == "cap-default"

    chain = gateway._resolve_chain("chat", None, course_id)
    assert [entry.external_id for entry in chain] == [
        "course-default",
        "fb-course-default",
    ]

    client.put(
        f"/api/v1/courses/{course_id}/tasks/chat", json={"model_id": course_task}
    )
    chain = gateway._resolve_chain("chat", None, course_id)
    assert [entry.external_id for entry in chain] == [
        "course-task",
        "fb-course-default",
    ]

    listed = chat_task(client.get(f"/api/v1/courses/{course_id}/tasks").json())
    assert listed["model_id"] is not None
    assert listed["global_model_label"] == "course-default"
    assert listed["global_fallback_model_label"] == "fb-course-default"

    cleared_default = client.put(
        f"/api/v1/courses/{course_id}/tasks/defaults/text",
        json={"model_id": None, "fallback_model_id": None},
    )
    assert cleared_default.status_code == 200
    chain = gateway._resolve_chain("chat", None, course_id)
    assert [entry.external_id for entry in chain] == ["course-task"]

    unknown_cap = client.put(
        f"/api/v1/courses/{course_id}/tasks/defaults/telepathy",
        json={"model_id": cap_default},
    )
    assert unknown_cap.status_code == 422

    missing_course_defaults = client.get("/api/v1/courses/999/tasks/defaults")
    assert missing_course_defaults.status_code == 404


def test_purge_course_removes_overrides(client: TestClient) -> None:
    from sqlalchemy import select

    from app.domain.models import CourseDefaultTaskAssignment, CourseTaskAssignment

    app = client.app
    assert isinstance(app, FastAPI)
    factory = app.state.session_factory

    provider = create_provider(client)
    model = add_model(client, provider["id"], "course-model")
    course_id = create_course(client)
    assigned = client.put(
        f"/api/v1/courses/{course_id}/tasks/chat", json={"model_id": model}
    )
    assert assigned.status_code == 200
    defaulted = client.put(
        f"/api/v1/courses/{course_id}/tasks/defaults/text",
        json={"model_id": model},
    )
    assert defaulted.status_code == 200

    with factory() as session:
        overrides = list(session.scalars(select(CourseTaskAssignment)))
        defaults = list(session.scalars(select(CourseDefaultTaskAssignment)))
        assert len(overrides) == 1
        assert len(defaults) == 1

    deleted = client.delete(
        f"/api/v1/courses/{course_id}", params={"confirmed_backup": True}
    )
    assert deleted.status_code in (200, 204), deleted.text

    with factory() as session:
        assert list(session.scalars(select(CourseTaskAssignment))) == []
        assert list(session.scalars(select(CourseDefaultTaskAssignment))) == []


def test_delete_model_unassigns_course_tasks_and_defaults(client: TestClient) -> None:
    provider = create_provider(client)
    model = add_model(client, provider["id"], "course-model")
    other = add_model(client, provider["id"], "keep-model")
    course_id = create_course(client)
    assert (
        client.put(
            f"/api/v1/courses/{course_id}/tasks/chat", json={"model_id": model}
        )
    ).status_code == 200
    assert (
        client.put(
            f"/api/v1/courses/{course_id}/tasks/defaults/text",
            json={"model_id": model, "fallback_model_id": other},
        )
    ).status_code == 200

    deleted = client.delete(f"/api/v1/models/{model}")
    assert deleted.status_code == 204

    tasks = client.get(f"/api/v1/courses/{course_id}/tasks").json()
    assert chat_task(tasks)["model_id"] is None
    defaults = client.get(f"/api/v1/courses/{course_id}/tasks/defaults").json()
    text_default = next(entry for entry in defaults if entry["requires"] == "text")
    assert text_default["model_id"] is None
    assert text_default["fallback_model_id"] == other
