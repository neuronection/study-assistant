import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai.contracts.contracts import Constraint, validate
from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


class ScriptedGateway(LLMGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(session_factory=None)
        self.responses = list(responses)
        self.calls: list[list[Message]] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="fake-chat",
            label="fake-chat",
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
        self.calls.append(messages)
        return self.responses.pop(0)

    def stream(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        text = self.generate(task, messages, model)
        for i in range(0, len(text), 8):
            yield text[i : i + 8]

    def stream_events(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        from app.ai.gateway import StreamChunk

        for delta in self.stream(task, messages, model):
            yield StreamChunk("text", delta)


class NoEmbedder:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None


class NoDescriber:
    def describe(
        self,
        title: str,
        markdown: str,
        course_id: int | None = None,
    ) -> dict[str, Any] | None:
        return None


@pytest.fixture
def make_chat_client(tmp_path: object) -> Callable[..., TestClient]:
    def _make(responses: list[str]) -> TestClient:
        gateway = ScriptedGateway(responses)
        app = create_app(
            Settings(data_dir=tmp_path, log_level="WARNING"),  # type: ignore[arg-type]
            gateway=gateway,
            embedder=NoEmbedder(),  # type: ignore[arg-type]
            describer=NoDescriber(),  # type: ignore[arg-type]
        )
        return TestClient(app)

    return _make


def wait_for_assistant(
    client: TestClient, session_id: int, timeout: float = 5.0
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw_messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()
        messages: list[dict[str, Any]] = raw_messages
        if messages and messages[-1]["role"] == "assistant":
            return messages
        time.sleep(0.05)
    raise AssertionError("assistant never replied")


def make_course(client: TestClient, title: str = "Chat course") -> int:
    return int(client.post("/api/v1/courses", json={"title": title}).json()["id"])


def add_material(client: TestClient, filename: str, content: str, course_id: int) -> int:
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, content.encode(), "text/plain")},
    )
    material_id: int = upload.json()["material"]["id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"] == "ready":
            return material_id
        time.sleep(0.05)
    raise AssertionError("material never ready")


def test_validate_citation_contract() -> None:
    context = {"chunks": [{"chunk_id": 1}]}
    ok = validate("answer [1] done", [Constraint("citation_if_context")], context)
    assert ok.ok
    bad = validate("no citations here", [Constraint("citation_if_context")], context)
    assert not bad.ok
    out_of_range = validate(
        "cites [3]", [Constraint("citations_in_range")], context
    )
    assert not out_of_range.ok
    no_context = validate("no citations", [Constraint("citation_if_context")], {})
    assert no_context.ok


def test_max_words_ignores_fenced_blocks() -> None:
    data = ", ".join(str(index) for index in range(500))
    output = f"Here is the graph.\n\n```chart\n{{\"data\": [{data}]}}\n```"
    result = validate(output, [Constraint("max_words", {"n": 400})], {})
    assert result.ok


def test_chat_turn_produces_cited_assistant_message(
    make_chat_client: Callable[..., TestClient],
) -> None:
    client = make_chat_client(["The chain rule states $f'(g(x))g'(x))$ — see [1] for details."])
    with client:
        material_id = add_material(
            client,
            "rules.txt",
            "The chain rule differentiates composite functions.",
            make_course(client),
        )
        session = client.post("/api/v1/chat/sessions", json={}).json()
        sent = client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "What is the chain rule?"},
        )
        assert sent.status_code == 200
        assert sent.json()["user_message"]["role"] == "user"

        messages = wait_for_assistant(client, session["id"])
        assistant = messages[-1]
        assert "[1]" in assistant["markdown"]
        assert assistant["citations"]
        assert assistant["citations"][0]["material_id"] == material_id
        assert assistant["grounded"] is True


def test_repair_loop_regenerates_on_missing_citation(
    make_chat_client: Callable[..., TestClient],
) -> None:
    client = make_chat_client(
        [
            "The answer is 42.",
            "Better: the answer follows from the material [1].",
        ]
    )
    with client:
        add_material(
            client, "deep.txt", "Contains the ultimate answer within.", make_course(client)
        )
        session = client.post("/api/v1/chat/sessions", json={}).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages", json={"content": "the answer?"}
        )
        messages = wait_for_assistant(client, session["id"])
        assert len(messages) == 2
        assert "[1]" in messages[-1]["markdown"]
        app = client.app
        assert isinstance(app, FastAPI)
        gateway = app.state.gateway
        assert isinstance(gateway, ScriptedGateway)
        assert len(gateway.calls) == 2
        second_prompt = _prompt_text(gateway.calls[1])
        assert "violated" in second_prompt.lower()


def _prompt_text(messages: list[Message]) -> str:
    return " ".join(
        message.content if isinstance(message.content, str) else "" for message in messages
    )


def test_uncited_answer_marked_not_grounded(make_chat_client: Callable[..., TestClient]) -> None:
    client = make_chat_client(["stubborn answer without any citations", "still no citations"])
    with client:
        add_material(client, "deep.txt", "Contains wisdom.", make_course(client))
        session = client.post("/api/v1/chat/sessions", json={}).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages", json={"content": "wisdom?"}
        )
        messages = wait_for_assistant(client, session["id"])
        assistant = messages[-1]
        assert assistant["grounded"] is False
        assert assistant["citations"] == []


def test_chat_scoped_to_course_materials(make_chat_client: Callable[..., TestClient]) -> None:
    client = make_chat_client(["scoped answer [1]"])
    with client:
        course = client.post("/api/v1/courses", json={"title": "Calc"}).json()
        other_course = client.post("/api/v1/courses", json={"title": "Biology"}).json()
        add_material(client, "inside.txt", "Chain rule lives here.", course["id"])
        add_material(
            client, "outside.txt", "Totally unrelated biology content.", other_course["id"]
        )
        session = client.post(
            "/api/v1/chat/sessions", json={"course_id": course["id"]}
        ).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages", json={"content": "chain rule"}
        )
        messages = wait_for_assistant(client, session["id"])
        cited_materials = {c["material_id"] for c in messages[-1]["citations"]}
        listing = client.get("/api/v1/materials", params={"course_id": course["id"]}).json()
        inside_ids = {m["id"] for m in listing}
        assert cited_materials <= inside_ids


def test_interaction_audit_logged(make_chat_client: Callable[..., TestClient]) -> None:
    client = make_chat_client(["audited answer [1]"])
    with client:
        add_material(client, "audit.txt", "auditable content", make_course(client))
        session = client.post("/api/v1/chat/sessions", json={}).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages", json={"content": "audit?"}
        )
        wait_for_assistant(client, session["id"])
        app = client.app
        assert isinstance(app, FastAPI)
        with app.state.session_factory() as db:
            rows = db.execute(
                text(
                    "SELECT model, input_tokens, output_tokens, latency_ms "
                    "FROM ai_interactions"
                )
            ).all()
        assert len(rows) == 1
        model, tokens_in, tokens_out, latency = rows[0]
        assert model == "fake-chat"
        assert tokens_in and tokens_out
        assert latency is not None and latency >= 0


def test_send_to_missing_session_404(make_chat_client: Callable[..., TestClient]) -> None:
    client = make_chat_client([])
    with client:
        response = client.post(
            "/api/v1/chat/sessions/999/messages", json={"content": "hello"}
        )
        assert response.status_code == 404
