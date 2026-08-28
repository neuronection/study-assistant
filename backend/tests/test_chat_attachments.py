import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, add_material, make_course

from app.core.config import Settings
from app.domain.models import Activity, Exercise, ExerciseStep, Material, Profile, Question
from app.main import create_app


def wait_for_assistant(
    client: TestClient, session_id: int, timeout: float = 5.0
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages: list[dict[str, Any]] = client.get(
            f"/api/v1/chat/sessions/{session_id}/messages"
        ).json()
        if messages and messages[-1]["role"] == "assistant":
            return messages
        time.sleep(0.05)
    raise AssertionError("assistant never replied")


@fixture
def gateway() -> ScriptedGateway:
    return ScriptedGateway([])


@fixture
def client(
    tmp_path: Path, gateway: ScriptedGateway
) -> Iterator[tuple[TestClient, ScriptedGateway, FastAPI]]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway, app


def make_session(client: TestClient, course_id: int) -> dict[str, Any]:
    created: dict[str, Any] = client.post(
        "/api/v1/chat/sessions", json={"course_id": course_id}
    ).json()
    return created


def insert_quiz(app: FastAPI, course_id: int) -> int:
    db = app.state.session_factory()
    profile_id = db.query(Profile).first().id
    activity = Activity(
        profile_id=profile_id,
        course_id=course_id,
        type="quiz",
        title="Derivatives check",
    )
    db.add(activity)
    db.flush()
    db.add(
        Question(
            activity_id=activity.id,
            type="choice",
            stem=[{"type": "text", "md": "What is $d/dx\\ x^2$?"}],
            options=[
                {"type": "text", "md": "$2x$"},
                {"type": "text", "md": "$x^2/2$"},
            ],
            answer={"index": 0},
        )
    )
    db.commit()
    activity_id = activity.id
    db.close()
    return activity_id


def insert_exercise(app: FastAPI, course_id: int) -> int:
    db = app.state.session_factory()
    profile_id = db.query(Profile).first().id
    exercise = Exercise(
        profile_id=profile_id,
        course_id=course_id,
        title="Chain rule practice",
        kind="multi_step",
    )
    db.add(exercise)
    db.flush()
    db.add(
        ExerciseStep(
            exercise_id=exercise.id,
            order_idx=0,
            prompt=[{"type": "text", "md": "Differentiate $\\sin(3x)$."}],
            expected={"answer": "3\\cos(3x)"},
        )
    )
    db.commit()
    exercise_id = exercise.id
    db.close()
    return exercise_id


def insert_pending_material(app: FastAPI, course_id: int) -> int:
    db = app.state.session_factory()
    profile_id = db.query(Profile).first().id
    material = Material(
        profile_id=profile_id,
        course_id=course_id,
        kind="doc",
        title="Slow scan.pdf",
        filename="slow.pdf",
        status="processing",
    )
    db.add(material)
    db.commit()
    material_id = material.id
    db.close()
    return material_id


def test_attachments_register_mentions_and_reach_the_prompt(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client, "body.txt", "integration techniques overview", course_id
        )
        gateway.responses.append("Here is the overview [1].")
        session = make_session(test_client, course_id)
        sent = test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={
                "content": "summarize what I attached",
                "attachments": [{"kind": "material", "id": material_id}],
            },
        )
        assert sent.status_code == 200, sent.text
        user_message = sent.json()["user_message"]
        assert [m["ref"] for m in user_message["mentions"]] == [f"M{material_id}"]
        wait_for_assistant(test_client, session["id"])
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert f"M{material_id} = " in prompt
        assert (
            "The student attached these items to the message "
            f"(handles from the referenceable-items manifest): [M{material_id}]"
            in prompt
        )
        context = test_client.get(
            f"/api/v1/chat/sessions/{session['id']}/context"
        ).json()
        refs = {entry["ref"] for entry in context["registry"]}
        assert f"M{material_id}" in refs


def test_attachments_across_kinds_resolve_to_registry_refs(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        quiz_id = insert_quiz(app, course_id)
        exercise_id = insert_exercise(app, course_id)
        session = make_session(test_client, course_id)
        sent = test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={
                "content": "review these",
                "attachments": [
                    {"kind": "quiz", "id": quiz_id},
                    {"kind": "exercise", "id": exercise_id},
                ],
            },
        )
        assert sent.status_code == 200, sent.text
        mentions = sent.json()["user_message"]["mentions"]
        by_ref = {m["ref"]: m for m in mentions}
        assert by_ref[f"Q{quiz_id}"]["title"] == "Derivatives check"
        assert "1 questions" in by_ref[f"Q{quiz_id}"]["summary"]
        assert by_ref[f"E{exercise_id}"]["kind"] == "exercise"
        assert "1 steps" in by_ref[f"E{exercise_id}"]["summary"]


def test_attach_course_maps_to_root_node(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client, "Linear algebra")
        gateway.responses.append("Ready when you are.")
        session = make_session(test_client, course_id)
        sent = test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "hi", "attachments": [{"kind": "course", "id": course_id}]},
        )
        assert sent.status_code == 200, sent.text
        mention = sent.json()["user_message"]["mentions"][0]
        tree = test_client.get(f"/api/v1/courses/{course_id}/tree").json()
        assert mention["kind"] == "node"
        assert mention["id"] == tree[0]["id"]
        assert mention["title"] == "Linear algebra"
        wait_for_assistant(test_client, session["id"])
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert "Linear algebra" in prompt


def test_read_quiz_and_exercise_attachments(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        quiz_id = insert_quiz(app, course_id)
        exercise_id = insert_exercise(app, course_id)
        gateway.responses.append(f"READ Q{quiz_id}\nREAD E{exercise_id}")
        gateway.responses.append(f"Both look good: [Q{quiz_id}] and [E{exercise_id}].")
        session = make_session(test_client, course_id)
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={
                "content": "check my quiz and exercise",
                "attachments": [
                    {"kind": "quiz", "id": quiz_id},
                    {"kind": "exercise", "id": exercise_id},
                ],
            },
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        read_refs = {read["ref"] for read in assistant["reads"]}
        assert read_refs == {f"Q{quiz_id}", f"E{exercise_id}"}
        assert [m["ref"] for m in assistant["mentions"]] == [
            f"Q{quiz_id}",
            f"E{exercise_id}",
        ]
        second_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "Derivatives check — quiz with 1 questions" in second_prompt
        assert "Q1 (choice): What is $d/dx\\ x^2$?" in second_prompt
        assert "A) $2x$" in second_prompt
        assert "answer: A" in second_prompt
        assert "Chain rule practice — multi_step exercise with 1 steps" in second_prompt
        assert "Step 1: Differentiate $\\sin(3x)$." in second_prompt
        assert '"answer": "3\\\\cos(3x)"' in second_prompt


def test_read_pending_material_reports_processing(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = insert_pending_material(app, course_id)
        gateway.responses.append(f"READ M{material_id}")
        gateway.responses.append("It is still processing.")
        session = make_session(test_client, course_id)
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "read it", "attachments": [{"kind": "material", "id": material_id}]},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert assistant["reads"] == []
        second_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "still being processed" in second_prompt


def test_attach_unknown_id_returns_404_and_unknown_kind_422(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        session = make_session(test_client, course_id)
        missing = test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "hi", "attachments": [{"kind": "material", "id": 999}]},
        )
        assert missing.status_code == 404
        bad_kind = test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "hi", "attachments": [{"kind": "dragon", "id": 1}]},
        )
        assert bad_kind.status_code == 422
