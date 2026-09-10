import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from sqlalchemy import select
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.core.config import Settings
from app.domain.models import Activity, Exercise, Job, Material, MaterialLink, Profile
from app.main import create_app

GENESIS_DRAFT: dict[str, Any] = {
    "title": "Linear Algebra for Economists",
    "description": "Foundations of linear algebra with economic applications.",
    "subject": "Mathematics",
    "level": "university-intro",
    "goals": ["Master matrices", "Understand eigenvalues"],
    "chapters": [
        {
            "title": "Vectors",
            "summary": "Vector basics.",
            "sections": [
                {"title": "Vector spaces", "objectives": ["Define a vector space"]},
                {"title": "Norms", "objectives": ["Compute a norm"]},
            ],
        },
        {
            "title": "Matrices",
            "summary": "Matrix algebra.",
            "sections": [
                {"title": "Multiplication", "objectives": ["Multiply matrices"]}
            ],
        },
    ],
}

LESSON_DOC = (
    "# Vectors — lesson\n\n"
    "A vector space is a set closed under addition and scalar multiplication.\n"
    "For example, $\\mathbb{R}^2$ with component-wise addition is a vector space.\n\n"
    "## Worked example\n\nCompute the norm of $(3, 4)$: "
    "$\\|(3,4)\\| = \\sqrt{9+16} = 5$.\n\n"
    "## Common pitfalls\n\n- Confusing vectors with points.\n"
    "- Forgetting that the zero vector must belong to the space.\n\n"
    "Practice by checking closure axioms on concrete sets until the definitions "
    "feel mechanical rather than memorised."
)

BAD_JSON = "not json at all"


def cards_payload(prefix: str = "vector", count: int = 10) -> str:
    cards = [
        {
            "kind": "basic",
            "front_md": f"What is a {prefix} concept #{i}?",
            "back_md": f"A {prefix} fact #{i}.",
        }
        for i in range(count)
    ]
    return json.dumps({"cards": cards})


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


class GenesisGateway(ScriptedGateway):
    """Routes by prompt so task ordering/repair rounds can't skew the script."""

    def generate(
        self,
        task: str,
        messages: Any,
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.calls.append(list(messages))
        prompt = "\n".join(str(message.content) for message in messages)
        if "Compose a lesson" in prompt:
            return LESSON_DOC
        if "flashcards from the following source" in prompt:
            prefix = "matrix" if "Matrices" in prompt else "vector"
            return cards_payload(prefix)
        return BAD_JSON


@fixture
def genesis_gateway() -> GenesisGateway:
    return GenesisGateway([])


@fixture
def genesis_client(
    tmp_path: Path, genesis_gateway: GenesisGateway
) -> Iterator[tuple[TestClient, GenesisGateway, FastAPI]]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=genesis_gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, genesis_gateway, app


def wait_job(client: TestClient, job_id: int, status: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30.0
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        jobs: list[dict[str, Any]] = client.get("/api/v1/jobs?type=genesis").json()
        found = next((entry for entry in jobs if entry["id"] == job_id), None)
        if found is not None:
            last = found
            if found.get("status") == status:
                return found
        time.sleep(0.05)
    raise AssertionError(f"job never reached {status}; last={last!r}")


def test_genesis_draft_returns_validated_outline(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        gateway.responses.append(json.dumps(GENESIS_DRAFT))
        response = test_client.post(
            "/api/v1/courses/genesis/draft",
            json={"topic": "Linear algebra", "level": "university-intro"},
        )
        assert response.status_code == 200, response.text
        draft = response.json()
        assert draft["title"] == "Linear Algebra for Economists"
        assert len(draft["chapters"]) == 2
        assert draft["chapters"][0]["sections"][0]["objectives"] == [
            "Define a vector space"
        ]


def test_genesis_draft_rejects_malformed_output(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        gateway.responses.append('{"title": "no chapters here"}')
        response = test_client.post(
            "/api/v1/courses/genesis/draft", json={"topic": "Linear algebra"}
        )
        assert response.status_code == 422


def test_genesis_commit_creates_course_nodes_and_job(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        response = test_client.post(
            "/api/v1/courses/genesis",
            json={"draft": GENESIS_DRAFT, "lessons": True},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        course = body["course"]
        assert course["origin"] == "genesis"
        assert course["hidden"] is False
        assert body["job_id"] is not None
        assert body["estimated_tasks"] == 2

        tree = test_client.get(f"/api/v1/courses/{course['id']}/tree").json()
        root = tree[0]
        chapters = root["children"]
        assert [chapter["title"] for chapter in chapters] == ["Vectors", "Matrices"]
        vectors = chapters[0]["children"]
        assert [section["title"] for section in vectors] == [
            "Vector spaces",
            "Norms",
        ]
        assert vectors[0]["ai_hint"] == "Define a vector space"
        assert root["ai_hint"] is None

        stored = app.state.session_factory()
        try:
            job = stored.get(Job, int(body["job_id"]))
            assert job is not None
            assert job.type == "genesis"
            assert job.payload["course_id"] == course["id"]
        finally:
            stored.close()


def test_genesis_commit_without_generation_skips_job(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        response = test_client.post(
            "/api/v1/courses/genesis",
            json={"draft": GENESIS_DRAFT, "lessons": False},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["job_id"] is None
        assert body["estimated_tasks"] == 0


def test_genesis_commit_enforces_budget_cap(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        stored = app.state.session_factory()
        try:
            profile = stored.get(Profile, 1)
            assert profile is not None
            profile.preferences = {"genesis_task_cap": 1}
            stored.commit()
        finally:
            stored.close()
        response = test_client.post(
            "/api/v1/courses/genesis",
            json={"draft": GENESIS_DRAFT, "lessons": True},
        )
        assert response.status_code == 422
        assert "budget cap" in response.json()["detail"]


def test_genesis_job_generates_lessons_and_isolates_failures(
    genesis_client: tuple[TestClient, GenesisGateway, FastAPI],
) -> None:
    test_client, _gateway, app = genesis_client
    with test_client:
        response = test_client.post(
            "/api/v1/courses/genesis",
            json={
                "draft": GENESIS_DRAFT,
                "lessons": True,
                "quizzes": True,
                "flashcards": True,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        course_id = int(body["course"]["id"])
        job_id = int(body["job_id"])

        final = wait_job(test_client, job_id, "done")
        assert final["status"] == "done"

        stored = app.state.session_factory()
        try:
            lessons = stored.scalars(
                select(Material).where(Material.course_id == course_id)
            ).all()
            lesson_rows = [
                material
                for material in lessons
                if (material.provenance or {}).get("kind") == "lesson"
            ]
            assert len(lesson_rows) == 2
            for material in lesson_rows:
                link = stored.scalars(
                    select(MaterialLink).where(
                        MaterialLink.material_id == material.id
                    )
                ).first()
                assert link is not None
            quizzes = stored.scalars(
                select(Activity).where(
                    Activity.course_id == course_id, Activity.type == "quiz"
                )
            ).all()
            assert quizzes == []
            cards = stored.scalars(
                select(Exercise).where(
                    Exercise.course_id == course_id, Exercise.kind.like("card_%")
                )
            ).all()
            assert len(cards) == 20
        finally:
            stored.close()
