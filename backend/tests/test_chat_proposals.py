import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from sqlalchemy import select
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, add_material, make_course

from app.ai.contracts.contracts import Constraint, validate
from app.ai.proposals import (
    CreateNotePayload,
    extract_proposal,
    strip_proposal_fences,
    validate_proposal_text,
)
from app.core.config import Settings
from app.domain.models import AiInteraction, MaterialLink, NodeConcept, Note
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


VALID_PROPOSAL = (
    "Here is a summary [1].\n\n```proposal\n"
    + json.dumps(
        {
            "action": "create_note",
            "title": "Chain rule summary",
            "body_md": "The chain rule: $(f \\circ g)' = f'g \\cdot g'$.",
            "node_id": None,
        }
    )
    + "\n```"
)


def test_validate_proposal_text_good_bad_unknown() -> None:
    assert validate_proposal_text("plain answer") == []
    assert validate_proposal_text(VALID_PROPOSAL) == []
    bad_json = "```proposal\n{not json}\n```"
    assert any("valid JSON" in problem for problem in validate_proposal_text(bad_json))
    unknown = '```proposal\n{"action": "delete_everything"}\n```'
    assert any("unknown proposal action" in problem for problem in validate_proposal_text(unknown))
    missing = '```proposal\n{"action": "create_note", "title": ""}\n```'
    assert any("payload invalid" in problem for problem in validate_proposal_text(missing))
    twice = VALID_PROPOSAL + "\n" + VALID_PROPOSAL
    assert any("at most 1" in problem for problem in validate_proposal_text(twice))


def test_extract_and_strip() -> None:
    extracted = extract_proposal(VALID_PROPOSAL)
    assert extracted is not None
    action, payload = extracted
    assert action == "create_note"
    assert payload["title"] == "Chain rule summary"
    assert CreateNotePayload.model_validate(payload)
    stripped = strip_proposal_fences(VALID_PROPOSAL)
    assert "proposal" not in stripped
    assert "```" not in stripped
    assert extract_proposal("no fences") is None
    assert extract_proposal('```proposal\n{"action": "nope"}\n```') is None


def test_proposal_contract_blocks_invalid_and_repairs(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "m.txt", "chain rule content", course_id)
        gateway.responses.append(
            "```proposal\n" + json.dumps({"action": "make_coffee"}) + "\n```"
        )
        gateway.responses.append(VALID_PROPOSAL)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "summarize the chain rule and offer to save it"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert len(gateway.calls) == 2
        repair_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "unknown proposal action" in repair_prompt
        assert "```proposal" not in assistant["markdown"]
        assert assistant["proposals"]
        assert assistant["proposals"][0]["action"] == "create_note"
        assert assistant["proposals"][0]["status"] == "proposed"


def test_no_note_created_until_approved_and_approve_creates_it(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "m.txt", "chain rule content", course_id)
        gateway.responses.append(VALID_PROPOSAL)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "summarize and offer to save"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        proposal = messages[-1]["proposals"][0]

        def note_rows() -> int:
            stored = app.state.session_factory()
            count = len(stored.scalars(select(Note.id)).all())
            stored.close()
            return count

        assert note_rows() == 0

        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "executed"
        note_id = body["result"]["note_id"]
        assert note_rows() == 1
        stored = app.state.session_factory()
        note = stored.get(Note, note_id)
        assert note is not None
        assert note.tags == ["ai-proposal"]
        assert note.course_id == course_id
        audits = stored.scalars(
            select(AiInteraction).where(AiInteraction.context_type == "proposal")
        ).all()
        stored.close()
        assert len(audits) == 1
        assert audits[0].context_id == proposal["id"]

        again = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert again.status_code == 409
        assert note_rows() == 1


def test_dismiss_blocks_execution(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "m.txt", "body", course_id)
        gateway.responses.append(VALID_PROPOSAL)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "summarize"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        proposal = messages[-1]["proposals"][0]
        dismissed = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/dismiss")
        assert dismissed.status_code == 200
        assert dismissed.json()["status"] == "dismissed"
        approve_after = test_client.post(
            f"/api/v1/chat/proposals/{proposal['id']}/approve"
        )
        assert approve_after.status_code == 409
        stored = app.state.session_factory()
        assert len(stored.scalars(select(Note.id)).all()) == 0
        stored.close()


def test_proposals_disabled_without_course(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        gateway.responses.append(VALID_PROPOSAL)
        session = test_client.post("/api/v1/chat/sessions", json={}).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "summarize"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert assistant["proposals"] == []
        assert "proposal" not in assistant["markdown"]
        system_prompt = str(gateway.calls[0][0].content)
        assert "proposal" not in system_prompt


def test_contract_ignores_proposals_when_disabled() -> None:
    ok = validate(
        "```proposal\n{broken\n```",
        [Constraint("proposal_valid")],
        {"proposals_enabled": False},
    )
    assert ok.ok
    strict = validate(
        "```proposal\n{broken\n```",
        [Constraint("proposal_valid")],
        {"proposals_enabled": True},
    )
    assert not strict.ok


ASSIGN_PROPOSAL = (
    "```proposal\n"
    + json.dumps(
        {"action": "assign_material", "material_id": "{mid}", "node_id": "{nid}"}
    )
    + "\n```"
)


COVER_PROPOSAL = (
    "```proposal\n"
    + json.dumps({"action": "cover_concept", "concept_id": "{cid}", "node_id": "{nid}"})
    + "\n```"
)


GENERATE_PROPOSAL = (
    "```proposal\n"
    + json.dumps(
        {
            "action": "generate_quiz",
            "topic": "chain rule",
            "count": 5,
            "node_id": None,
        }
    )
    + "\n```"
)


def make_node(client: TestClient, course_id: int, title: str) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = int(tree[0]["id"])
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": title},
    )
    return int(created.json()["id"])


def get_proposal(client: TestClient, session_id: int) -> dict[str, Any]:
    messages = wait_for_assistant(client, session_id)
    proposals: list[dict[str, Any]] = messages[-1]["proposals"]
    assert proposals
    return proposals[0]


def test_assign_material_executes_and_is_idempotent(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "m.txt", "body", course_id)
        node_id = make_node(test_client, course_id, "Target")
        gateway.responses.append(
            "Summary [1].\n\n"
            + ASSIGN_PROPOSAL.replace("{mid}", str(material_id)).replace(
                "{nid}", str(node_id)
            )
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "assign it"},
        )
        proposal = get_proposal(test_client, session["id"])
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "executed"

        stored = app.state.session_factory()
        link = stored.scalars(
            select(MaterialLink).where(
                MaterialLink.node_id == node_id,
                MaterialLink.material_id == material_id,
            )
        ).first()
        assert link is not None
        assert link.rationale == "AI proposal"
        stored.close()

        stale_retry = test_client.post(
            f"/api/v1/chat/proposals/{proposal['id']}/approve"
        )
        assert stale_retry.status_code == 409


def test_revalidation_marks_stale_on_deleted_target(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "m.txt", "body", course_id)
        node_id = make_node(test_client, course_id, "Doomed")
        gateway.responses.append(
            "Sure [1].\n\n"
            + ASSIGN_PROPOSAL.replace("{mid}", str(material_id)).replace(
                "{nid}", str(node_id)
            )
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "go"},
        )
        proposal = get_proposal(test_client, session["id"])
        tree = test_client.get(f"/api/v1/courses/{course_id}/tree").json()
        root_id = int(tree[0]["id"])
        deleted = test_client.delete(
            f"/api/v1/nodes/{node_id}",
            params={"merge_into": root_id},
        )
        assert deleted.status_code < 400, deleted.text
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200
        body = approved.json()
        assert body["status"] == "stale"
        assert body["result"]["error"]


def test_cover_concept_executes(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "m.txt", "chain rule body", course_id)
        node_id = make_node(test_client, course_id, "Ch2")
        gateway.responses.append(
            json.dumps(
                {
                    "concepts": [
                        {"name": "Chain Rule", "description": "composites", "aliases": []}
                    ],
                    "links": [],
                }
            )
        )
        extracted = test_client.post(
            f"/api/v1/courses/{course_id}/concepts/extract", json={}
        )
        assert extracted.status_code == 200, extracted.text
        draft = extracted.json()
        committed = test_client.post(
            f"/api/v1/courses/{course_id}/concepts/commit",
            json={
                "concepts": draft["concepts"],
                "links": draft.get("links", []),
                "nodes": draft.get("nodes", []),
            },
        )
        assert committed.status_code == 200, committed.text
        concepts = test_client.get(
            f"/api/v1/courses/{course_id}/concepts"
        ).json()["concepts"]
        assert concepts
        concept_id = int(concepts[0]["id"])
        gateway.responses.append(
            "Cover it.\n\n"
            + COVER_PROPOSAL.replace("{cid}", str(concept_id)).replace(
                "{nid}", str(node_id)
            )
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "cover"},
        )
        proposal = get_proposal(test_client, session["id"])
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "executed"
        stored = app.state.session_factory()
        coverage = stored.scalars(
            select(NodeConcept).where(
                NodeConcept.node_id == node_id, NodeConcept.concept_id == concept_id
            )
        ).first()
        stored.close()
        assert coverage is not None


def test_generate_proposal_marks_approved_with_dialog_params(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "m.txt", "body", course_id)
        gateway.responses.append(f"Quiz yourself.\n\n{GENERATE_PROPOSAL}")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "quiz me"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "generate_quiz"
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "approved"
        assert body["result"]["open_dialog"]["topic"] == "chain rule"
        assert body["result"]["open_dialog"]["count"] == 5


def test_dismissal_feedback_injects_prompt_note(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "m.txt", "body", course_id)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        for _ in range(2):
            gateway.responses.append(VALID_PROPOSAL)
            test_client.post(
                f"/api/v1/chat/sessions/{session['id']}/messages",
                json={"content": "summarize"},
            )
            proposal = get_proposal(test_client, session["id"])
            dismissed = test_client.post(
                f"/api/v1/chat/proposals/{proposal['id']}/dismiss"
            )
            assert dismissed.status_code == 200
        gateway.responses.append("Fine, no proposal. [1]")
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "again"},
        )
        wait_for_assistant(test_client, session["id"])
        last_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "dismissed earlier proposals" in last_prompt
