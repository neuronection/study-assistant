import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app
from app.services.study.exercise_rubric import validate_rubric_payload
from app.services.study.exercise_structs import (
    check_structural,
    public_input,
    validate_structural_payload,
)

MATCHING_DRAFT = json.dumps(
    {
        "title": "Derivative pairs",
        "kind": "matching",
        "prompt_md": "Match each function to its derivative.",
        "difficulty": 2,
        "payload": {
            "pairs": [
                {"left": "$x^2$", "right": "$2x$"},
                {"left": "$\\sin x$", "right": "$\\cos x$"},
                {"left": "$e^x$", "right": "$e^x$"},
                {"left": "$\\ln x$", "right": "$1/x$"},
            ]
        },
    }
)

ORDERING_DRAFT = json.dumps(
    {
        "title": "Steps of u-substitution",
        "kind": "ordering",
        "prompt_md": "Put the steps in the correct order.",
        "payload": {
            "items": [
                "Identify the inner function",
                "Substitute $u$",
                "Integrate in $u$",
                "Substitute back",
                "Simplify",
            ]
        },
    }
)

CATEGORIZE_DRAFT = json.dumps(
    {
        "title": "Even or odd",
        "kind": "categorize",
        "prompt_md": "Sort each function.",
        "payload": {
            "categories": ["even", "odd"],
            "items": [
                {"label": "$x^2$", "category": 0},
                {"label": "$x^3$", "category": 1},
                {"label": "$\\cos x$", "category": 0},
                {"label": "$\\sin x$", "category": 1},
            ],
        },
    }
)

FILL_BLANK_DRAFT = json.dumps(
    {
        "title": "Power rule",
        "kind": "fill_blank",
        "prompt_md": "Fill in the blanks.",
        "payload": {
            "prompt_md": "The derivative of $x^n$ is {{1}} and of a constant is {{2}}.",
            "answers": ["$nx^{n-1}$", ["0", "zero"]],
        },
    }
)

class StructsGateway(LLMGateway):
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
            external_id="exgen-model",
            label="exgen-model",
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


def make_client(responses: list[str]) -> TestClient:
    tmp = Path(tempfile.mkdtemp(prefix="ca-structs-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=StructsGateway(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient) -> int:
    return int(client.post("/api/v1/courses", json={"title": "Test course"}).json()["id"])


DRAFTS = {
    "matching": MATCHING_DRAFT,
    "ordering": ORDERING_DRAFT,
    "categorize": CATEGORIZE_DRAFT,
    "fill_blank": FILL_BLANK_DRAFT,
}


def test_validate_structural_payload_accepts_and_rejects() -> None:
    assert (
        validate_structural_payload(
            "matching", json.loads(MATCHING_DRAFT)["payload"]
        )
        == []
    )
    problems = validate_structural_payload(
        "matching", {"pairs": [{"left": "a", "right": "b"}, {"left": "a", "right": "c"}]}
    )
    assert any("duplicate" in problem for problem in problems)
    assert validate_structural_payload("ordering", {"items": ["a", "b"]}) != []
    assert validate_structural_payload("ordering", {"items": ["a", "a", "c"]}) != []
    assert (
        validate_structural_payload(
            "categorize", {"categories": ["x"], "items": [{"label": "a", "category": 0}]}
        )
        != []
    )
    assert (
        validate_structural_payload(
            "categorize", {"categories": ["x", "y"], "items": [{"label": "a", "category": 5}]}
        )
        != []
    )
    assert (
        validate_structural_payload(
            "fill_blank", {"prompt_md": "{{1}} and {{3}}", "answers": ["a", "b"]}
        )
        != []
    )
    assert (
        validate_structural_payload("fill_blank", {"prompt_md": "no blanks", "answers": []})
        != []
    )


def test_check_structural_grading() -> None:
    ok, stage = check_structural(
        "matching", json.loads(MATCHING_DRAFT)["payload"], [0, 1, 2, 3]
    )
    assert ok and stage == "matching: correct"
    ok, stage = check_structural(
        "matching", json.loads(MATCHING_DRAFT)["payload"], [0, 1, 3, 2]
    )
    assert not ok and "2/4" in stage

    ok, _ = check_structural(
        "ordering", json.loads(ORDERING_DRAFT)["payload"], [0, 1, 2, 3, 4]
    )
    assert ok
    ok, stage = check_structural(
        "ordering", json.loads(ORDERING_DRAFT)["payload"], [4, 3, 2, 1, 0]
    )
    assert not ok and "1/5" in stage

    ok, _ = check_structural(
        "categorize", json.loads(CATEGORIZE_DRAFT)["payload"], [0, 1, 0, 1]
    )
    assert ok
    ok, stage = check_structural(
        "categorize", json.loads(CATEGORIZE_DRAFT)["payload"], [0, 0, 0, 1]
    )
    assert not ok and "3/4" in stage

    ok, _ = check_structural(
        "fill_blank", json.loads(FILL_BLANK_DRAFT)["payload"], ["$nx^{n-1}$", "zero"]
    )
    assert ok
    ok, _ = check_structural(
        "fill_blank", json.loads(FILL_BLANK_DRAFT)["payload"], ["wrong", "0"]
    )
    assert not ok

    assert check_structural("matching", {"pairs": []}, "garbage")[0] is False


def test_public_input_hides_answers() -> None:
    spec = public_input("matching", json.loads(MATCHING_DRAFT)["payload"], seed=7)
    assert spec["widget"] == "matching"
    assert [entry["label"] for entry in spec["rights"]] != [
        "$2x$",
        "$\\cos x$",
        "$e^x$",
        "$1/x$",
    ]
    assert sorted(entry["index"] for entry in spec["rights"]) == [0, 1, 2, 3]

    spec = public_input("ordering", json.loads(ORDERING_DRAFT)["payload"], seed=7)
    assert [entry["id"] for entry in spec["items"]] != [0, 1, 2, 3, 4]
    assert sorted(entry["id"] for entry in spec["items"]) == [0, 1, 2, 3, 4]

    spec = public_input("fill_blank", json.loads(FILL_BLANK_DRAFT)["payload"], seed=7)
    assert spec["blank_count"] == 2
    assert "answers" not in spec


def test_generate_each_structural_kind_and_answer_flow() -> None:
    for kind, draft in DRAFTS.items():
        client = make_client([draft])
        course_id = make_course(client)
        created = client.post(
            "/api/v1/exercises/generate",
            json={"course_id": course_id, "topic": "derivatives", "kind": kind},
        )
        assert created.status_code == 201, (kind, created.text)
        exercise = created.json()
        assert exercise["kind"] == kind
        assert exercise["step_count"] == 1

        steps = client.get(f"/api/v1/exercises/{exercise['id']}/steps").json()
        assert steps[0]["kind"] == kind
        assert steps[0]["input"]["widget"] == kind

        session = client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
        wrong = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer",
            json={"response": _wrong_response(kind, steps[0]["input"])},
        )
        assert wrong.status_code == 200, (kind, wrong.text)
        assert wrong.json()["correct"] is False
        assert wrong.json()["error_class"] is None
        session = wrong.json()["session"]
        assert session["status"] == "active"

        right = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer",
            json={"response": _right_response(kind)},
        )
        assert right.status_code == 200, (kind, right.text)
        assert right.json()["correct"] is True
        assert right.json()["session"]["status"] == "completed"


def _right_response(kind: str) -> Any:
    if kind == "matching":
        return [0, 1, 2, 3]
    if kind == "ordering":
        return [0, 1, 2, 3, 4]
    if kind == "categorize":
        return [0, 1, 0, 1]
    return ["$nx^{n-1}$", "0"]


def _wrong_response(kind: str, widget: dict[str, Any]) -> Any:
    if kind == "matching":
        return [1, 0, 3, 2]
    if kind == "ordering":
        return [4, 3, 2, 1, 0]
    if kind == "categorize":
        return [1, 0, 1, 0]
    return ["wrong", "wrong"]


def test_generate_rejects_unknown_kind() -> None:
    client: TestClient = make_client([])
    course_id = make_course(client)
    response = client.post(
        "/api/v1/exercises/generate",
        json={"course_id": course_id, "kind": "telepathy"},
    )
    assert response.status_code == 422

EXPLAIN_DRAFT = json.dumps(
    {
        "title": "Explain the chain rule",
        "kind": "explain",
        "prompt_md": "Explain the chain rule in your own words.",
        "payload": {
            "prompt_md": "Explain the chain rule in your own words.",
            "rubric": [
                {"id": "composite", "text": "mentions differentiating a composite function"},
                {"id": "outer", "text": "names the outer function derivative"},
                {"id": "inner", "text": "names multiplying by the inner derivative"},
            ],
        },
    }
)

ERROR_SPOT_DRAFT = json.dumps(
    {
        "title": "Spot the error",
        "kind": "error_spot",
        "prompt_md": "One line below is flawed. Identify it.",
        "payload": {
            "prompt_md": "One line below is flawed. Identify it.",
            "lines": [
                "$d/dx (3x^2) = 6x$",
                "$d/dx (\\sin(2x)) = \\cos(2x)$",
                "$d/dx (e^x) = e^x$",
            ],
            "flaw_index": 1,
            "rubric": [
                {"id": "chain", "text": "the missing inner derivative factor 2"}
            ],
        },
    }
)

CORRECT_SOLUTION_DRAFT = json.dumps(
    {
        "title": "Fix the derivative",
        "kind": "correct_solution",
        "prompt_md": "Correct the flawed line.",
        "payload": {
            "prompt_md": "Fix: $d/dx (\\sin(2x)) = \\cos(2x)$",
            "fix": "2\\cos(2x)",
            "rubric": [
                {"id": "factor", "text": "restores the inner-derivative factor 2"}
            ],
        },
    }
)

RUBRIC_GRADE = json.dumps(
    {
        "verdict": "correct",
        "score": 1.0,
        "rationale": [
            {"rubric_id": "composite", "reason": "clearly stated"},
            {"rubric_id": "outer", "reason": "named f'"},
            {"rubric_id": "inner", "reason": "named g'"},
        ],
    }
)

RUBRIC_DRAFTS = {
    "explain": EXPLAIN_DRAFT,
    "error_spot": ERROR_SPOT_DRAFT,
    "correct_solution": CORRECT_SOLUTION_DRAFT,
}


def test_validate_rubric_payload() -> None:
    for draft in RUBRIC_DRAFTS.values():
        payload = json.loads(draft)["payload"]
        kind = json.loads(draft)["kind"]
        assert validate_rubric_payload(kind, payload) == [], kind
    assert (
        validate_rubric_payload("explain", {"rubric": []}) != []
    )
    assert (
        validate_rubric_payload(
            "explain",
            {"rubric": [{"id": "a", "text": "t"}, {"id": "a", "text": "u"}]},
        )
        != []
    )
    assert (
        validate_rubric_payload(
            "error_spot", {"rubric": [{"id": "a", "text": "t"}], "lines": ["x"], "flaw_index": 0}
        )
        != []
    )
    assert (
        validate_rubric_payload(
            "error_spot",
            {
                "rubric": [{"id": "a", "text": "t"}],
                "lines": ["a", "b"],
                "flaw_index": 9,
            },
        )
        != []
    )
    assert (
        validate_rubric_payload(
            "correct_solution", {"rubric": [{"id": "a", "text": "t"}], "fix": "  "}
        )
        != []
    )


def test_rubric_generate_and_ai_graded_answer_flow() -> None:
    for kind, draft in RUBRIC_DRAFTS.items():
        client = make_client([draft, RUBRIC_GRADE])
        course_id = make_course(client)
        created = client.post(
            "/api/v1/exercises/generate",
            json={"course_id": course_id, "topic": "chain rule", "kind": kind},
        )
        assert created.status_code == 201, (kind, created.text)
        exercise = created.json()
        assert exercise["kind"] == kind

        steps = client.get(f"/api/v1/exercises/{exercise['id']}/steps").json()
        widget = steps[0]["input"]
        assert steps[0]["kind"] == kind
        if kind == "error_spot":
            assert widget["widget"] == "lines"
            assert widget["lines"] == json.loads(ERROR_SPOT_DRAFT)["payload"]["lines"]
            assert "flaw_index" not in widget
            assert "rubric" not in widget
        if kind == "correct_solution":
            assert widget["widget"] == "math"
            assert "fix" not in widget
        if kind == "explain":
            assert widget["widget"] == "essay"
            assert "rubric" not in widget

        session = client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
        answer = client.post(
            f"/api/v1/exercises/sessions/{session['id']}/answer",
            json={
                "response": (
                    "The chain rule differentiates a composite: "
                    "outer f' times inner g'."
                )
            },
        )
        assert answer.status_code == 200, (kind, answer.text)
        assert answer.json()["correct"] is True
        assert answer.json()["session"]["status"] == "completed"


def test_error_spot_exact_pick_skips_llm_and_wrong_pick_reports() -> None:
    client = make_client([ERROR_SPOT_DRAFT])
    course_id = make_course(client)
    exercise = client.post(
        "/api/v1/exercises/generate",
        json={"course_id": course_id, "kind": "error_spot"},
    ).json()
    session = client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()

    good = client.post(
        f"/api/v1/exercises/sessions/{session['id']}/answer",
        json={"response": json.dumps([1])},
    )
    assert good.status_code == 200
    assert good.json()["correct"] is True
    assert "error_spot: correct" in good.json()["stage"]

    session2 = client.post(f"/api/v1/exercises/{exercise['id']}/sessions").json()
    bad = client.post(
        f"/api/v1/exercises/sessions/{session2['id']}/answer",
        json={"response": json.dumps([0])},
    )
    assert bad.status_code == 200
    assert bad.json()["correct"] is False
    assert "wrong line" in bad.json()["stage"]
