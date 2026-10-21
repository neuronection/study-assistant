"""Payload contract law (plan 81 D, ADR-200).

Known-shape state is typed (columns/tables), canonical content documents keep
their JSON shape behind a `<column>_schema_version` sibling, and every write
boundary rejects a malformed document with a typed error.
"""

from typing import Any, cast

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.vocab import ProposalAnchorOp
from app.domain.documents import (
    DOCUMENT_SCHEMA_VERSION,
    DocumentShapeError,
    validate_blocks,
    validate_strokes,
)
from app.domain.models import (
    ChatMessage,
    ChatProposal,
    ChatProposalAnchor,
    ChatQuizPending,
    ChatSession,
    Course,
    Material,
    MaterialDrawing,
    Note,
    NoteDrawing,
)
from app.domain.payloads import ProposalResult
from app.domain.preferences import PreferencesError, validate_preferences
from app.domain.proposal_contract import (
    ProposalPayloadError,
    validate_proposal_payload,
    validate_proposal_result,
)


def _seed(session: Session, profile_id: str) -> dict[str, Any]:
    course = Course(profile_id=profile_id, title="C", origin="manual")
    session.add(course)
    session.flush()
    material = Material(
        profile_id=profile_id,
        course_id=course.id,
        kind="md",
        title="M",
        filename="m.md",
        status="ready",
    )
    chat_session = ChatSession(profile_id=profile_id, course_id=course.id, title="S")
    session.add_all([material, chat_session])
    session.flush()
    return {
        "profile_id": profile_id,
        "course_id": course.id,
        "material_id": material.id,
        "chat_session_id": chat_session.id,
    }


def _note(session: Session, seeded: dict[str, Any]) -> Note:
    note = Note(
        profile_id=seeded["profile_id"],
        course_id=seeded["course_id"],
        title="N",
        body=[{"type": "text", "md": "hello"}],
    )
    session.add(note)
    session.flush()
    return note


def test_note_body_rejects_a_malformed_document(db_session: Session, profile_id: str) -> None:
    note = _note(db_session, _seed(db_session, profile_id))
    with pytest.raises(DocumentShapeError):
        note.body = [{"type": "md", "md": "x"}]
    with pytest.raises(DocumentShapeError):
        note.body = [{"type": "text"}]


def test_note_body_stamps_the_schema_version(db_session: Session, profile_id: str) -> None:
    note = _note(db_session, _seed(db_session, profile_id))
    assert note.body_schema_version == DOCUMENT_SCHEMA_VERSION
    note.body = [{"type": "text", "md": "changed"}]
    assert note.body_schema_version == DOCUMENT_SCHEMA_VERSION


def test_drawing_strokes_require_points() -> None:
    assert validate_strokes([{"points": [[0, 0], [1, 1]], "width": 2}])
    bad_values: list[Any] = [
        [{"color": "red"}],
        [{"points": []}],
        [{"points": [[0]]}],
        "nope",
    ]
    for bad in bad_values:
        with pytest.raises(DocumentShapeError):
            validate_strokes(bad)


def test_drawing_view_lives_in_columns(db_session: Session, profile_id: str) -> None:
    seeded = _seed(db_session, profile_id)
    drawing = MaterialDrawing(
        material_id=seeded["material_id"],
        strokes=[{"points": [[0, 0]], "width": 1}],
        view_x=1.0,
        view_y=2.0,
        view_width=300.0,
        view_height=200.0,
    )
    db_session.add(drawing)
    db_session.flush()
    assert drawing.strokes_schema_version == DOCUMENT_SCHEMA_VERSION
    assert (drawing.view_x, drawing.view_y) == (1.0, 2.0)
    assert not hasattr(drawing, "view")


def test_note_drawing_ocr_blocks_are_versioned(db_session: Session, profile_id: str) -> None:
    note = _note(db_session, _seed(db_session, profile_id))
    drawing = NoteDrawing(
        note_id=note.id,
        strokes=[{"points": [[0, 0]]}],
        ocr_blocks=[{"type": "text", "md": "ocr"}],
    )
    db_session.add(drawing)
    db_session.flush()
    assert drawing.ocr_blocks_schema_version == DOCUMENT_SCHEMA_VERSION
    with pytest.raises(DocumentShapeError):
        drawing.ocr_blocks = [{"md": "no type"}]


def test_chat_blocks_reject_a_malformed_document() -> None:
    message = ChatMessage(session_id="s", role="assistant", blocks=[{"type": "text", "md": "ok"}])
    assert message.blocks_schema_version == DOCUMENT_SCHEMA_VERSION
    with pytest.raises(DocumentShapeError):
        message.blocks = [{"type": "unknown"}]


def test_proposal_payload_is_validated_per_action() -> None:
    valid = {"title": "T", "body_md": "B"}
    assert validate_proposal_payload("create_note", valid) == valid
    with pytest.raises(ProposalPayloadError):
        validate_proposal_payload("create_note", {})
    with pytest.raises(ProposalPayloadError):
        validate_proposal_payload("not_an_action", {})
    with pytest.raises(ProposalPayloadError):
        validate_proposal_payload("create_note", ["not", "a", "mapping"])


def test_proposal_result_vocabulary_is_closed() -> None:
    assert validate_proposal_result({"note_id": "n1", "deduped": False})
    with pytest.raises(ProposalPayloadError):
        validate_proposal_result({"mystery": 1})


def test_chat_proposal_write_boundary_rejects_a_malformed_payload() -> None:
    with pytest.raises(ProposalPayloadError):
        ChatProposal(message_id="m", action="create_note", payload={})
    proposal = ChatProposal(
        message_id="m",
        action="create_note",
        payload={"title": "T", "body_md": "B"},
    )
    assert proposal.payload_schema_version == 1
    with pytest.raises(ProposalPayloadError):
        proposal.result = cast(ProposalResult, {"mystery": 1})


def test_anchor_ops_are_a_closed_set() -> None:
    anchor = ChatProposalAnchor(proposal_id="p", position=0, op="replace", find_text="a", text="b")
    assert anchor.op == ProposalAnchorOp.REPLACE.value
    assert anchor.text == "b"


def test_quiz_pending_row_holds_the_grading_state(db_session: Session, profile_id: str) -> None:
    seeded = _seed(db_session, profile_id)
    pending = ChatQuizPending(
        session_id=seeded["chat_session_id"],
        question="2+2?",
        choices=["3", "4"],
        expected_index=1,
        accept=["four"],
        awaiting_answer=True,
    )
    db_session.add(pending)
    db_session.flush()
    assert pending.verdict is None
    other = ChatSession(profile_id=profile_id, title="S2")
    db_session.add(other)
    db_session.flush()
    invalid = ChatQuizPending(session_id=other.id, question="x", verdict="maybe")
    db_session.add(invalid)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_preferences_validate_known_keys_and_pass_extension_sections() -> None:
    document = {
        "use_embeddings": False,
        "ocr_image_max_edge": 1024,
        "discovery": {"enabled": ["web"], "sites": [{"site": "example.org"}]},
        "mcp": {"servers": [{"name": "local"}]},
        "search_providers": [{"kind": "searxng"}],
    }
    assert validate_preferences(document) is document
    with pytest.raises(PreferencesError):
        validate_preferences({"use_embeddings": "definitely"})
    with pytest.raises(PreferencesError):
        validate_preferences({"discovery": "not a section"})


def test_validate_blocks_accepts_every_contract_block_type() -> None:
    blocks: list[dict[str, Any]] = [
        {"type": "text", "md": "x"},
        {"type": "drawing", "drawing_id": "d"},
        {"type": "image_ref", "image_id": "i"},
        {"type": "chart", "plotly": {"data": []}},
        {"type": "widget", "widget": "checklist", "id": "w1", "props": {}},
    ]
    assert validate_blocks(blocks) == blocks


def test_session_out_exposes_only_the_public_quiz_state(
    client: Any, db_session: Session, profile_id: str
) -> None:
    seeded = _seed(db_session, profile_id)
    db_session.add(
        ChatQuizPending(
            session_id=seeded["chat_session_id"],
            question="2+2?",
            choices=["3", "4"],
            expected_index=1,
            expected_latex="4",
            accept=["four"],
            awaiting_answer=True,
        )
    )
    db_session.commit()
    sessions = client.get("/api/v1/chat/sessions").json()
    row = next(item for item in sessions if item["id"] == seeded["chat_session_id"])
    assert row["quiz_pending"]["question"] == "2+2?"
    assert row["quiz_pending"]["choices"] == ["3", "4"]
    assert row["quiz_pending"]["answered"] is False
    assert "expected_index" not in row["quiz_pending"]
    assert "expected_latex" not in row["quiz_pending"]
    assert "accept" not in row["quiz_pending"]
