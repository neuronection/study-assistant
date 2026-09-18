import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pytest import fixture
from sqlalchemy import select
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, add_material, make_course

from app.ai.contracts.contracts import Constraint, validate
from app.ai.proposals import (
    MAX_PROPOSALS_PER_TURN,
    PROPOSAL_ACTIONS,
    CreateNotePayload,
    extract_proposals,
    extract_proposals_with_drops,
    strip_proposal_fences,
    validate_proposal_text,
)
from app.core.config import Settings
from app.domain.models import AiInteraction, MaterialLink, NodeConcept, Note, NoteVersion
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
    assert validate_proposal_text(twice) == []
    over_cap = "\n".join([VALID_PROPOSAL] * (MAX_PROPOSALS_PER_TURN + 1))
    assert any("at most 3" in problem for problem in validate_proposal_text(over_cap))


def test_registry_is_complete_and_doc_is_assembled() -> None:
    from app.services.platform.proposal_actions import EXECUTORS

    assert MAX_PROPOSALS_PER_TURN == 3
    assert PROPOSAL_ACTIONS
    for action, spec in PROPOSAL_ACTIONS.items():
        if spec.api_executed:
            continue
        assert action in EXECUTORS, f"{action} has no executor"
        assert '{"action"' in spec.doc_line, f"{action} has no doc line"
    for action in EXECUTORS:
        assert action in PROPOSAL_ACTIONS, f"{action} has no spec"


def test_extract_and_strip() -> None:
    extracted = extract_proposals(VALID_PROPOSAL)
    assert len(extracted) == 1
    action, payload = extracted[0]
    assert action == "create_note"
    assert payload["title"] == "Chain rule summary"
    assert CreateNotePayload.model_validate(payload)
    stripped = strip_proposal_fences(VALID_PROPOSAL)
    assert "proposal" not in stripped
    assert "```" not in stripped
    assert extract_proposals("no fences") == []
    assert extract_proposals('```proposal\n{"action": "nope"}\n```') == []
    assert extract_proposals("```proposal\n{broken\n```") == []
    doubled = VALID_PROPOSAL + "\n" + VALID_PROPOSAL
    assert len(extract_proposals(doubled)) == 2
    over_cap = "\n".join([VALID_PROPOSAL] * (MAX_PROPOSALS_PER_TURN + 2))
    assert len(extract_proposals(over_cap)) == MAX_PROPOSALS_PER_TURN


def test_extract_proposals_with_drops_reason_codes() -> None:
    proposals, drops = extract_proposals_with_drops(VALID_PROPOSAL)
    assert drops == []
    assert len(proposals) == 1
    _, drops = extract_proposals_with_drops("no fences")
    assert drops == []
    _, drops = extract_proposals_with_drops("```proposal\n{broken\n```")
    assert drops == ["invalid_json"]
    _, drops = extract_proposals_with_drops('```proposal\n"just a string"\n```')
    assert drops == ["not_object"]
    _, drops = extract_proposals_with_drops(
        '```proposal\n{"action": "make_coffee"}\n```'
    )
    assert drops == ["unknown_action"]
    _, drops = extract_proposals_with_drops(
        '```proposal\n{"action": "create_note", "title": ""}\n```'
    )
    assert drops == ["schema"]
    over_cap = "\n".join([VALID_PROPOSAL] * (MAX_PROPOSALS_PER_TURN + 2))
    proposals, drops = extract_proposals_with_drops(over_cap)
    assert len(proposals) == MAX_PROPOSALS_PER_TURN
    assert drops == ["cap"]
    mixed = "\n".join(
        [
            VALID_PROPOSAL,
            "```proposal\n{broken\n```",
            '```proposal\n{"action": "nope"}\n```',
        ]
    )
    proposals, drops = extract_proposals_with_drops(mixed)
    assert len(proposals) == 1
    assert drops == ["invalid_json", "unknown_action"]


def test_dropped_proposals_surface_warning_and_trace(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    unfixable = (
        "Here you go.\n\n```proposal\n{broken\n```\n\n"
        + VALID_PROPOSAL
    )
    gateway.responses.append(unfixable)
    gateway.responses.append(unfixable)
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "m.txt", "chain rule content", course_id)
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
    assert len(assistant["proposals"]) == 1
    assert assistant["proposals"][0]["action"] == "create_note"
    assert any(
        "1 suggested action(s) dropped (invalid_json: 1)" in warning
        for warning in assistant["warnings"]
    )
    assert assistant["trace"]["proposals_dropped"] == ["invalid_json"]


def test_tools_catalog_lists_capabilities_as_non_executable(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    from app.ai.tools import (
        CAPABILITY_TOOL_NAMES,
        CHAT_CAPABILITY_CATALOG,
        build_tool_doc,
        native_tool_schemas,
        run_tool_line,
    )

    test_client, _gateway, _app = client
    with test_client:
        payload = test_client.get("/api/v1/ai/tools").json()
    capabilities = [tool for tool in payload["tools"] if tool.get("hitl")]
    assert {tool["name"] for tool in capabilities} == set(CAPABILITY_TOOL_NAMES)
    assert {tool["kind"] for tool in capabilities} == {"capability"}
    for tool in capabilities:
        assert tool["arguments"] == []
    plain_tool = {"name": "CALC", "description": "d", "arguments": []}
    doc = build_tool_doc([*CHAT_CAPABILITY_CATALOG, plain_tool])
    assert "PROPOSE_EDITS" not in doc
    assert "CALC" in doc
    assert native_tool_schemas(CHAT_CAPABILITY_CATALOG) == []
    for name in sorted(CAPABILITY_TOOL_NAMES):
        result = run_tool_line(name, "")
        assert result.startswith("error: HITL capability")


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


def make_note(client: TestClient, course_id: int, body_md: str) -> int:
    created = client.post(
        "/api/v1/notes",
        json={
            "course_id": course_id,
            "owner_type": "standalone",
            "title": "Derivation note",
            "body_md": body_md,
        },
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


EDIT_NOTE_PROPOSAL = (
    "```proposal\n"
    + json.dumps(
        {
            "action": "edit_note",
            "note_id": "{nid}",
            "new_body_md": "# Derivation note\n\nFixed: the derivative is $-2x$.",
            "reason": "sign error",
        }
    )
    + "\n```"
)

APPEND_NOTE_PROPOSAL = (
    "```proposal\n"
    + json.dumps(
        {
            "action": "append_note",
            "note_id": "{nid}",
            "markdown": "Extra worked example.",
            "heading": "Worked example",
        }
    )
    + "\n```"
)


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


def test_multiple_proposals_persist_and_approve_independently(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "m.txt", "body", course_id)
        node_id = make_node(test_client, course_id, "Ch3")
        assign = ASSIGN_PROPOSAL.replace("{mid}", str(material_id)).replace(
            "{nid}", str(node_id)
        )
        gateway.responses.append(f"Doing both.\n\n{VALID_PROPOSAL}\n\n{assign}")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "note and assign"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        proposals = messages[-1]["proposals"]
        assert len(proposals) == 2
        assert {entry["action"] for entry in proposals} == {
            "create_note",
            "assign_material",
        }
        assert "```" not in messages[-1]["markdown"]

        first = test_client.post(
            f"/api/v1/chat/proposals/{proposals[0]['id']}/approve"
        )
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "executed"
        second = test_client.post(
            f"/api/v1/chat/proposals/{proposals[1]['id']}/approve"
        )
        assert second.status_code == 200, second.text
        assert second.json()["status"] == "executed"
        replay = test_client.post(
            f"/api/v1/chat/proposals/{proposals[0]['id']}/approve"
        )
        assert replay.status_code == 409


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


def test_edit_note_captures_snapshot_and_executes(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        note_id = make_note(
            test_client, course_id, "# Derivation note\n\nThe derivative is $2x$."
        )
        gateway.responses.append(f"READ N{note_id}")
        gateway.responses.append(
            "Fixing it.\n\n" + EDIT_NOTE_PROPOSAL.replace("{nid}", str(note_id))
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "fix the sign error"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "edit_note"
        assert proposal["payload"]["original_md"]
        assert "derivative" in proposal["payload"]["original_md"]

        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "executed"
        assert body["result"]["note_id"] == note_id

        stored = app.state.session_factory()
        versions = stored.scalars(
            select(NoteVersion).where(NoteVersion.note_id == note_id)
        ).all()
        stored.close()
        assert len(versions) == 1
        assert versions[0].cause == "ai-edit"

        note = test_client.get(f"/api/v1/notes/{note_id}").json()
        assert "Fixed" in str(note["body"])

        replay = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert replay.status_code == 409


def test_edit_note_marks_stale_when_note_changed(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        note_id = make_note(test_client, course_id, "# Derivation note\n\nOriginal.")
        gateway.responses.append(f"READ N{note_id}")
        gateway.responses.append(
            "Fixing it.\n\n" + EDIT_NOTE_PROPOSAL.replace("{nid}", str(note_id))
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "fix"},
        )
        proposal = get_proposal(test_client, session["id"])
        patched = test_client.patch(
            f"/api/v1/notes/{note_id}",
            json={"body_md": "# Derivation note\n\nUser edited this first."},
        )
        assert patched.status_code == 200, patched.text
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200
        body = approved.json()
        assert body["status"] == "stale"
        assert "changed" in body["result"]["error"]
        note = test_client.get(f"/api/v1/notes/{note_id}").json()
        assert "User edited" in str(note["body"])


def test_edit_note_unknown_target_marks_stale(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        gateway.responses.append(
            "Fixing it.\n\n" + EDIT_NOTE_PROPOSAL.replace("{nid}", "999999")
        )
        gateway.responses.append(
            "Fixing it.\n\n" + EDIT_NOTE_PROPOSAL.replace("{nid}", "999999")
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "fix"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert assistant["proposals"] == []
        assert any("ungrounded" in warning for warning in assistant["warnings"])
        assert assistant["trace"]["proposals_dropped"] == ["ungrounded"]


def test_append_note_executes_and_versions(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        note_id = make_note(test_client, course_id, "# Derivation note\n\nBase body.")
        gateway.responses.append(f"READ N{note_id}")
        gateway.responses.append(
            "Adding it.\n\n" + APPEND_NOTE_PROPOSAL.replace("{nid}", str(note_id))
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "append an example"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "append_note"
        assert proposal["payload"]["original_md"]

        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "executed"

        note = test_client.get(f"/api/v1/notes/{note_id}").json()
        rendered = str(note["body"])
        assert "Base body." in rendered
        assert "Worked example" in rendered
        assert "Extra worked example." in rendered

        stored = app.state.session_factory()
        versions = stored.scalars(
            select(NoteVersion).where(NoteVersion.note_id == note_id)
        ).all()
        stored.close()
        assert len(versions) == 1


EDIT_MATERIAL_PROPOSAL = (
    "```proposal\n"
    + json.dumps(
        {
            "action": "edit_material",
            "material_id": "{mid}",
            "new_markdown": "# Chain rule\n\nEdited body with the correct sign.",
            "reason": "sign error",
        }
    )
    + "\n```"
)

APPEND_MATERIAL_PROPOSAL = (
    "```proposal\n"
    + json.dumps(
        {
            "action": "append_material",
            "material_id": "{mid}",
            "markdown": "Appended section body.",
            "heading": "Appended section",
        }
    )
    + "\n```"
)


def test_edit_material_captures_snapshot_and_executes(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "m.txt", "Original body.", course_id)
        gateway.responses.append(f"READ M{material_id}")
        gateway.responses.append(
            "Fixing it.\n\n" + EDIT_MATERIAL_PROPOSAL.replace("{mid}", str(material_id))
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "fix the material"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "edit_material"
        assert proposal["payload"]["original_md"]

        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "executed"
        assert body["result"]["material_id"] == material_id
        assert body["result"]["extraction_id"] > 0

        versions = test_client.get(
            f"/api/v1/materials/{material_id}/extractions"
        ).json()
        assert len(versions) >= 2
        latest = test_client.get(
            f"/api/v1/materials/{material_id}/extractions/{len(versions)}"
        ).json()
        assert "Edited body" in latest["markdown"]

        replay = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert replay.status_code == 409


def test_edit_material_marks_stale_when_edited_elsewhere(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "m.txt", "Original body.", course_id)
        gateway.responses.append(f"READ M{material_id}")
        gateway.responses.append(
            "Fixing it.\n\n" + EDIT_MATERIAL_PROPOSAL.replace("{mid}", str(material_id))
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "fix"},
        )
        proposal = get_proposal(test_client, session["id"])
        patched = test_client.patch(
            f"/api/v1/materials/{material_id}/extraction",
            json={"markdown": "# Chain rule\n\nUser fixed this first."},
        )
        assert patched.status_code == 200, patched.text
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200
        body = approved.json()
        assert body["status"] == "stale"
        assert "changed" in body["result"]["error"]


def test_append_material_executes(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "m.txt", "Original body.", course_id)
        gateway.responses.append(f"READ M{material_id}")
        gateway.responses.append(
            "Adding it.\n\n"
            + APPEND_MATERIAL_PROPOSAL.replace("{mid}", str(material_id))
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "append a section"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "append_material"
        assert proposal["payload"]["original_md"]

        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "executed"

        versions = test_client.get(
            f"/api/v1/materials/{material_id}/extractions"
        ).json()
        latest = test_client.get(
            f"/api/v1/materials/{material_id}/extractions/{len(versions)}"
        ).json()
        assert "Original body." in latest["markdown"]
        assert "## Appended section" in latest["markdown"]
        assert "Appended section body." in latest["markdown"]


def test_proposals_carry_target_info(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "m.txt", "Original body.", course_id)
        node_id = make_node(test_client, course_id, "Chapter 3")
        gateway.responses.append(f"READ M{material_id}")
        gateway.responses.append(
            "Extending it.\n\n"
            + APPEND_MATERIAL_PROPOSAL.replace("{mid}", str(material_id))
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "append a section"},
        )
        proposal = get_proposal(test_client, session["id"])
        payload = proposal["payload"]
        assert payload["target_kind"] == "material"
        assert payload["target_name"]

        create_text = (
            "```proposal\n"
            + json.dumps(
                {
                    "action": "create_material",
                    "title": "Integration cheat sheet",
                    "body_md": "# Integration\n\nReference formulas.",
                    "node_id": node_id,
                }
            )
            + "\n```"
        )
        gateway.responses.append(f"Saving it.\n\n{create_text}")
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "make a material"},
        )
        created = get_proposal(test_client, session["id"])
        assert created["payload"]["target_kind"] == "material"
        assert created["payload"]["target_name"] == "Integration cheat sheet"
        path = created["payload"]["target_node_path"]
        assert path[-1] == "Chapter 3"
        assert len(path) >= 2
        assert created["payload"]["target_node_id"] == node_id


def test_generate_payload_question_type_validation() -> None:
    from app.ai.proposals import GenerateQuizPayload

    ok = GenerateQuizPayload.model_validate(
        {"question_types": ["single", "numberline"], "shuffle": True}
    )
    assert ok.shuffle is True
    try:
        GenerateQuizPayload.model_validate({"question_types": ["haiku"]})
    except ValidationError:
        pass
    else:
        raise AssertionError("unknown question type accepted")


def test_generate_proposal_context_must_be_offered() -> None:
    from app.ai.proposals import validate_proposal_context

    text = (
        "```proposal\n"
        + json.dumps(
            {
                "action": "generate_quiz",
                "topic": "chain rule",
                "material_ids": [5],
                "note_ids": [2],
            }
        )
        + "\n```"
    )
    assert validate_proposal_context(text, ["M5", "N2"]) == []
    problems = validate_proposal_context(text, ["M5"])
    assert len(problems) == 1
    assert "note 2" in problems[0]
    assert "not offered" in problems[0]
    assert validate_proposal_context("no fences", ["M5"]) == []


def test_generate_context_contract_rejects_unoffered_ids(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "m.txt", "chain rule content", course_id)
        bad = (
            "```proposal\n"
            + json.dumps(
                {
                    "action": "generate_quiz",
                    "topic": "chain rule",
                    "material_ids": [99999],
                }
            )
            + "\n```"
        )
        good = (
            "```proposal\n"
            + json.dumps(
                {
                    "action": "generate_quiz",
                    "topic": "chain rule",
                    "count": 5,
                    "material_ids": [material_id],
                    "instructions": "Focus on the sign rule",
                    "question_types": ["single"],
                    "shuffle": True,
                }
            )
            + "\n```"
        )
        gateway.responses.append(bad)
        gateway.responses.append(good)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "quiz me on the material"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "generate_quiz"
        repair_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert "not offered" in repair_prompt
        assert proposal["payload"]["material_ids"] == [material_id]
        assert proposal["payload"]["instructions"] == "Focus on the sign rule"
        assert proposal["payload"]["question_types"] == ["single"]
        assert proposal["payload"]["shuffle"] is True


FLASHCARDS_PROPOSAL = (
    "```proposal\n"
    + json.dumps(
        {"action": "generate_flashcards", "material_id": "{mid}", "count": 12}
    )
    + "\n```"
)


def test_flashcards_proposal_marks_approved_with_dialog_params(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "m.txt", "chain rule content", course_id)
        gateway.responses.append(
            "Cards.\n\n" + FLASHCARDS_PROPOSAL.replace("{mid}", str(material_id))
        )
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "make cards"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "generate_flashcards"
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "approved"
        assert body["result"]["open_dialog"]["material_id"] == material_id
        assert body["result"]["open_dialog"]["count"] == 12


def test_create_material_executes_with_ingest_and_node_link(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        node_id = make_node(test_client, course_id, "Ch4")
        proposal_text = (
            "```proposal\n"
            + json.dumps(
                {
                    "action": "create_material",
                    "title": "Chain rule summary",
                    "body_md": "# Chain rule\n\nIf $f$ and $g$ are differentiable…",
                    "node_id": node_id,
                }
            )
            + "\n```"
        )
        gateway.responses.append(f"Here you go.\n\n{proposal_text}")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "save that as a material"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "create_material"
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "executed"
        material_id = body["result"]["material_id"]
        assert body["result"]["deduped"] is False

        stored = app.state.session_factory()
        from app.domain.models import MaterialLink as MaterialLinkModel

        link = stored.scalars(
            select(MaterialLinkModel).where(
                MaterialLinkModel.node_id == node_id,
                MaterialLinkModel.material_id == material_id,
            )
        ).first()
        stored.close()
        assert link is not None


def test_create_concept_executes_and_links_node(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, app = client
    with test_client:
        course_id = make_course(test_client)
        node_id = make_node(test_client, course_id, "Ch5")
        proposal_text = (
            "```proposal\n"
            + json.dumps(
                {
                    "action": "create_concept",
                    "name": "Substitution Rule",
                    "description": "Integrating via substitution",
                    "node_id": node_id,
                }
            )
            + "\n```"
        )
        gateway.responses.append(f"Adding it.\n\n{proposal_text}")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "track this concept"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert proposal["action"] == "create_concept"
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "executed"
        assert body["result"]["created"] is True
        assert body["result"]["node_id"] == node_id

        stored = app.state.session_factory()
        from app.domain.models import Concept as ConceptModel

        concept = stored.scalars(
            select(ConceptModel).where(ConceptModel.course_id == course_id)
        ).all()
        coverage = stored.scalars(
            select(NodeConcept).where(NodeConcept.node_id == node_id)
        ).all()
        stored.close()
        assert any(c.name == "Substitution Rule" for c in concept)
        assert len(coverage) == 1

        replay = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert replay.status_code == 409


def test_find_tool_line_extraction() -> None:
    from app.ai.tools import extract_tool_calls

    assert extract_tool_calls("FIND taylor series") == [("FIND", "taylor series")]
    assert extract_tool_calls("CALC 1+1") == [("CALC", "1+1")]


def test_find_tool_searches_registers_and_reads(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(
            test_client, "taylor.txt", "taylor series expansion basics", course_id
        )
        other_course = make_course(test_client, title="Other course")
        add_material(test_client, "taylor2.txt", "taylor series elsewhere", other_course)

        gateway.responses.append("FIND taylor series")
        gateway.responses.append(f"READ M{material_id}")
        gateway.responses.append("The taylor series chapter says so [1].")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "find my material on taylor series"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        assistant = messages[-1]
        assert assistant["role"] == "assistant"
        find_calls = [
            call for call in assistant["tool_calls"] if call["name"] == "FIND"
        ]
        assert find_calls
        find_result = str(find_calls[0].get("result", ""))
        assert f"M{material_id}" in find_result
        assert "taylor2" not in find_result
        read_calls = [
            call for call in assistant["tool_calls"] if call["name"] == "READ"
        ]
        assert read_calls
        reads = assistant["reads"]
        assert any(entry["id"] == material_id for entry in reads)


def test_move_tag_exam_proposals_execute(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        note_id = make_note(test_client, course_id, "# Note\n\nBody.")
        node_id = make_node(test_client, course_id, "Ch9")
        move = (
            "```proposal\n"
            + json.dumps(
                {"action": "move_to_node", "kind": "note", "id": note_id, "node_id": node_id}
            )
            + "\n```"
        )
        tags = (
            "```proposal\n"
            + json.dumps(
                {
                    "action": "tag_note",
                    "note_id": note_id,
                    "add": ["Derivatives", " To-Review "],
                }
            )
            + "\n```"
        )
        exam = (
            "```proposal\n"
            + json.dumps({"action": "set_exam_date", "exam_date": "2026-10-01"})
            + "\n```"
        )
        gateway.responses.append(f"Doing three things.\n\n{move}\n\n{tags}\n\n{exam}")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "organize me"},
        )
        messages = wait_for_assistant(test_client, session["id"])
        proposals = messages[-1]["proposals"]
        assert len(proposals) == 3
        for proposal in proposals:
            approved = test_client.post(
                f"/api/v1/chat/proposals/{proposal['id']}/approve"
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == "executed"

        note = test_client.get(f"/api/v1/notes/{note_id}").json()
        assert note["node_id"] == node_id
        assert note["tags"] == ["derivatives", "to-review"]
        course = test_client.get(f"/api/v1/courses/{course_id}").json()
        assert course["exam_date"] == "2026-10-01"


def test_generate_plan_and_add_plan_items_proposals(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        make_node(test_client, course_id, "Ch1")
        exam = (
            "```proposal\n"
            + json.dumps({"action": "set_exam_date", "exam_date": "2026-10-01"})
            + "\n```"
        )
        gen = "```proposal\n" + json.dumps({"action": "generate_plan"}) + "\n```"
        add = (
            "```proposal\n"
            + json.dumps(
                {
                    "action": "add_plan_items",
                    "items": [
                        {"title": "Practice: chain rule", "days_ahead": 2, "kind": "practice"},
                        {"title": "Review derivatives", "days_ahead": 4, "kind": "review"},
                        {"title": "Mock exam", "days_ahead": 6, "kind": "milestone"},
                    ],
                }
            )
            + "\n```"
        )
        gateway.responses.append(f"Planning.\n\n{exam}\n\n{gen}\n\n{add}")
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "plan my study"},
        )
        proposals = wait_for_assistant(test_client, session["id"])[-1]["proposals"]
        assert {entry["action"] for entry in proposals} == {
            "set_exam_date",
            "generate_plan",
            "add_plan_items",
        }
        for proposal in proposals:
            approved = test_client.post(
                f"/api/v1/chat/proposals/{proposal['id']}/approve"
            )
            assert approved.status_code == 200, approved.text
            body = approved.json()
            assert body["status"] == "executed", body
            if proposal["action"] == "add_plan_items":
                assert body["result"]["created"] == 3


def test_proposal_node_id_must_exist_in_course() -> None:
    from app.ai.proposals import validate_proposal_context

    text = (
        "```proposal\n"
        + json.dumps(
            {
                "action": "create_material",
                "title": "New note on limits",
                "body_md": "Some content.",
                "node_id": 77,
            }
        )
        + "\n```"
    )
    assert validate_proposal_context(text, ["T7"], course_node_ids={1, 7, 77}) == []
    assert validate_proposal_context(text, ["T7"], course_node_ids=None) == []
    problems = validate_proposal_context(text, ["T7"], course_node_ids={1, 7})
    assert len(problems) == 1
    assert "node 77" in problems[0]
    assert "[T#]" in problems[0]
    null_node = text.replace('"node_id": 77', '"node_id": null')
    assert validate_proposal_context(null_node, ["T7"], course_node_ids={1}) == []


def test_manifest_checks_cover_singular_ids() -> None:
    from app.ai.proposals import validate_proposal_context

    offered = ["N3", "M7"]
    ungrounded_edit = (
        '```proposal\n{"action": "edit_note", "note_id": 999, '
        '"new_body_md": "x"}\n```'
    )
    assert any(
        "note 999" in problem
        for problem in validate_proposal_context(ungrounded_edit, offered)
    )
    flashcards_none = (
        '```proposal\n{"action": "generate_flashcards", "count": 5}\n```'
    )
    assert validate_proposal_context(flashcards_none, offered) == []
    flashcards_bad = (
        '```proposal\n{"action": "generate_flashcards", "material_id": 999}\n```'
    )
    assert any(
        "material 999" in problem
        for problem in validate_proposal_context(flashcards_bad, offered)
    )
    move_bad = (
        '```proposal\n{"action": "move_to_node", "kind": "note", '
        '"id": 999, "node_id": 1}\n```'
    )
    assert any(
        "note 999" in problem
        for problem in validate_proposal_context(move_bad, offered, {1})
    )
    cover_concept = (
        '```proposal\n{"action": "cover_concept", "concept_id": 55, '
        '"node_id": 1}\n```'
    )
    assert validate_proposal_context(cover_concept, offered, {1}) == []


def test_grounding_gate_and_ungrounded_filter() -> None:
    from app.ai.proposals import (
        filter_ungrounded,
        validate_proposal_grounding,
    )

    edit = '```proposal\n{"action": "edit_note", "note_id": 3, "new_body_md": "x"}\n```'
    problems = validate_proposal_grounding(edit, [])
    assert len(problems) == 1
    assert "unread_target" in problems[0]
    assert "READ [N3]" in problems[0]
    assert validate_proposal_grounding(edit, ["N3"]) == []
    cross_kind = validate_proposal_grounding(edit, ["M7"])
    assert len(cross_kind) == 1
    assert "unread_target" in cross_kind[0]
    create = (
        '```proposal\n{"action": "create_note", "title": "t", '
        '"body_md": "b", "node_id": null}\n```'
    )
    assert validate_proposal_grounding(create, []) == []

    proposals: list[tuple[str, dict[str, Any]]] = [
        ("edit_note", {"note_id": 3, "new_body_md": "x"}),
        ("create_note", {"title": "t", "body_md": "b"}),
    ]
    kept, drops = filter_ungrounded(proposals, ["N3"])
    assert drops == []
    assert len(kept) == 2
    kept, drops = filter_ungrounded(proposals, [])
    assert drops == ["ungrounded"]
    assert [action for action, _payload in kept] == ["create_note"]


def test_unread_edit_repairs_after_read(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        note_id = make_note(test_client, course_id, "# Derivation note\n\nOriginal.")
        proposal_text = EDIT_NOTE_PROPOSAL.replace("{nid}", str(note_id))
        gateway.responses.append("Fixing it.\n\n" + proposal_text)
        gateway.responses.append(f"READ N{note_id}")
        gateway.responses.append("Fixing it.\n\n" + proposal_text)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "fix the sign error"},
        )
        proposal = get_proposal(test_client, session["id"])
        assert len(gateway.calls) == 3
        repair_prompt = "\n".join(
            str(message.content) for message in gateway.calls[1]
        )
        assert "unread_target" in repair_prompt
        assert f"READ [N{note_id}]" in repair_prompt
        assert proposal["action"] == "edit_note"
        assert proposal["payload"]["original_md"]
