import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

SIGN_SLIP_DRILL = json.dumps(
    {
        "title": "Spot the sign slip",
        "kind": "error_spot",
        "prompt_md": "One line below is flawed. Identify it and supply the fix.",
        "difficulty": 2,
        "payload": {
            "prompt_md": "One line below is flawed. Identify it and supply the fix.",
            "lines": [
                "$d/dx (-3x^2) = 6x$",
                "At $x = 1$: $6$",
            ],
            "flaw_index": 0,
            "lines_correct": [
                "$d/dx (-3x^2) = -6x$",
                "At $x = 1$: $-6$",
            ],
            "answers_flawed": ["6*x", "6"],
            "answers_correct": ["-6*x", "6"],
            "correct_line": "$d/dx (-3x^2) = -6x$",
            "requires_fix": True,
            "rubric": [{"id": "sign", "text": "the flipped minus sign"}],
        },
    }
)

BROKEN_SEED_DRILL = json.dumps(
    {
        "title": "Broken seed",
        "kind": "error_spot",
        "prompt_md": "One line below is flawed. Identify it and supply the fix.",
        "payload": {
            "prompt_md": "One line below is flawed. Identify it and supply the fix.",
            "lines": [
                "$d/dx (-3x^2) = 6x$",
                "At $x = 1$: $6$",
            ],
            "flaw_index": 0,
            "lines_correct": [
                "$d/dx (-3x^2) = -6x$",
                "At $x = 1$: $-6$",
            ],
            "answers_flawed": ["3*x", "6"],
            "answers_correct": ["-6*x", "6"],
            "correct_line": "$d/dx (-3x^2) = -6x$",
            "requires_fix": True,
            "rubric": [{"id": "sign", "text": "the flipped minus sign"}],
        },
    }
)


class DrillGateway(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="drill-model",
            label="drill-model",
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
        return self.responses.pop(0)


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


@pytest.fixture
def drill_client() -> Iterator[TestClient]:
    gateway = DrillGateway([SIGN_SLIP_DRILL])
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-error-spot-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        yield client


def make_math_course(client: TestClient) -> int:
    types = {
        entry["key"]: entry["id"]
        for entry in client.get("/api/v1/skills/course-types").json()
    }
    created = client.post(
        "/api/v1/courses",
        json={"title": "Calculus", "course_type_id": types.get("math")},
    )
    return int(created.json()["id"])


def run_drill(client: TestClient, course_id: int) -> Any:
    created = client.post(
        "/api/v1/exercises/drills",
        json={"pattern": "sign_slip", "course_id": course_id},
    )
    assert created.status_code == 201, created.text
    return created.json()


def answer(client: TestClient, session_id: int, response: Any) -> Any:
    payload = response if isinstance(response, str) else json.dumps(response)
    result = client.post(
        f"/api/v1/exercises/sessions/{session_id}/answer", json={"response": payload}
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_drill_builds_provable_error_spot_exercise(drill_client: TestClient) -> None:
    course_id = make_math_course(drill_client)
    exercise = run_drill(drill_client, course_id)
    assert exercise["kind"] == "error_spot"
    steps = drill_client.get(f"/api/v1/exercises/{exercise['id']}/steps").json()
    widget = steps[0]["input"]
    assert widget["widget"] == "lines"
    assert widget["requires_fix"] is True
    assert "flaw_index" not in widget
    assert "answers_correct" not in widget


def test_seeded_fix_grades_through_the_chain(drill_client: TestClient) -> None:
    course_id = make_math_course(drill_client)
    exercise = run_drill(drill_client, course_id)

    session = drill_client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
    good = answer(
        drill_client,
        session["id"],
        {"picked": [0], "fix": "-6*x"},
    )
    assert good["correct"] is True
    assert "correction" in good["stage"]

    session2 = drill_client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
    wrong_fix = answer(
        drill_client,
        session2["id"],
        {"picked": [0], "fix": "6*x"},
    )
    assert wrong_fix["correct"] is False
    assert "not equivalent" in wrong_fix["stage"]

    session3 = drill_client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
    missing_fix = answer(drill_client, session3["id"], {"picked": [0], "fix": ""})
    assert missing_fix["correct"] is False
    assert "corrected line" in missing_fix["stage"]

    session4 = drill_client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
    wrong_pick = answer(
        drill_client,
        session4["id"],
        {"picked": [1], "fix": "-6*x"},
    )
    assert wrong_pick["correct"] is False
    assert "wrong line" in wrong_pick["stage"]


def test_spotted_counts_track_correct_picks(drill_client: TestClient) -> None:
    course_id = make_math_course(drill_client)
    exercise = run_drill(drill_client, course_id)
    session = drill_client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
    answer(drill_client, session["id"], {"picked": [0], "fix": "-6*x"})

    patterns = drill_client.get(
        f"/api/v1/exercises/drills/patterns?course_id={course_id}"
    ).json()
    sign_slip = next(entry for entry in patterns if entry["pattern"] == "sign_slip")
    assert sign_slip["spotted"] == 1


def test_unseeded_flaw_is_rejected_into_repair() -> None:
    gateway = DrillGateway([BROKEN_SEED_DRILL, SIGN_SLIP_DRILL])
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-error-spot-repair-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=gateway,
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        course_id = make_math_course(client)
        created = client.post(
            "/api/v1/exercises/drills",
            json={"pattern": "sign_slip", "course_id": course_id},
        )
        assert created.status_code == 201, created.text
        assert gateway.responses == []
        steps = client.get(f"/api/v1/exercises/{created.json()['id']}/steps").json()
        assert steps[0]["input"]["requires_fix"] is True


def test_legacy_pick_response_still_graded_deterministically(
    drill_client: TestClient,
) -> None:
    course_id = make_math_course(drill_client)
    exercise = run_drill(drill_client, course_id)
    steps = drill_client.get(f"/api/v1/exercises/{exercise['id']}/steps").json()
    assert steps[0]["input"]["requires_fix"] is True

    session = drill_client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
    bare = answer(drill_client, session["id"], 1)
    assert bare["correct"] is False
    assert "wrong line" in bare["stage"]

    session2 = drill_client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
    listed = answer(drill_client, session2["id"], json.dumps([0]))
    assert listed["correct"] is False
    assert "corrected line" in listed["stage"]
