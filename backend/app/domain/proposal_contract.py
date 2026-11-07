"""Contract validators for the proposal documents that stay JSON (ADR-200).

`chat_proposals.payload` keeps the per-action instruction document the card
executes: the action set is closed in Python, each action has a pydantic
payload model in `app.ai.proposals`, and this module is the single write
boundary that applies it.  `chat_proposals.result` is a polymorphic outcome
map with a closed key/type vocabulary — a mapping contract, not a record, so
it stays a versioned document instead of becoming twenty nullable columns.
"""

from typing import Any

from pydantic import ValidationError

from ..core.vocab import ProposalAnchorOp

PAYLOAD_SCHEMA_VERSION = 1
RESULT_SCHEMA_VERSION = 1

RESULT_TYPE: dict[str, type | tuple[type, ...]] = {
    "note_id": str,
    "material_id": str,
    "extraction_id": str,
    "concept_id": str,
    "node_id": str,
    "course_id": str,
    "exam_date": str,
    "job_id": str,
    "kind": str,
    "id": str,
    "error": str,
    "conflict": str,
    "note": str,
    "draft_count": int,
    "created": int,
    "deduped": bool,
    "replaced_chunk_ids": (list,),
    "tags": (list,),
    "open_dialog": (dict,),
}


class ProposalPayloadError(ValueError):
    """A proposal document does not satisfy its action contract."""


def validate_proposal_payload(action: str, payload: Any) -> dict[str, Any]:
    from ..ai.proposals import PROPOSAL_ACTIONS

    if not isinstance(payload, dict):
        raise ProposalPayloadError("proposal payload must be a JSON object")
    spec = PROPOSAL_ACTIONS.get(action)
    if spec is None:
        raise ProposalPayloadError(f"unknown proposal action '{action}'")
    try:
        spec.payload_model.model_validate(payload)
    except ValidationError as error:
        raise ProposalPayloadError(f"proposal payload invalid: {error}") from error
    return payload


def validate_proposal_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ProposalPayloadError("proposal result must be a JSON object")
    for key, value in result.items():
        expected = RESULT_TYPE.get(key)
        if expected is None:
            raise ProposalPayloadError(f"proposal result has an unknown key '{key}'")
        if value is not None and not isinstance(value, expected):
            raise ProposalPayloadError(f"proposal result key '{key}' has the wrong type")
    return result


def normalize_anchors(raw: Any) -> list[dict[str, Any]]:
    """The ordered anchored-edit contract stored in `chat_proposal_anchors`."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ProposalPayloadError("text_edits must be a list")
    anchors: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ProposalPayloadError(f"text_edits entry #{index + 1} is not an object")
        op = entry.get("op")
        if op not in {member.value for member in ProposalAnchorOp}:
            raise ProposalPayloadError(f"text_edits entry #{index + 1} has an unknown op")
        find = entry.get("find")
        text = entry.get("text", "")
        if find is not None and not isinstance(find, str):
            raise ProposalPayloadError(f"text_edits entry #{index + 1} has a non-string find")
        if not isinstance(text, str):
            raise ProposalPayloadError(f"text_edits entry #{index + 1} has a non-string text")
        anchors.append({"op": op, "find": find, "text": text})
    return anchors
