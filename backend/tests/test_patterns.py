import json
from collections import defaultdict
from typing import Any

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app

EQUATION_QUIZ = json.dumps(
    {
        "questions": [
            {
                "type": "equation",
                "stem_md": "Differentiate $f(x) = x^2 \\sin x$.",
                "answer": {"value": "2*x*sin(x) + x^2*cos(x)"},
                "explanation_md": "Product rule.",
                "concepts": ["product rule"],
                "skill": "procedural",
                "bloom": "apply",
                "difficulty": 3,
                "expected_time_sec": 60,
                "sympy_check": {"expected": "2*x*sin(x) + x**2*cos(x)"},
            }
        ]
    }
)

ERROR_SPOT_DRILL_JSON = json.dumps(
    {
        "title": "Spot the dropped term",
        "kind": "error_spot",
        "prompt_md": "One line below is flawed. Identify it and supply the fix.",
        "difficulty": 2,
        "payload": {
            "prompt_md": "One line below is flawed. Identify it and supply the fix.",
            "lines": [
                "Let $f = x^2$ and $g = \\sin x$.",
                "$f' = 2x$ and $g' = \\cos x$.",
                "$f'g + fg' = 2x\\sin x$",
            ],
            "flaw_index": 2,
            "lines_correct": [
                "Let $f = x^2$ and $g = \\sin x$.",
                "$f' = 2x$ and $g' = \\cos x$.",
                "$f'g + fg' = 2x\\sin x + x^2\\cos x$",
            ],
            "answers_flawed": ["x**2", "2*x", "2*x*sin(x)"],
            "answers_correct": ["x**2", "2*x", "2*x*sin(x) + x**2*cos(x)"],
            "correct_line": "$f'g + fg' = 2x\\sin x + x^2\\cos x$",
            "requires_fix": True,
            "rubric": [
                {"id": "second_term", "text": "the missing $x^2\\cos x$ term"}
            ],
        },
    }
)

PROPOSALS_JSON = json.dumps(
    {
        "proposals": [
            {
                "key": "forgot_product_second_term",
                "name": "Forgot product second term",
                "description": "applying the product rule but dropping the second term",
                "example": "d/dx (fg) written as f'g instead of f'g + fg'",
            }
        ]
    }
)


class PatternGateway(LLMGateway):
    def __init__(self, responses: dict[str, list[str]]) -> None:
        super().__init__(session_factory=None)
        self.responses = {key: list(value) for key, value in responses.items()}
        self.calls: dict[str, list[list[Message]]] = defaultdict(list)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="pattern-model",
            label="pattern-model",
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
        self.calls[task].append(messages)
        return self.responses[task].pop(0)


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


def make_client(responses: dict[str, list[str]]) -> TestClient:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="ca-patterns-"))
    app = create_app(
        Settings(data_dir=tmp, log_level="WARNING"),
        gateway=PatternGateway(responses),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def make_course(client: TestClient, course_type: str | None = None) -> int:
    types = {
        entry["key"]: entry["id"]
        for entry in client.get("/api/v1/skills/course-types").json()
    }
    payload: dict[str, Any] = {"title": f"{course_type or 'generic'} course"}
    if course_type is not None:
        payload["course_type_id"] = types.get(course_type)
    return int(client.post("/api/v1/courses", json=payload).json()["id"])


def _wrong_equation(client: TestClient, course_id: int, response: str) -> dict[str, Any]:
    activity = client.post(
        "/api/v1/quiz/generate", json={"count": 1, "course_id": course_id}
    ).json()
    questions = client.get(
        f"/api/v1/quiz/activities/{activity['id']}/questions"
    ).json()
    attempt = client.post(
        f"/api/v1/quiz/activities/{activity['id']}/attempts"
    ).json()
    body = client.post(
        f"/api/v1/quiz/attempts/{attempt['id']}/answers",
        json={"question_id": questions[0]["id"], "response": response},
    )
    assert body.status_code == 200, body.text
    payload = body.json()
    assert isinstance(payload, dict)
    return payload


def test_drill_patterns_scoped_by_course_type() -> None:
    client = make_client({})
    with client:
        math = make_course(client, "math")
        entries = client.get(
            f"/api/v1/exercises/drills/patterns?course_id={math}"
        ).json()
        keys = {entry["pattern"] for entry in entries}
        assert "sign_slip" in keys
        assert "missing_chain_rule_factor" in keys
        assert all(entry["source"] == "seeded" for entry in entries)
        assert all(entry["occurrences"] == 0 for entry in entries)

        generic = make_course(client, "generic")
        bare = make_course(client, None)
        assert client.get(
            f"/api/v1/exercises/drills/patterns?course_id={generic}"
        ).json() == []
        assert client.get(
            f"/api/v1/exercises/drills/patterns?course_id={bare}"
        ).json() == []

        missing = client.get("/api/v1/exercises/drills/patterns")
        assert missing.status_code == 422


def test_deterministic_sign_slip_tags_wrong_equation() -> None:
    client = make_client({"quizgen": [EQUATION_QUIZ]})
    with client:
        math = make_course(client, "math")
        body = _wrong_equation(
            client, math, "-(2*x*sin(x) + x^2*cos(x))"
        )
        assert body["correct"] is False
        assert "sign_slip" in body["error_tags"]

        patterns = client.get(
            f"/api/v1/exercises/drills/patterns?course_id={math}"
        ).json()
        counts = {entry["pattern"]: entry["occurrences"] for entry in patterns}
        assert counts["sign_slip"] == 1
        assert counts["dropped_factor"] == 0


def test_no_detection_for_unrelated_wrong_answer() -> None:
    client = make_client({"quizgen": [EQUATION_QUIZ]})
    with client:
        math = make_course(client, "math")
        body = _wrong_equation(client, math, "x")
        assert "sign_slip" not in body["error_tags"]


def test_drill_rejects_unresolved_pattern() -> None:
    client = make_client({})
    with client:
        generic = make_course(client, "generic")
        drill = client.post(
            "/api/v1/exercises/drills",
            json={"pattern": "sign_slip", "course_id": generic},
        )
        assert drill.status_code == 422


def test_propose_empty_without_mistakes() -> None:
    client = make_client({})
    with client:
        math = make_course(client, "math")
        proposals = client.post(
            "/api/v1/exercises/drills/propose", json={"course_id": math}
        )
        assert proposals.status_code == 200
        assert proposals.json() == []


def test_propose_and_approve_discovered_pattern() -> None:
    client = make_client(
        {
            "quizgen": [EQUATION_QUIZ],
            "description": [PROPOSALS_JSON],
            "exgen": [ERROR_SPOT_DRILL_JSON],
        }
    )
    with client:
        math = make_course(client, "math")
        _wrong_equation(client, math, "2*x*sin(x)")

        proposals = client.post(
            "/api/v1/exercises/drills/propose", json={"course_id": math}
        )
        assert proposals.status_code == 200, proposals.text
        proposed = proposals.json()
        assert len(proposed) == 1
        assert proposed[0]["key"] == "forgot_product_second_term"

        created = client.post(
            "/api/v1/exercises/drills/patterns",
            json={
                "course_id": math,
                "key": proposed[0]["key"],
                "name": proposed[0]["name"],
                "description": proposed[0]["description"],
                "example": proposed[0]["example"],
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["source"] == "discovered"

        entries = client.get(
            f"/api/v1/exercises/drills/patterns?course_id={math}"
        ).json()
        discovered = {
            entry["pattern"]: entry for entry in entries
        }["forgot_product_second_term"]
        assert discovered["source"] == "discovered"
        assert discovered["occurrences"] == 0

        drill = client.post(
            "/api/v1/exercises/drills",
            json={"pattern": "forgot_product_second_term", "course_id": math},
        )
        assert drill.status_code == 201, drill.text

        duplicate = client.post(
            "/api/v1/exercises/drills/patterns",
            json={
                "course_id": math,
                "key": "forgot_product_second_term",
                "name": "dup",
                "description": "dup",
            },
        )
        assert duplicate.status_code == 422


def test_propose_validates_slugs_and_collisions() -> None:
    invalid = json.dumps(
        {
            "proposals": [
                {
                    "key": "UPPER-case!",
                    "name": "",
                    "description": "",
                },
                {
                    "key": "sign_slip",
                    "name": "dupe",
                    "description": "already seeded",
                },
            ]
        }
    )
    client = make_client(
        {"quizgen": [EQUATION_QUIZ], "description": [invalid, invalid, invalid]}
    )
    with client:
        math = make_course(client, "math")
        _wrong_equation(client, math, "2*x*sin(x)")
        proposals = client.post(
            "/api/v1/exercises/drills/propose", json={"course_id": math}
        )
        assert proposals.status_code == 422
