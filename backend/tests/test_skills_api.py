from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


class NoAI:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None

    def describe(
        self,
        title: str,
        markdown: str,
        course_id: int | None = None,
    ) -> dict[str, Any] | None:
        return None


class QuietGateway(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="quiet",
            label="quiet",
            caps=["text"],
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        return "ok"


def make_client() -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-skills-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=QuietGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def test_skills_seeded_from_code() -> None:
    client = make_client()
    with client:
        skills = {entry["key"]: entry for entry in client.get("/api/v1/skills").json()}
        assert "tutor.hint" in skills
        assert "chat.answer" in skills
        assert "quiz.generate" in skills
        assert skills["tutor.hint"]["is_system"] is True
        assert skills["notes.transcribe"]["name"] == "Handwriting OCR"

        notes_ocr = client.get("/api/v1/skills/notes.transcribe/versions").json()
        template = notes_ocr[0]["system_template"]
        assert "ONLY the text that is actually written" in template
        assert "Do NOT describe the image" in template
        assert "description in brackets" not in template

        versions = client.get("/api/v1/skills/tutor.hint/versions").json()
        assert len(versions) == 1
        assert versions[0]["scope_type"] == "system"
        assert versions[0]["is_active"] is True
        assert "ladder" in versions[0]["system_template"].lower()

        ct = {entry["key"]: entry for entry in client.get("/api/v1/skills/course-types").json()}
        assert set(ct) >= {"math", "science", "generic"}


def test_seed_refresh_updates_seed_name_and_description() -> None:
    import dataclasses
    import unittest.mock

    import app.ai.skills as skills_module
    import app.services.skills as services_skills
    from app.services.skills import seed_skills

    seed = next(entry for entry in skills_module.SEEDS if entry.key == "notes.transcribe")
    client = make_client()
    app = client.app
    assert isinstance(app, FastAPI)
    with client:
        renamed = dataclasses.replace(
            seed, name="Renamed OCR", description="Renamed description."
        )
        with unittest.mock.patch.object(
            services_skills,
            "SEEDS",
            [
                renamed,
                *(entry for entry in skills_module.SEEDS if entry.key != seed.key),
            ],
        ), app.state.session_factory() as session:
            seed_skills(session)
            session.commit()

        skills = {entry["key"]: entry for entry in client.get("/api/v1/skills").json()}
        assert skills["notes.transcribe"]["name"] == "Renamed OCR"
        assert skills["notes.transcribe"]["description"] == "Renamed description."


def test_resolution_chain_and_course_scoping() -> None:
    client = make_client()
    with client:
        math_type = next(
            entry for entry in client.get("/api/v1/skills/course-types").json()
            if entry["key"] == "math"
        )
        course = client.post(
            "/api/v1/courses",
            json={"title": "Calc", "course_type_id": math_type["id"]},
        ).json()
        assert course["course_type_id"] == math_type["id"]

        base_resolution = client.get("/api/v1/skills/tutor.hint/resolution").json()
        assert base_resolution["chain"]["system"].startswith("v")
        assert base_resolution["active"]["version"] == 1

        saved = client.post(
            "/api/v1/skills/tutor.hint/versions",
            json={
                "scope_type": "course_type",
                "scope_ref": math_type["id"],
                "system_template": "Math-mode Socratic tutor, {{hint_level}}.",
                "contract": {"max_words": 200, "no_answer_reveal": True},
            },
        )
        assert saved.status_code == 201, saved.text

        course_resolution = client.get(
            "/api/v1/skills/tutor.hint/resolution", params={"course_id": course["id"]}
        ).json()
        assert course_resolution["chain"]["course_type"].startswith("v")
        assert course_resolution["active"]["version"] == saved.json()["version"]
        assert "Socratic" in course_resolution["active"]["system_template"]

        generic_resolution = client.get("/api/v1/skills/tutor.hint/resolution").json()
        assert generic_resolution["active"]["version"] == 1


def test_versioning_activate_and_restore() -> None:
    client = make_client()
    with client:
        saved = client.post(
            "/api/v1/skills/tutor.hint/versions",
            json={
                "scope_type": "system",
                "system_template": "You are a Socratic tutor. Use {{hint_level}}.",
                "user_template": "Level {{hint_level}}: {{step_prompt}}",
                "contract": {"max_words": 200, "no_answer_reveal": True},
            },
        )
        assert saved.status_code == 201, saved.text
        v2 = saved.json()
        assert v2["version"] == 2
        assert v2["is_active"] is True

        versions = client.get("/api/v1/skills/tutor.hint/versions").json()
        by_version = {entry["version"]: entry for entry in versions}
        assert by_version[1]["is_active"] is False
        assert by_version[2]["is_active"] is True

        resolution = client.get("/api/v1/skills/tutor.hint/resolution").json()
        assert resolution["active"]["version"] == 2

        activate = client.post(f"/api/v1/skills/tutor.hint/versions/{by_version[1]['id']}/activate")
        assert activate.status_code == 200
        assert client.get("/api/v1/skills/tutor.hint/resolution").json()["active"]["version"] == 1

        restored = client.post("/api/v1/skills/tutor.hint/restore")
        assert restored.status_code == 200
        assert restored.json()["version"] == 1


def test_sandbox_test_run_and_contracts() -> None:
    client = make_client()
    with client:
        run = client.post(
            "/api/v1/skills/test-run",
            json={"skill_key": "tutor.hint", "context": {"hint_level": "2"}},
        )
        assert run.status_code == 200, run.text
        body = run.json()
        assert "tutor" in body["system"]
        kinds = {constraint["kind"] for constraint in body["constraints"]}
        assert "no_answer_reveal" in kinds
        assert "max_words" in kinds

        chat_run = client.post(
            "/api/v1/skills/test-run",
            json={"skill_key": "chat.answer", "context": {"user_question": "hi"}},
        ).json()
        chat_kinds = {entry["kind"] for entry in chat_run["constraints"]}
        assert "citation_if_context" in chat_kinds


def test_template_validation_and_course_type_creation() -> None:
    client = make_client()
    with client:
        bad = client.post(
            "/api/v1/skills/tutor.hint/versions",
            json={
                "scope_type": "system",
                "system_template": "Broken {{ template }} with unbalanced {{.",
            },
        )
        assert bad.status_code == 422

        created = client.post(
            "/api/v1/skills/course-types",
            json={"key": "history", "name": "History", "description": "Date precision."},
        )
        assert created.status_code == 201, created.text

        dup = client.post(
            "/api/v1/skills/course-types",
            json={"key": "history", "name": "History again", "description": ""},
        )
        assert dup.status_code == 422


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


def test_skill_version_logged_on_pipeline_calls() -> None:
    client = make_client()
    with client:
        exercise = client.post(
            "/api/v1/exercises",
            json={
                "title": "Squares",
                "course_id": make_course(client),
                "steps": [
                    {"prompt_md": "Compute $x \\cdot x$.", "expected": {"value": "x^2"}}
                ],
            },
        ).json()
        session_id = client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()["id"]
        client.post(
            f"/api/v1/exercises/sessions/{session_id}/hint", json={"level": 1}
        )

        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            from sqlalchemy import text

            row = db.execute(
                text(
                    "SELECT skill_version_id FROM ai_interactions "
                    "WHERE context_type = 'tutor' ORDER BY id DESC LIMIT 1"
                )
            ).one()
        assert row[0] is not None


def test_seed_refresh_updates_unmodified_system_v1_only() -> None:
    import dataclasses
    import unittest.mock

    import app.ai.skills as skills_module
    from app.services.skills import SkillService, seed_skills

    seed = next(entry for entry in skills_module.SEEDS if entry.key == "tutor.hint")
    original = seed.system_prompt

    client = make_client()
    app = client.app
    assert isinstance(app, FastAPI)
    with client:
        forked = client.post(
            "/api/v1/skills/tutor.hint/versions",
            json={
                "scope_type": "system",
                "system_template": "MY CUSTOM TEMPLATE stays untouched",
                "user_template": "",
                "contract": {},
            },
        )
        assert forked.status_code == 201, forked.text
        versions = client.get("/api/v1/skills/tutor.hint/versions").json()
        min(entry["id"] for entry in versions)

        import app.services.skills as services_skills

        mutated = original.replace("ladder", "escalator")
        assert mutated != original
        with unittest.mock.patch.object(
            services_skills,
            "SEEDS",
            [
                dataclasses.replace(seed, system_prompt=mutated),
                *(entry for entry in skills_module.SEEDS if entry.key != seed.key),
            ],
        ), app.state.session_factory() as session:
            seed_skills(session)
            session.commit()

        refreshed = {
            entry["version"]: entry
            for entry in client.get("/api/v1/skills/tutor.hint/versions").json()
        }
        assert "escalator" in refreshed[1]["system_template"]
        assert refreshed[2]["system_template"] == "MY CUSTOM TEMPLATE stays untouched"

        with app.state.session_factory() as session:
            service = SkillService(session)
            system_versions = service.versions("tutor.hint")
            assert [entry.version for entry in system_versions] == [1, 2]
            assert "escalator" in system_versions[0].system_template


def test_exgen_system_skill_teaches_structural_family() -> None:
    client = make_client()
    with client:
        {entry["key"]: entry for entry in client.get("/api/v1/skills").json()}
        versions = client.get("/api/v1/skills/exercise.generate/versions").json()
        template = versions[0]["system_template"]
        assert "multi-step" in template
        assert "matching" in template
        assert "families of exercises" in template
        assert "payload" in template
