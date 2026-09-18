import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from ..core.vocab import PLAN_ITEM_KINDS, QUESTION_TYPES
from .mentions import KIND_BY_LETTER, LETTER_BY_KIND


class ProposalError(ValueError):
    pass


class CreateNotePayload(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1, max_length=50000)
    node_id: int | None = None


class EditNotePayload(BaseModel):
    note_id: int
    new_body_md: str = Field(min_length=1, max_length=50000)
    reason: str | None = Field(default=None, max_length=500)


class AppendNotePayload(BaseModel):
    note_id: int
    markdown: str = Field(min_length=1, max_length=50000)
    heading: str | None = Field(default=None, max_length=300)


class EditMaterialPayload(BaseModel):
    material_id: int
    new_markdown: str = Field(min_length=1, max_length=200000)
    reason: str | None = Field(default=None, max_length=500)


class AppendMaterialPayload(BaseModel):
    material_id: int
    markdown: str = Field(min_length=1, max_length=50000)
    heading: str | None = Field(default=None, max_length=300)


class GenerateFlashcardsPayload(BaseModel):
    material_id: int | None = None
    note_id: int | None = None
    count: int = Field(default=10, ge=1, le=30)


class CreateMaterialPayload(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1, max_length=50000)
    node_id: int | None = None


class CreateConceptPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    node_id: int | None = None


class AttachLinkPayload(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=300)
    node_id: int | None = None

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("attach_link url must be an http(s) URL")
        return value.strip()


class MoveToNodePayload(BaseModel):
    kind: Literal["note", "quiz", "exercise", "material"]
    id: int
    node_id: int


class TagNotePayload(BaseModel):
    note_id: int
    add: list[str] = Field(min_length=1, max_length=10)


class SetExamDatePayload(BaseModel):
    exam_date: date


class AddPlanItem(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_date: date | None = None
    days_ahead: int | None = Field(default=None, ge=0, le=365)
    kind: str = "study"

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in PLAN_ITEM_KINDS:
            raise ValueError(
                f"unknown plan item kind '{value}' (allowed: {', '.join(PLAN_ITEM_KINDS)})"
            )
        return value

    @model_validator(mode="after")
    def _exactly_one_date(self) -> "AddPlanItem":
        if (self.due_date is None) == (self.days_ahead is None):
            raise ValueError("give exactly one of due_date or days_ahead")
        return self


class AddPlanItemsPayload(BaseModel):
    items: list[AddPlanItem] = Field(min_length=1, max_length=20)


class GeneratePlanPayload(BaseModel):
    pass


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
    material_ids: list[int] = Field(default_factory=list, max_length=10)
    note_ids: list[int] = Field(default_factory=list, max_length=10)
    instructions: str | None = Field(default=None, max_length=2000)
    question_types: list[str] = Field(default_factory=list, max_length=12)
    shuffle: bool = False

    @field_validator("question_types")
    @classmethod
    def _known_question_types(cls, value: list[str]) -> list[str]:
        unknown = [t for t in value if t not in QUESTION_TYPES]
        if unknown:
            raise ValueError(
                f"unknown question type(s) {unknown} (allowed: {', '.join(QUESTION_TYPES)})"
            )
        return value


class GenerateExercisePayload(BaseModel):
    topic: str | None = Field(default=None, max_length=500)
    steps: int = Field(default=4, ge=1, le=20)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    node_id: int | None = None
    material_ids: list[int] = Field(default_factory=list, max_length=10)
    note_ids: list[int] = Field(default_factory=list, max_length=10)
    instructions: str | None = Field(default=None, max_length=2000)


class ComposeMaterialPayload(BaseModel):
    kind: str = "study_guide"
    title: str = Field(min_length=1, max_length=300)
    instructions: str | None = Field(default=None, max_length=4000)


@dataclass(frozen=True)
class ProposalActionSpec:
    payload_model: type[BaseModel]
    doc_line: str
    api_executed: bool = False
    snapshot: str | None = None
    context_ids: tuple[tuple[str, str], ...] = ()


PROPOSAL_ACTIONS: dict[str, ProposalActionSpec] = {
    "create_note": ProposalActionSpec(
        payload_model=CreateNotePayload,
        doc_line=(
            '{"action": "create_note", "title": str, "body_md": markdown, '
            '"node_id": int|null}'
        ),
        api_executed=True,
    ),
    "edit_note": ProposalActionSpec(
        payload_model=EditNotePayload,
        doc_line=(
            '{"action": "edit_note", "note_id": int, "new_body_md": markdown, '
            '"reason": str|null}'
        ),
        snapshot="note_body",
        context_ids=(("note_id", "note"),),
    ),
    "append_note": ProposalActionSpec(
        payload_model=AppendNotePayload,
        doc_line=(
            '{"action": "append_note", "note_id": int, "markdown": markdown, '
            '"heading": str|null}'
        ),
        snapshot="note_body",
        context_ids=(("note_id", "note"),),
    ),
    "edit_material": ProposalActionSpec(
        payload_model=EditMaterialPayload,
        doc_line=(
            '{"action": "edit_material", "material_id": int, '
            '"new_markdown": markdown, "reason": str|null}'
        ),
        snapshot="extraction_md",
        context_ids=(("material_id", "material"),),
    ),
    "append_material": ProposalActionSpec(
        payload_model=AppendMaterialPayload,
        doc_line=(
            '{"action": "append_material", "material_id": int, '
            '"markdown": markdown, "heading": str|null}'
        ),
        snapshot="extraction_md",
        context_ids=(("material_id", "material"),),
    ),
    "assign_material": ProposalActionSpec(
        payload_model=AssignMaterialPayload,
        doc_line='{"action": "assign_material", "material_id": int, "node_id": int}',
        context_ids=(("material_id", "material"),),
    ),
    "cover_concept": ProposalActionSpec(
        payload_model=CoverConceptPayload,
        doc_line='{"action": "cover_concept", "concept_id": int, "node_id": int}',
    ),
    "set_node_ai_hint": ProposalActionSpec(
        payload_model=SetNodeAiHintPayload,
        doc_line='{"action": "set_node_ai_hint", "node_id": int, "hint": str}',
    ),
    "generate_quiz": ProposalActionSpec(
        payload_model=GenerateQuizPayload,
        doc_line=(
            '{"action": "generate_quiz", "topic": str|null, "count": 1-30, '
            '"difficulty": 1-5|null, "node_id": int|null, "material_ids": [int], '
            '"note_ids": [int], "instructions": str|null, '
            '"question_types": ["single"|"multi"|"truefalse"|"text"|"numeric"|'
            '"equation"|"numberline"|"table_fill"|"composite"|"graph_read"|"code"], '
            '"shuffle": bool}'
        ),
        api_executed=True,
    ),
    "generate_exercise": ProposalActionSpec(
        payload_model=GenerateExercisePayload,
        doc_line=(
            '{"action": "generate_exercise", "topic": str|null, "steps": 1-20, '
            '"difficulty": 1-5|null, "node_id": int|null, "material_ids": [int], '
            '"note_ids": [int], "instructions": str|null}'
        ),
        api_executed=True,
    ),
    "compose_material": ProposalActionSpec(
        payload_model=ComposeMaterialPayload,
        doc_line=(
            '{"action": "compose_material", "kind": "study_guide"|"summary_sheet"|'
            '"practice_set"|"error_recap", "title": str, "instructions": str|null}'
        ),
        api_executed=True,
    ),
    "generate_flashcards": ProposalActionSpec(
        payload_model=GenerateFlashcardsPayload,
        doc_line=(
            '{"action": "generate_flashcards", "material_id": int|null, '
            '"note_id": int|null, "count": 1-30}'
        ),
        api_executed=True,
        context_ids=(("material_id", "material"), ("note_id", "note")),
    ),
    "create_material": ProposalActionSpec(
        payload_model=CreateMaterialPayload,
        doc_line=(
            '{"action": "create_material", "title": str, "body_md": markdown, '
            '"node_id": int|null}'
        ),
    ),
    "create_concept": ProposalActionSpec(
        payload_model=CreateConceptPayload,
        doc_line=(
            '{"action": "create_concept", "name": str, "description": str|null, '
            '"node_id": int|null}'
        ),
    ),
    "attach_link": ProposalActionSpec(
        payload_model=AttachLinkPayload,
        doc_line=(
            '{"action": "attach_link", "url": "https://...", "title": str|null, '
            '"node_id": int|null}'
        ),
    ),
    "move_to_node": ProposalActionSpec(
        payload_model=MoveToNodePayload,
        doc_line=(
            '{"action": "move_to_node", "kind": "note"|"quiz"|"exercise"|'
            '"material", "id": int, "node_id": int}'
        ),
    ),
    "tag_note": ProposalActionSpec(
        payload_model=TagNotePayload,
        doc_line=(
            '{"action": "tag_note", "note_id": int, "add": [str]}'
        ),
        context_ids=(("note_id", "note"),),
    ),
    "set_exam_date": ProposalActionSpec(
        payload_model=SetExamDatePayload,
        doc_line=(
            '{"action": "set_exam_date", "exam_date": "YYYY-MM-DD"}'
        ),
    ),
    "generate_plan": ProposalActionSpec(
        payload_model=GeneratePlanPayload,
        doc_line=(
            '{"action": "generate_plan"}'
        ),
    ),
    "add_plan_items": ProposalActionSpec(
        payload_model=AddPlanItemsPayload,
        doc_line=(
            '{"action": "add_plan_items", "items": [{"title": str, '
            '"due_date": "YYYY-MM-DD"|null, "days_ahead": int|null, '
            '"kind": "study"|"practice"|"review"|"milestone"}]}'
        ),
    ),
}

GENERATE_ACTIONS = ("generate_quiz", "generate_exercise", "generate_flashcards")

PROPOSAL_FENCE_RE = re.compile(r"```proposal\s*\n(.*?)\n?```", re.DOTALL)

MAX_PROPOSALS_PER_TURN = 3

PROPOSAL_DOC = (
    "You may end your reply with up to THREE action proposals for the student "
    "to approve (never execute anything yourself — the student clicks):\n"
    "```proposal\n"
    + "\n".join(spec.doc_line for spec in PROPOSAL_ACTIONS.values())
    + "\n```\n"
    "Use ids only from the offered manifest. When a payload has node_id, it "
    "must be the integer id of a [T#] node from the course structure "
    "(or null to leave placement unchanged). edit_note, append_note, "
    "edit_material and append_material REQUIRE the target's full content to "
    "be read in this turn first: call READ [N#]/[M#], then propose the edit. "
    "Use proposals only when they "
    "clearly help; at most three proposal blocks per reply; omit them otherwise."
)

DISMISSAL_NOTE = (
    "NOTE: the user dismissed earlier proposals in this conversation — be more "
    "conservative; propose only when explicitly asked."
)


def proposal_actions() -> list[str]:
    return sorted(PROPOSAL_ACTIONS)


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
        spec = PROPOSAL_ACTIONS.get(action)
        if spec is None:
            problems.append(
                f"unknown proposal action '{action}' — allowed: {proposal_actions()}"
            )
            continue
        try:
            spec.payload_model.model_validate(raw.get("payload") or _payload_from(raw))
        except ValidationError as error:
            detail = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
                for issue in error.errors()
            )
            problems.append(f"proposal payload invalid ({detail})")
    return problems


def _payload_from(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key != "action"}


CONTEXT_ID_FIELDS: dict[str, str] = {
    "material_ids": "material",
    "note_ids": "note",
}

_OFFERED_REF_RE = re.compile(r"([MNCTQE])(\d+)")


def _singular_context_problems(
    action: str,
    payload: BaseModel,
    spec: ProposalActionSpec,
    offered: dict[str, set[int]],
) -> list[str]:
    problems: list[str] = []
    for field_name, kind in spec.context_ids:
        value = getattr(payload, field_name, None)
        if value is None or value in offered.get(kind, set()):
            continue
        problems.append(
            f"proposal {action} references {kind} {value} which was "
            "not offered in this conversation — use only offered ids"
        )
    return problems


def validate_proposal_context(
    text: str,
    offered_refs: list[str],
    course_node_ids: set[int] | None = None,
) -> list[str]:
    fences = PROPOSAL_FENCE_RE.findall(text)
    if not fences or not offered_refs:
        return []
    offered: dict[str, set[int]] = {}
    for ref in offered_refs:
        match = _OFFERED_REF_RE.fullmatch(ref)
        if match:
            offered.setdefault(KIND_BY_LETTER[match.group(1)], set()).add(
                int(match.group(2))
            )
    problems: list[str] = []
    for fence in fences:
        try:
            raw = json.loads(fence)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action"))
        spec = PROPOSAL_ACTIONS.get(action)
        if spec is None:
            continue
        try:
            payload = spec.payload_model.model_validate(
                raw.get("payload") or _payload_from(raw)
            )
        except ValidationError:
            continue
        for field_name, kind in CONTEXT_ID_FIELDS.items():
            if field_name not in type(payload).model_fields:
                continue
            for item_id in getattr(payload, field_name):
                if item_id not in offered.get(kind, set()):
                    problems.append(
                        f"proposal {action} references {kind} {item_id} which was "
                        "not offered in this conversation — use only offered ids "
                        "in material_ids/note_ids"
                    )
        problems.extend(_singular_context_problems(action, payload, spec, offered))
        move_kind = getattr(payload, "kind", None)
        move_id = getattr(payload, "id", None)
        if (
            action == "move_to_node"
            and move_kind is not None
            and move_id is not None
            and move_kind in offered
            and move_id not in offered[move_kind]
        ):
            problems.append(
                f"proposal {action} references {move_kind} {move_id} "
                "which was not offered in this conversation — use only "
                "offered ids"
            )
        node_id = getattr(payload, "node_id", None)
        if (
            node_id is not None
            and course_node_ids is not None
            and node_id not in course_node_ids
        ):
            problems.append(
                f"proposal {action} targets node {node_id} which does not exist "
                "in this course — use the integer id of a [T#] node from the "
                "course structure, or null"
            )
    return problems


def _grounding_target(
    payload: BaseModel, spec: ProposalActionSpec
) -> tuple[str, int, str] | None:
    """The (field, id, kind) an edit-in-place op must have had read."""
    for field_name, kind in spec.context_ids:
        value = getattr(payload, field_name, None)
        if value is not None:
            return (field_name, int(value), kind)
    return None


def validate_proposal_grounding(
    text: str,
    read_refs: list[str],
) -> list[str]:
    """Read-before-edit gate (plan 78-B): edit-in-place proposals (the
    snapshot-bearing actions) are violations unless the target's full
    content was READ in this turn."""
    fences = PROPOSAL_FENCE_RE.findall(text)
    if not fences:
        return []
    read_ids: dict[str, set[int]] = {}
    for ref in read_refs or []:
        match = _OFFERED_REF_RE.fullmatch(ref)
        if match:
            read_ids.setdefault(KIND_BY_LETTER[match.group(1)], set()).add(
                int(match.group(2))
            )
    problems: list[str] = []
    for fence in fences:
        try:
            raw = json.loads(fence)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action"))
        spec = PROPOSAL_ACTIONS.get(action)
        if spec is None or spec.snapshot is None:
            continue
        try:
            payload = spec.payload_model.model_validate(
                raw.get("payload") or _payload_from(raw)
            )
        except ValidationError:
            continue
        target = _grounding_target(payload, spec)
        if target is None:
            continue
        _field, target_id, kind = target
        if target_id in read_ids.get(kind, set()):
            continue
        letter = LETTER_BY_KIND.get(kind, kind[:1].upper())
        problems.append(
            f"unread_target: proposal {action} targets {kind} {target_id} "
            f"whose full content was not read this turn — call READ "
            f"[{letter}{target_id}] first, then propose the edit"
        )
    return problems


def filter_ungrounded(
    proposals: list[tuple[str, dict[str, Any]]],
    read_refs: list[str],
) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
    """Extraction-time twin of `validate_proposal_grounding`: after the
    repair budget is spent, ungrounded edit-in-place proposals are dropped
    with the `ungrounded` code instead of becoming cards doomed to stale."""
    read_ids: dict[str, set[int]] = {}
    for ref in read_refs or []:
        match = _OFFERED_REF_RE.fullmatch(ref)
        if match:
            read_ids.setdefault(KIND_BY_LETTER[match.group(1)], set()).add(
                int(match.group(2))
            )
    kept: list[tuple[str, dict[str, Any]]] = []
    drops: list[str] = []
    for action, payload in proposals:
        spec = PROPOSAL_ACTIONS.get(action)
        target: tuple[str, int, str] | None = None
        if spec is not None and spec.snapshot is not None:
            try:
                target = _grounding_target(
                    spec.payload_model.model_validate(payload), spec
                )
            except ValidationError:
                target = None
        if target is not None and target[1] not in read_ids.get(target[2], set()):
            drops.append("ungrounded")
            continue
        kept.append((action, payload))
    return kept, drops


PROPOSAL_DROP_REASONS: tuple[str, ...] = (
    "invalid_json",
    "not_object",
    "unknown_action",
    "schema",
    "ungrounded",
    "cap",
)


def extract_proposals_with_drops(
    text: str,
) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
    """Validated proposals plus one stable reason code per dropped fence.

    ``cap`` appears once when fences beyond MAX_PROPOSALS_PER_TURN were
    ignored; every other code is per dropped fence, in fence order.
    """
    proposals: list[tuple[str, dict[str, Any]]] = []
    drops: list[str] = []
    fences = PROPOSAL_FENCE_RE.findall(text)
    if len(fences) > MAX_PROPOSALS_PER_TURN:
        drops.append("cap")
    for fence in fences[:MAX_PROPOSALS_PER_TURN]:
        try:
            raw = json.loads(fence)
        except json.JSONDecodeError:
            drops.append("invalid_json")
            continue
        if not isinstance(raw, dict) or "action" not in raw:
            drops.append("not_object")
            continue
        action = str(raw["action"])
        spec = PROPOSAL_ACTIONS.get(action)
        if spec is None:
            drops.append("unknown_action")
            continue
        try:
            payload = spec.payload_model.model_validate(_payload_from(raw))
        except ValidationError:
            drops.append("schema")
            continue
        proposals.append((action, json.loads(payload.model_dump_json())))
    return proposals, drops


def extract_proposals(text: str) -> list[tuple[str, dict[str, Any]]]:
    proposals, _ = extract_proposals_with_drops(text)
    return proposals


def strip_proposal_fences(text: str) -> str:
    return PROPOSAL_FENCE_RE.sub("", text).strip()
