import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, add_material, make_course

from app.ai.contracts.contracts import CHAT_ANSWER_CONTRACT, Constraint, validate
from app.ai.mentions import MentionRegistry, registry_from_json
from app.core.config import Settings
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


QUIZ_JSON = json.dumps(
    {
        "questions": [
            {
                "type": "truefalse",
                "stem_md": "Differentiate compositions.",
                "answer": {"value": True},
                "explanation_md": "See [M{mid}] for the chain rule.",
                "concepts": ["chain rule"],
                "skill": "conceptual",
                "bloom": "remember",
                "difficulty": 1,
                "expected_time_sec": 30,
            }
        ]
    }
)

EXERCISE_JSON = json.dumps(
    {
        "title": "Chain practice",
        "context_md": "Based on [M{mid}].",
        "difficulty": 2,
        "steps": [
            {
                "prompt_md": "Differentiate $x^2 \\sin(x)$ (from [M{mid}]).",
                "expected_kind": "math",
                "expected_value": "2*x*sin(x) + x**2*cos(x)",
            }
        ],
    }
)


def test_registry_parse_dedup_and_order() -> None:
    registry = MentionRegistry()
    registry.add("material", 12, "Lecture 3")
    registry.add("note", 3, "My note")
    registry.add("concept", 7, "chain rule")
    used = registry.parse("start [M12] mid [C7] again [M12] end [N3]")
    assert [entry.ref for entry in used] == ["M12", "C7", "N3"]
    assert used[0].title == "Lecture 3"
    assert used[0].kind == "material"
    assert used[0].id == 12


def test_registry_unknown_handles_left_out() -> None:
    registry = MentionRegistry()
    registry.add("material", 12, "Lecture 3")
    assert registry.parse("see [M999] and [X12]") == []
    assert registry.out_of_range("see [M999] [M12]") == ["M999"]


def test_registry_stable_titles_and_roundtrip() -> None:
    registry = MentionRegistry()
    registry.add("material", 12, "Lecture 3")
    registry.add("material", 12, "Renamed later")
    first = registry.get("M12")
    assert first is not None and first.title == "Lecture 3"
    restored = registry_from_json(registry.to_json())
    again = restored.get("M12")
    assert again is not None and again.title == "Lecture 3"
    assert registry_from_json(None).refs() == []
    broken = registry_from_json([{"kind": "material"}])
    assert len(broken) == 0


def test_registry_prompt_section_teaches_handles() -> None:
    registry = MentionRegistry()
    registry.add("material", 12, "Lecture 3")
    section = registry.prompt_section()
    assert "M12 = Lecture 3" in section
    assert "clickable" in section
    assert MentionRegistry().prompt_section() == ""


def test_mentions_in_range_blocking_and_advisory() -> None:
    context = {"mention_refs": ["M12"]}
    blocking = validate("uses [M13]", [Constraint("mentions_in_range")], context)
    assert not blocking.ok
    advisory = validate("uses [M13]", [Constraint("mentions_in_range", advisory=True)], context)
    assert advisory.ok
    assert [v.constraint for v in advisory.advisories] == ["mentions_in_range"]
    ok = validate("uses [M12]", [Constraint("mentions_in_range")], context)
    assert ok.ok and ok.advisories == []
    empty = validate("uses [M13]", [Constraint("mentions_in_range")], {})
    assert empty.ok


def test_chat_contract_carries_advisory_mention_constraint() -> None:
    kinds = [constraint.kind for constraint in CHAT_ANSWER_CONTRACT]
    assert "mentions_in_range" in kinds
    advisory = next(c for c in CHAT_ANSWER_CONTRACT if c.kind == "mentions_in_range")
    assert advisory.advisory is True


def test_chat_mention_resolved_stored_and_taught(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client,
            "chain.txt",
            "The chain rule differentiates composite functions.",
            course_id,
        )
        gateway.responses.append(f"The rule is in [M{material_id}] — see [1].")
        session = test_client.post("/api/v1/chat/sessions", json={"course_id": course_id}).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "where is the chain rule?"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert assistant["mentions"]
        assert assistant["mentions"][0]["ref"] == f"M{material_id}"
        assert assistant["mentions"][0]["kind"] == "material"
        assert assistant["mentions"][0]["title"]
        prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert f"M{material_id} = " in prompt
        assert "Referenceable items" in prompt


def test_chat_handles_stable_across_turns_and_unknown_ignored(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client,
            "stable.txt",
            "Integration by parts content.",
            course_id,
        )
        gateway.responses.append(f"First: see [M{material_id}] [1].")
        session = test_client.post("/api/v1/chat/sessions", json={"course_id": course_id}).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "turn one"},
        )
        first = wait_for_assistant(test_client, session["id"])
        assert first[-1]["mentions"][0]["ref"] == f"M{material_id}"

        gateway.responses.append(
            f"Still [M{material_id}], but [M999] does not exist and [1] stays a citation."
        )
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "turn two"},
        )
        second = wait_for_assistant(test_client, session["id"])
        refs = {mention["ref"] for mention in second[-1]["mentions"]}
        assert f"M{material_id}" in refs
        assert "M999" not in refs
        assert "[M999]" in second[-1]["markdown"]


def test_quizgen_explanation_carries_mentions(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client,
            "quiz.txt",
            "Derivatives of composite functions are covered here.",
            course_id,
        )
        gateway.responses.append(QUIZ_JSON.replace("{mid}", str(material_id)))
        generated = test_client.post(
            "/api/v1/quiz/generate",
            json={"course_id": course_id, "count": 1},
        )
        assert generated.status_code == 201, generated.text
        stored = _app.state.session_factory()
        from sqlalchemy import select

        from app.domain.models import Question

        rows = stored.scalars(
            select(Question).where(Question.activity_id == int(generated.json()["id"]))
        ).all()
        stored.close()
        assert rows
        explanation = rows[0].explanation[0]
        assert explanation.get("mentions")
        assert explanation["mentions"][0]["ref"] == f"M{material_id}"


def test_exgen_steps_carry_mentions(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client,
            "ex.txt",
            "Product rule and chain rule practice material.",
            course_id,
        )
        gateway.responses.append(EXERCISE_JSON.replace("{mid}", str(material_id)))
        generated = test_client.post(
            "/api/v1/exercises/generate",
            json={"course_id": course_id, "steps": 1},
        )
        assert generated.status_code == 201, generated.text
        exercise_id = int(generated.json()["id"])
        steps = test_client.get(f"/api/v1/exercises/{exercise_id}/steps").json()
        prompt_block = steps[0]["prompt"][0]
        assert prompt_block.get("mentions")
        assert prompt_block["mentions"][0]["ref"] == f"M{material_id}"
        stored = _app.state.session_factory()

        from app.domain.models import Exercise

        exercise = stored.get(Exercise, exercise_id)
        stored.close()
        assert exercise is not None
        context_blocks = exercise.context or []
        assert context_blocks[0].get("mentions")
        assert context_blocks[0]["mentions"][0]["ref"] == f"M{material_id}"


def test_chat_mention_registry_persisted_on_session(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client,
            "persist.txt",
            "Persistence of registry entries.",
            course_id,
        )
        gateway.responses.append(f"See [M{material_id}] [1].")
        session = test_client.post("/api/v1/chat/sessions", json={"course_id": course_id}).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "hello"},
        )
        wait_for_assistant(test_client, session["id"])
        stored = _app.state.session_factory()
        from sqlalchemy import select

        from app.domain.models import ChatSession

        row = stored.scalars(select(ChatSession).where(ChatSession.id == session["id"])).first()
        assert row is not None
        refs = {entry["ref"] for entry in (row.mention_registry or [])}
        assert f"M{material_id}" in refs
        stored.close()
