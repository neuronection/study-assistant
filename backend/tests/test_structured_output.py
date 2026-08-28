from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.ai.runner import AuditRef, TaskRunner
from app.ai.structured import QuizgenOut

VALID_QUIZGEN: dict[str, Any] = {
    "questions": [
        {
            "type": "single",
            "stem_md": "What is 2+2?",
            "options_md": ["3", "4"],
            "answer": {"index": 1},
            "explanation_md": "Basic addition.",
            "concepts": ["arithmetic"],
            "skill": "compute",
        }
    ]
}

INVALID_QUIZGEN: dict[str, Any] = {
    "questions": [
        {
            "type": "single",
            "stem_md": "What is 2+2?",
            "options_md": ["4", "4"],
            "answer": {"index": 0},
            "explanation_md": "Basic addition.",
            "concepts": ["arithmetic"],
            "skill": "compute",
        }
    ]
}


def validate_quizgen(draft: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    questions = draft.get("questions")
    if not isinstance(questions, list) or not questions:
        problems.append("no questions")
        return problems
    for index, question in enumerate(questions):
        options = question.get("options_md")
        answer = question.get("answer")
        if not isinstance(options, list) or len(options) < 2:
            problems.append(f"q{index}: need at least two options")
            continue
        if isinstance(answer, dict) and answer.get("index") is not None:
            chosen = options[int(answer["index"])]
            if options.count(chosen) > 1:
                problems.append(f"q{index}: distractor equals answer")
        if not str(question.get("stem_md", "")).strip():
            problems.append(f"q{index}: empty stem")
    return problems


class StructuredFake(LLMGateway):
    def __init__(
        self,
        caps: list[str],
        structured_responses: list[dict[str, Any] | None],
        text_responses: list[str] | None = None,
    ) -> None:
        super().__init__(session_factory=None)
        self.caps = caps
        self.structured = list(structured_responses)
        self.text = list(text_responses or [])
        self.structured_calls = 0
        self.generate_calls = 0

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="fake",
            label="fake",
            caps=self.caps,
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.generate_calls += 1
        return self.text.pop(0) if self.text else '{"questions": []}'

    def generate_structured(
        self,
        task: str,
        messages: list[Message],
        schema: type[Any],
        course_id: int | None = None,
    ) -> dict[str, Any] | None:
        self.structured_calls += 1
        if "tools" not in self.caps:
            return None
        if not self.structured:
            return None
        return self.structured.pop(0)


@pytest.fixture
def runner(db_session: Session) -> TaskRunner:
    return TaskRunner(db_session, StructuredFake([], []))


def _run(db_session: Session, gateway: StructuredFake) -> Any:
    runner = TaskRunner(db_session, gateway)
    return runner.run_json(
        task="quizgen",
        prompt="Generate a quiz.",
        validate=validate_quizgen,
        fallback_system="You generate quizzes as JSON.",
        max_rounds=2,
        error_type=ValueError,
        audit=AuditRef("quizgen", None, "test"),
        schema=QuizgenOut,
    )


def test_structured_output_used_when_capable(db_session: Session) -> None:
    gateway = StructuredFake(["text", "tools"], [VALID_QUIZGEN])
    result = _run(db_session, gateway)
    assert result.problems == []
    assert result.rounds == 1
    assert gateway.structured_calls == 1
    assert gateway.generate_calls == 0
    assert result.draft["questions"][0]["stem_md"] == "What is 2+2?"


def test_structured_output_skipped_when_not_capable(db_session: Session) -> None:
    gateway = StructuredFake(["text"], [], text_responses=['{"questions": []}'])
    result = _run(db_session, gateway)
    assert result.problems  # empty questions -> validation fails
    assert gateway.generate_calls >= 1  # plain generate used
    assert gateway.structured_calls >= 1  # runner tried, gateway declined


def test_content_invalid_draft_still_enters_repair(db_session: Session) -> None:
    gateway = StructuredFake(["text", "tools"], [INVALID_QUIZGEN, VALID_QUIZGEN])
    result = _run(db_session, gateway)
    assert result.problems == []
    assert result.rounds == 2
    assert gateway.structured_calls == 2
    assert "distractor equals answer" not in " ".join(result.problems)


def test_structured_degrades_to_plain_generate(db_session: Session) -> None:
    gateway = StructuredFake(["text", "tools"], [None], text_responses=['{"questions": []}'])
    result = _run(db_session, gateway)
    assert gateway.structured_calls >= 1
    assert gateway.generate_calls >= 1
    assert result.problems


def test_gateway_structured_cap_gate_makes_no_request() -> None:
    import httpx

    gateway = LLMGateway(
        None,
        transport=httpx.MockTransport(lambda request: httpx.Response(500, text="boom")),
    )
    ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="m",
        label="m",
        caps=["text"],
        api_key="k",
    )
    result = gateway.generate_structured(
        "chat", [Message(role="user", content="hi")], QuizgenOut
    )
    assert result is None


def test_audit_recorded_with_structured_output(db_session: Session) -> None:
    from sqlalchemy import text

    gateway = StructuredFake(["text", "tools"], [VALID_QUIZGEN])
    _run(db_session, gateway)
    db_session.flush()
    rows = db_session.execute(
        text("SELECT context_type, task, model FROM ai_interactions")
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "quizgen"
    assert rows[0][1] == "quizgen"
    assert rows[0][2] == "fake"
