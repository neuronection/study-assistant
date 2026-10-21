"""Named payload types for every JSON column (plan 81 D, ADR-200).

`PAYLOAD_TYPES` maps each ``table.column`` JSON column to the type alias the
model declares. The schema wall asserts the registry covers exactly the JSON
columns the models carry and that the model annotation names the registered
type — a new JSON column cannot land untyped.

Shapes are deliberately ``total=False``: document-shaped payloads are
extensible by design (canonical content, AI-authored authoring documents,
extension-owned sections). They capture the fields the product reads or
writes; unknown fields survive because the columns stay JSON.
"""

from typing import Any, TypedDict

from .preferences import ProfilePreferences as ProfilePreferences

__all__ = ["PAYLOAD_TYPES", "PAYLOAD_TYPE_NAMES"]


class BlockDict(TypedDict, total=False):
    type: str
    md: str
    drawing_id: str
    image_id: str
    plotly: dict[str, Any]
    widget: str
    id: str
    props: dict[str, Any]


type BlockList = list[BlockDict]


class StrokeDict(TypedDict, total=False):
    points: list[list[float]]
    color: str
    width: float
    tool: str


type StrokeList = list[StrokeDict]

type StringList = list[str]
type TrashPayload = dict[str, Any]
type WidgetStateMap = dict[str, Any]
type ExternalSourceOptions = dict[str, Any]
type ExternalSourceCursor = dict[str, Any]
type DistractorSelection = dict[str, int]
type DistractorMisconceptions = dict[str, str]


class CitationDict(TypedDict, total=False):
    index: int
    chunk_id: str
    material_id: str
    title: str
    quote: str


type CitationList = list[CitationDict]


class MentionDict(TypedDict, total=False):
    ref: str
    kind: str
    id: str
    title: str
    course_id: str | None
    summary: str | None


type MentionList = list[MentionDict]
type MentionRegistryList = list[MentionDict]


class ReadDict(TypedDict, total=False):
    ref: str
    kind: str
    id: str
    title: str
    course_id: str | None
    chars: int


type ReadList = list[ReadDict]


class QuizDict(TypedDict, total=False):
    question: str
    choices: list[str]
    answered: bool
    verdict: str
    student_answer: str
    expected_display: str | None


class ToolCallDict(TypedDict, total=False):
    name: str
    argument: str
    phase: str | None
    result: str | None
    title: str | None
    status: str | None
    start_ms: int | None
    duration_ms: int | None
    quiz: QuizDict


type ToolCallList = list[ToolCallDict]


class HelpEventDict(TypedDict, total=False):
    type: str
    level: int
    rung: int
    at: str
    kind: str
    text: str
    created_at: str


type HelpEventList = list[HelpEventDict]
type FeedbackList = list[dict[str, Any]]


class ActivityConfig(TypedDict, total=False):
    count: int
    topic: str
    imported: bool


class ActivityGeneratedFrom(TypedDict, total=False):
    format: str


class AnswerResponse(TypedDict, total=False):
    value: Any
    input_mode: str
    strokes: StrokeList


class AttemptMeta(TypedDict, total=False):
    site: str
    mcp: bool
    published: str | None


class ChatSessionContext(TypedDict, total=False):
    quiz_attempt_id: str
    question_id: str
    exercise_session_id: str
    pending_answer: Any
    proposal_feedback_ids: list[str]


class ChatTrace(TypedDict, total=False):
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    repair_rounds: int
    rounds: list[int]
    thinking: str
    interruption: str
    proposals_dropped: list[str]
    turn_failed: bool


class ProposalPayload(TypedDict, total=False):
    title: str
    body_md: str
    node_id: str | None
    note_id: str
    material_id: str
    new_body_md: str | None
    new_markdown: str | None
    reason: str | None
    markdown: str
    heading: str | None
    name: str
    description: str | None
    url: str
    kind: str
    id: str
    add: list[str]
    exam_date: str
    items: list[dict[str, Any]]
    instructions: str | None
    topic: str | None
    difficulty: int | None
    material_ids: list[str]
    note_ids: list[str]
    question_types: list[str]
    shuffle: bool
    steps: int
    count: int


class ProposalResult(TypedDict, total=False):
    note_id: str
    material_id: str
    extraction_id: str
    concept_id: str
    node_id: str
    course_id: str
    exam_date: str
    job_id: str
    kind: str
    id: str
    error: str
    conflict: str
    note: str
    draft_count: int
    created: int
    deduped: bool
    replaced_chunk_ids: list[str]
    tags: list[str]
    open_dialog: ProposalPayload


class MaterialProvenance(TypedDict, total=False):
    generator: str
    source: str
    url: str
    from_material_id: str
    from_version: int
    coverage: dict[str, Any]
    needs_review: bool
    practice_items: list[dict[str, Any]]
    source_ref: str | None


class ExtractionConfidence(TypedDict, total=False):
    pages: list[dict[str, Any]]
    score: float
    mode: str


type ExternalSourceCursorDocument = dict[str, Any]


class SuggestionMeta(TypedDict, total=False):
    site: str
    mcp: bool
    published: str | None


class DetectionSpec(TypedDict, total=False):
    type: str
    factors: list[int]


class QuestionAnswer(TypedDict, total=False):
    value: Any
    index: int
    indices: list[int]
    mode: str
    domain: str
    tolerance: float
    kind: str
    back: BlockList
    latex: str
    text: str
    rows: list[dict[str, Any]] | list[list[str]]
    points: list[Any]
    intervals: list[dict[str, Any]]
    parts: list[dict[str, Any]]
    tests: list[dict[str, Any]]
    point_x: float
    expression: str
    accept: list[str]


class QuestionProvenance(TypedDict, total=False):
    generator: str
    source: str


class QuestionStats(TypedDict, total=False):
    attempts: int
    correct: int
    accuracy: float


class SympyCheck(TypedDict, total=False):
    expected: str
    variables: list[str]


class ExpectedAnswer(TypedDict, total=False):
    kind: str
    value: Any
    tolerance: float
    back: BlockList
    concept: str
    steps: list[str]
    rubric: list[dict[str, Any]]


class RubricDocument(TypedDict, total=False):
    rows: list[dict[str, Any]]
    rubric: list[dict[str, Any]]


class ExerciseContextDocument(TypedDict, total=False):
    topic: str
    difficulty: int
    node_id: str | None
    material_ids: list[str]
    note_ids: list[str]


type ExerciseContextList = list[ExerciseContextDocument]


class ExerciseCreatedFrom(TypedDict, total=False):
    source: str
    generator: str
    kind: str
    pattern: str
    from_exercise_id: str
    source_ref: str | None


class StepResponse(TypedDict, total=False):
    value: Any
    input_mode: str
    strokes: StrokeList


class StepState(TypedDict, total=False):
    hint_level: int
    hint: str
    revealed: bool


class StepFeedbackList(TypedDict, total=False):
    rows: list[dict[str, Any]]


class ProviderStatus(TypedDict, total=False):
    ok: bool
    checked_at: str
    message: str
    models: int


class SkillParams(TypedDict, total=False):
    temperature: float
    max_tokens: int
    reasoning_effort: str


class SkillContract(TypedDict, total=False):
    max_words: int | None
    no_answer_reveal: bool
    citation_if_context: bool


class TaskParams(TypedDict, total=False):
    monthly_cap_usd: float
    temperature: float
    max_tokens: int
    reasoning_effort: str
    transport: str


class JobPayload(TypedDict, total=False):
    """The union of every job-type payload (the type column selects the shape)."""

    material_id: str
    blob_sha: str | None
    mode: str
    replaced_chunk_ids: list[str]
    extraction_id: str
    chat_session_id: str
    user_message_id: str
    kind: str
    drawing_id: str
    note_id: str
    image_id: str
    course_id: str
    lessons: bool
    quizzes: bool
    flashcards: bool
    action: str
    profile_id: str | None
    node_id: str | None
    title: str | None
    instructions: str | None
    extra_md: str | None
    scope: str | None
    include_material_ids: list[str] | None
    exclude_material_ids: list[str] | None
    concept_ids: list[str] | None
    context_hint: str | None
    regenerate: bool | None
    include_unassigned: bool | None


PAYLOAD_TYPE_NAMES: dict[str, str] = {
    "activities.config": "ActivityConfig",
    "activities.generated_from": "ActivityGeneratedFrom",
    "answers.error_tags": "StringList",
    "answers.feedback": "FeedbackList",
    "answers.help_events": "HelpEventList",
    "answers.response": "AnswerResponse",
    "attempts.meta": "AttemptMeta",
    "chat_messages.blocks": "BlockList",
    "chat_messages.citations": "CitationList",
    "chat_messages.mentions": "MentionList",
    "chat_messages.reads": "ReadList",
    "chat_messages.state": "WidgetStateMap",
    "chat_messages.tool_calls": "ToolCallList",
    "chat_messages.trace": "ChatTrace",
    "chat_messages.warnings": "StringList",
    "chat_proposals.payload": "ProposalPayload",
    "chat_proposals.result": "ProposalResult",
    "chat_proposals.target_node_path": "StringList",
    "chat_quiz_pendings.accept": "StringList",
    "chat_quiz_pendings.choices": "StringList",
    "chat_sessions.context": "ChatSessionContext",
    "chat_sessions.mention_registry": "MentionRegistryList",
    "concepts.aliases": "StringList",
    "courses.goals": "StringList",
    "courses.tags": "StringList",
    "deleted_items.payload": "TrashPayload",
    "error_patterns.detection": "DetectionSpec",
    "exercise_steps.expected": "ExpectedAnswer",
    "exercise_steps.hints_pregenerated": "BlockList",
    "exercise_steps.prompt": "BlockList",
    "exercise_steps.rubric": "RubricDocument",
    "exercises.context": "ExerciseContextList",
    "exercises.created_from": "ExerciseCreatedFrom",
    "external_sources.cursor": "ExternalSourceCursorDocument",
    "external_sources.options": "ExternalSourceOptions",
    "extractions.blocks": "BlockList",
    "extractions.confidence": "ExtractionConfidence",
    "item_stats.distractor_selection": "DistractorSelection",
    "jobs.payload": "JobPayload",
    "material_drawings.ocr_blocks": "BlockList",
    "material_drawings.strokes": "StrokeList",
    "material_index_cards.key_terms": "StringList",
    "material_index_cards.topics": "StringList",
    "material_sources.include_globs": "StringList",
    "material_suggestions.meta": "SuggestionMeta",
    "materials.provenance": "MaterialProvenance",
    "materials.tags": "StringList",
    "mistakes.concept_ids": "StringList",
    "mistakes.error_tags": "StringList",
    "models.caps": "StringList",
    "note_drawings.ocr_blocks": "BlockList",
    "note_drawings.strokes": "StrokeList",
    "note_versions.body": "BlockList",
    "note_versions.tags": "StringList",
    "notes.body": "BlockList",
    "notes.tags": "StringList",
    "profiles.preferences": "ProfilePreferences",
    "providers.status": "ProviderStatus",
    "questions.answer": "QuestionAnswer",
    "questions.concept_ids": "StringList",
    "questions.distractor_misconceptions": "DistractorMisconceptions",
    "questions.explanation": "BlockList",
    "questions.input_modes": "StringList",
    "questions.options": "BlockList",
    "questions.provenance": "QuestionProvenance",
    "questions.source_refs": "StringList",
    "questions.stats": "QuestionStats",
    "questions.stem": "BlockList",
    "questions.sympy_check": "SympyCheck",
    "questions.tags": "StringList",
    "skill_versions.contract": "SkillContract",
    "skill_versions.params": "SkillParams",
    "step_attempts.feedback": "FeedbackList",
    "step_attempts.response": "StepResponse",
    "step_attempts.state": "StepState",
    "task_assignments.params": "TaskParams",
    "tree_nodes.objectives": "StringList",
}

PAYLOAD_TYPES: dict[str, object] = {
    "ActivityConfig": ActivityConfig,
    "ActivityGeneratedFrom": ActivityGeneratedFrom,
    "AnswerResponse": AnswerResponse,
    "AttemptMeta": AttemptMeta,
    "BlockList": BlockList,
    "ChatSessionContext": ChatSessionContext,
    "ChatTrace": ChatTrace,
    "CitationList": CitationList,
    "DetectionSpec": DetectionSpec,
    "DistractorMisconceptions": DistractorMisconceptions,
    "DistractorSelection": DistractorSelection,
    "ExerciseContextList": ExerciseContextList,
    "ExerciseCreatedFrom": ExerciseCreatedFrom,
    "ExpectedAnswer": ExpectedAnswer,
    "ExternalSourceCursorDocument": ExternalSourceCursorDocument,
    "ExternalSourceOptions": ExternalSourceOptions,
    "ExtractionConfidence": ExtractionConfidence,
    "FeedbackList": FeedbackList,
    "HelpEventList": HelpEventList,
    "JobPayload": JobPayload,
    "MaterialProvenance": MaterialProvenance,
    "MentionList": MentionList,
    "MentionRegistryList": MentionRegistryList,
    "ProfilePreferences": ProfilePreferences,
    "ProposalPayload": ProposalPayload,
    "ProposalResult": ProposalResult,
    "ProviderStatus": ProviderStatus,
    "QuestionAnswer": QuestionAnswer,
    "QuestionProvenance": QuestionProvenance,
    "QuestionStats": QuestionStats,
    "ReadList": ReadList,
    "RubricDocument": RubricDocument,
    "SkillContract": SkillContract,
    "SkillParams": SkillParams,
    "StepFeedbackList": StepFeedbackList,
    "StepResponse": StepResponse,
    "StepState": StepState,
    "StringList": StringList,
    "StrokeList": StrokeList,
    "SuggestionMeta": SuggestionMeta,
    "SympyCheck": SympyCheck,
    "TaskParams": TaskParams,
    "ToolCallList": ToolCallList,
    "TrashPayload": TrashPayload,
    "WidgetStateMap": WidgetStateMap,
}
