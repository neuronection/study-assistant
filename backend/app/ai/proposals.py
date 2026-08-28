import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class ProposalError(ValueError):
    pass


class CreateNotePayload(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1, max_length=50000)
    node_id: int | None = None


class AssignMaterialPayload(BaseModel):
    material_id: int
    node_id: int


class CoverConceptPayload(BaseModel):
    concept_id: int
    node_id: int


class SetNodeAiHintPayload(BaseModel):
    node_id: int
    hint: str = Field(min_length=1, max_length=2000)


class GenerateQuizPayload(BaseModel):
    topic: str | None = Field(default=None, max_length=500)
    count: int = Field(default=8, ge=1, le=30)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    node_id: int | None = None


class GenerateExercisePayload(BaseModel):
    topic: str | None = Field(default=None, max_length=500)
    steps: int = Field(default=4, ge=1, le=20)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    node_id: int | None = None


class ComposeMaterialPayload(BaseModel):
    kind: str = "study_guide"
    title: str = Field(min_length=1, max_length=300)
    instructions: str | None = Field(default=None, max_length=4000)


PROPOSAL_SCHEMAS: dict[str, type[BaseModel]] = {
    "create_note": CreateNotePayload,
    "assign_material": AssignMaterialPayload,
    "cover_concept": CoverConceptPayload,
    "set_node_ai_hint": SetNodeAiHintPayload,
    "generate_quiz": GenerateQuizPayload,
    "generate_exercise": GenerateExercisePayload,
    "compose_material": ComposeMaterialPayload,
}

GENERATE_ACTIONS = ("generate_quiz", "generate_exercise")

PROPOSAL_FENCE_RE = re.compile(r"```proposal\s*\n(.*?)\n?```", re.DOTALL)

PROPOSAL_DOC = (
    "You may end your reply with ONE action proposal for the student to approve "
    "(never execute anything yourself — the student clicks):\n"
    "```proposal\n"
    '{"action": "create_note", "title": str, "body_md": markdown, '
    '"node_id": int|null}\n'
    '{"action": "assign_material", "material_id": int, "node_id": int}\n'
    '{"action": "cover_concept", "concept_id": int, "node_id": int}\n'
    '{"action": "set_node_ai_hint", "node_id": int, "hint": str}\n'
    '{"action": "generate_quiz", "topic": str|null, "count": 1-30, '
    '"difficulty": 1-5|null, "node_id": int|null}\n'
    '{"action": "generate_exercise", "topic": str|null, "steps": 1-20, '
    '"difficulty": 1-5|null, "node_id": int|null}\n'
    '{"action": "compose_material", "kind": "study_guide"|"summary_sheet"|'
    '"practice_set"|"error_recap", "title": str, "instructions": str|null}\n'
    "```\n"
    "Use ids only from the offered manifest. Use proposals only when they "
    "clearly help; at most one proposal block per reply; omit it otherwise."
)

DISMISSAL_NOTE = (
    "NOTE: the user dismissed earlier proposals in this conversation — be more "
    "conservative; propose only when explicitly asked."
)

MAX_PROPOSALS_PER_TURN = 1


def proposal_actions() -> list[str]:
    return sorted(PROPOSAL_SCHEMAS)


def validate_proposal_text(text: str) -> list[str]:
    problems: list[str] = []
    fences = PROPOSAL_FENCE_RE.findall(text)
    if not fences:
        return problems
    if len(fences) > MAX_PROPOSALS_PER_TURN:
        problems.append(
            f"{len(fences)} proposal blocks found — at most "
            f"{MAX_PROPOSALS_PER_TURN} per reply"
        )
    for fence in fences:
        try:
            raw = json.loads(fence)
        except json.JSONDecodeError as error:
            problems.append(f"proposal block is not valid JSON ({error.msg})")
            continue
        if not isinstance(raw, dict) or "action" not in raw:
            problems.append("proposal block must be a JSON object with an 'action'")
            continue
        action = str(raw["action"])
        schema = PROPOSAL_SCHEMAS.get(action)
        if schema is None:
            problems.append(
                f"unknown proposal action '{action}' — allowed: {proposal_actions()}"
            )
            continue
        try:
            schema.model_validate(raw.get("payload") or _payload_from(raw))
        except ValidationError as error:
            detail = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
                for issue in error.errors()
            )
            problems.append(f"proposal payload invalid ({detail})")
    return problems


def _payload_from(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key != "action"}


def extract_proposal(text: str) -> tuple[str, dict[str, Any]] | None:
    fences = PROPOSAL_FENCE_RE.findall(text)
    if not fences:
        return None
    try:
        raw = json.loads(fences[0])
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict) or "action" not in raw:
        return None
    action = str(raw["action"])
    schema = PROPOSAL_SCHEMAS.get(action)
    if schema is None:
        return None
    try:
        payload = schema.model_validate(_payload_from(raw))
    except ValidationError:
        return None
    return action, payload.model_dump()


def strip_proposal_fences(text: str) -> str:
    return PROPOSAL_FENCE_RE.sub("", text).strip()
