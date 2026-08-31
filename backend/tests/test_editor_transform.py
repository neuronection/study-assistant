import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_chat_api import (
    NoDescriber,
    NoEmbedder,
    ScriptedGateway,
    add_material,
    make_course,
)

from app.ai.gateway import Message, TaskUnassigned
from app.core.config import Settings
from app.domain.models import AiInteraction
from app.main import create_app
from app.services.platform.editor_ai import validate_output
from app.services.platform.skills import SkillService


class UnassignedGateway(ScriptedGateway):
    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        raise TaskUnassigned(task)


@pytest.fixture
def gateway() -> ScriptedGateway:
    return ScriptedGateway([])


@pytest.fixture
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


def transform_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "text": "The derivative of $x^2$ is $2x$ because of the power rule.",
        "preset": "compact",
        "mode": "transform",
    }
    payload.update(overrides)
    return payload


def wait_for_job(client: TestClient, job_id: int, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(f"/api/v1/ai/editor/jobs/{job_id}").json()
        if body["status"] not in ("queued", "running"):
            return body
        time.sleep(0.05)
    raise AssertionError("editor transform job never finished")


def test_editor_transform_task_seeded(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        tasks = test_client.get("/api/v1/tasks").json()
        assert any(entry["task"] == "editor_transform" for entry in tasks)


def test_editor_transform_skill_seeded_and_resolves(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        factory = app.state.session_factory
        with factory() as session:
            version = SkillService(session).resolve("editor.transform", course_id=None)
            assert version is not None
            assert version.skill.task == "editor_transform"


def test_transform_runs_and_audits(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        gateway.responses.append("A very compact version of the sentence.")
        response = test_client.post(
            "/api/v1/ai/editor/transform", json=transform_payload()
        )
        assert response.status_code == 200, response.text
        job_id = int(response.json()["job_id"])
        body = wait_for_job(test_client, job_id)
        assert body["status"] == "done", body
        assert body["result_md"] == "A very compact version of the sentence."
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert "Transform the text below" in prompt
        assert "power rule" in prompt
        factory = app.state.session_factory
        with factory() as session:
            audit = session.scalars(
                select(AiInteraction).where(
                    AiInteraction.context_type == "editor_transform"
                )
            ).first()
            assert audit is not None
            assert audit.task == "editor_transform"
            assert audit.skill_version_id is not None


def test_include_context_appears_in_prompt(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        gateway.responses.append("A compact result.")
        response = test_client.post(
            "/api/v1/ai/editor/transform",
            json=transform_payload(
                include_context=True,
                context_document="Surrounding note text about limits.",
            ),
        )
        assert response.status_code == 200, response.text
        job_id = int(response.json()["job_id"])
        body = wait_for_job(test_client, job_id)
        assert body["status"] == "done", body
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert "Surrounding note text about limits." in prompt


def test_unknown_preset_rejected(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        response = test_client.post(
            "/api/v1/ai/editor/transform", json=transform_payload(preset="warp")
        )
        assert response.status_code == 422
        assert "unknown preset" in response.text


def test_transform_mode_requires_text(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        response = test_client.post(
            "/api/v1/ai/editor/transform",
            json=transform_payload(text="   ", preset="explain"),
        )
        assert response.status_code == 422
        assert "text is required" in response.text


def test_write_mode_allows_empty_text(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        gateway.responses.append("Fresh content written by the model.")
        response = test_client.post(
            "/api/v1/ai/editor/transform",
            json={"text": "", "instruction": "Write a definition of a limit", "mode": "write"},
        )
        assert response.status_code == 200, response.text
        job_id = int(response.json()["job_id"])
        body = wait_for_job(test_client, job_id)
        assert body["status"] == "done", body
        assert "Fresh content" in body["result_md"]


def test_ground_in_material_requires_course(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        response = test_client.post(
            "/api/v1/ai/editor/transform",
            json=transform_payload(ground_in_material=True),
        )
        assert response.status_code == 422
        assert "course_id" in response.text


def test_unassigned_task_fails_the_job(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=UnassignedGateway([]),
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/ai/editor/transform", json=transform_payload()
        )
        assert response.status_code == 200, response.text
        job_id = int(response.json()["job_id"])
        body = wait_for_job(test_client, job_id)
        assert body["status"] == "error"
        assert "unassigned" in (body["error"] or "").lower()


def test_contract_failure_after_repair_fails_the_job(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        gateway.responses.append("Sure, here is the compact version.")
        gateway.responses.append("Sure, here is the compact version again.")
        gateway.responses.append("Sure, still a preamble.")
        response = test_client.post(
            "/api/v1/ai/editor/transform", json=transform_payload()
        )
        assert response.status_code == 200, response.text
        job_id = int(response.json()["job_id"])
        body = wait_for_job(test_client, job_id)
        assert body["status"] == "error"
        assert "preamble" in (body["error"] or "")


def test_job_not_found_404(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        response = test_client.get("/api/v1/ai/editor/jobs/999999")
        assert response.status_code == 404


def test_ground_in_material_injects_the_course_manifest(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client, "src.txt", "limits and derivatives source", course_id
        )
        gateway.responses.append("A compact answer grounded in the material.")
        response = test_client.post(
            "/api/v1/ai/editor/transform",
            json=transform_payload(ground_in_material=True, course_id=course_id),
        )
        assert response.status_code == 200, response.text
        job_id = int(response.json()["job_id"])
        body = wait_for_job(test_client, job_id)
        assert body["status"] == "done", body
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert f"[M{material_id}]" in prompt


def test_validate_output_units() -> None:
    text = "long input text for compact checks"
    assert validate_output("", text, "compact") == ["empty output"]
    assert "preamble" in validate_output("Sure, done.", text, "compact")[0]
    long_out = "an even longer output text than input here"
    assert "not shorter" in validate_output(long_out, text, "compact")[0]
    assert validate_output("Shorter.", text, "compact") == []
    assert "sentence" in validate_output("no punctuation at all", "question?", "answer")[0]
    assert validate_output("It is two.", "question?", "answer") == []
    markdown_problems = validate_output("```fence", text, "markdown")
    assert "fences" in markdown_problems[0]
    markdown_problems = validate_output("value is $x$ and $y", text, "markdown")
    assert "math" in markdown_problems[0]
    markdown_problems = validate_output("a <div>raw</div> tag", text, "markdown")
    assert "HTML" in markdown_problems[0]
    assert validate_output("# Fine\n\n- item", text, "markdown") == []


def test_stream_text_matches_run_text(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    _test_client, gateway, app = client
    text = "The collected streamed output equals the non-streamed one."
    gateway.responses.append(text)
    gateway.responses.append(text)
    with app.state.session_factory() as session:
        from app.ai.runner import TaskRunner

        runner = TaskRunner(session, gateway)
        sync_result = runner.run_text(
            task="editor_transform",
            prompt="prompt",
            validate=lambda out: [],
            fallback_system="system",
        )
        deltas: list[str] = []
        result = None
        for kind, value in runner.stream_text(
            task="editor_transform",
            prompt="prompt",
            validate=lambda out: [],
            fallback_system="system",
        ):
            if kind == "delta":
                deltas.append(str(value))
            elif kind == "result":
                result = value
        assert "".join(deltas) == text
        assert result is not None
        assert result.output_text == text == sync_result.output_text


def test_stream_text_repairs_then_succeeds(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    _test_client, gateway, app = client
    gateway.responses.append("bad first attempt")
    gateway.responses.append("good second attempt.")
    with app.state.session_factory() as session:
        from app.ai.runner import TaskRunner

        runner = TaskRunner(session, gateway)
        events: list[str] = []
        result = None
        for kind, value in runner.stream_text(
            task="editor_transform",
            prompt="prompt",
            validate=lambda out: ["bad"] if "bad" in out else [],
            fallback_system="system",
        ):
            events.append(kind)
            if kind == "result":
                result = value
        assert events[-1] == "result"
        assert events.count("repair") == 1
        assert result is not None
        assert result.output_text == "good second attempt."
        assert result.rounds == 2


def test_stream_text_stop_breaks_early(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    _test_client, gateway, app = client
    gateway.responses.append("0123456789abcdefghijklmnopqrstuvwxyz")
    with app.state.session_factory() as session:
        from app.ai.runner import TaskRunner

        runner = TaskRunner(session, gateway)
        calls = {"n": 0}

        def stop() -> bool:
            calls["n"] += 1
            return calls["n"] >= 2

        deltas: list[str] = []
        result = None
        for kind, value in runner.stream_text(
            task="editor_transform",
            prompt="prompt",
            validate=lambda out: [],
            fallback_system="system",
            stop=stop,
        ):
            if kind == "delta":
                deltas.append(str(value))
            elif kind == "result":
                result = value
        assert len(deltas) == 1
        assert result is not None
        assert result.output_text == deltas[0]
