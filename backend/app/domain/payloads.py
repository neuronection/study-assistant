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

from collections.abc import Mapping
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


class BundleManifestMap(TypedDict, total=False):
    format: str
    app_version: str
    created_at: str
    course_title: str
    options: dict[str, bool]
    counts: dict[str, int]
    warnings: list[str]


class BundleCourseMap(TypedDict, total=False):
    id: str
    title: str
    description: str | None
    subject: str | None
    level: str | None
    goals: list[str] | None
    tags: list[str] | None
    color: str | None
    exam_date: str | None


class BundleTreeRow(TypedDict, total=False):
    id: str
    parent_id: str | None
    title: str
    summary: str | None
    objectives: list[str] | None
    ai_hint: str | None
    order_idx: int
    is_root: bool
    depth: int


class BundleConceptRow(TypedDict, total=False):
    id: str
    name: str
    description: str | None
    aliases: list[str] | None


class BundleConceptLinkRow(TypedDict, total=False):
    from_concept_id: str
    to_concept_id: str
    relation: str


class BundleCoverageRow(TypedDict, total=False):
    node_id: str
    concept_id: str
    weight: float | None


class BundleMaterialDrawingRow(TypedDict, total=False):
    id: str
    strokes: list[StrokeDict]
    png_sha: str | None
    view: dict[str, float] | None
    ocr_markdown: str | None
    ocr_blocks: list[BlockDict] | None
    ocr_version: int


class BundleMaterialExtraction(TypedDict, total=False):
    version: int
    extractor: str
    model: str | None
    blocks: list[BlockDict]
    markdown: str
    language: str | None
    reviewed: bool


class BundleMaterialIndexCard(TypedDict, total=False):
    summary: str | None
    topics: list[str] | None
    key_terms: list[str] | None
    reading_minutes: int | None
    difficulty: int | None


class BundleMaterialLinkRow(TypedDict, total=False):
    node_id: str
    rationale: str | None
    auto_assigned: bool
    confidence: float | None


class BundleMaterialRow(TypedDict, total=False):
    id: str
    kind: str
    title: str
    filename: str
    mime: str | None
    pages: int | None
    language: str | None
    blob_sha: str | None
    provenance: Mapping[str, Any] | None
    source_url: str | None
    source_url_norm: str | None
    tags: list[str] | None
    starred: bool
    drawings: list[BundleMaterialDrawingRow]
    extraction: BundleMaterialExtraction | None
    index_card: BundleMaterialIndexCard | None
    folder_path: str | None
    links: list[BundleMaterialLinkRow]


class BundleFolderRow(TypedDict, total=False):
    id: str
    path: str
    name: str


class BundleFolderLinkRow(TypedDict, total=False):
    node_id: str
    folder_path: str
    rationale: str | None
    auto_assigned: bool
    confidence: float | None


class BundleFoldersMap(TypedDict, total=False):
    folders: list[BundleFolderRow]
    links: list[BundleFolderLinkRow]


class BundleHistoryMap(TypedDict, total=False):
    attempts: list[dict[str, Any]]
    answers: list[dict[str, Any]]
    exercise_sessions: list[dict[str, Any]]
    step_attempts: list[dict[str, Any]]
    quiz_help_events: list[dict[str, Any]]


class BundleConceptsMap(TypedDict, total=False):
    concepts: list[BundleConceptRow]
    links: list[BundleConceptLinkRow]
    coverage: list[BundleCoverageRow]


class TurnFailure(TypedDict, total=False):
    code: str
    detail: str


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


class PresetModelRef(TypedDict, total=False):
    id: str
    name: str
    caps: list[str]


class PresetDecisionModel(PresetModelRef, total=False):
    transport: str
    provisional: bool


class ChatTraceRound(TypedDict, total=False):
    index: int
    streamed: bool
    start_ms: int
    duration_ms: int
    phase: str


class ChatTrace(TypedDict, total=False):
    run_id: str
    model: str | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    repair_rounds: int
    rounds: list[ChatTraceRound]
    thinking: str
    interruption: str
    proposals_dropped: list[str]
    turn_failed: bool


class ProposalPayload(TypedDict, total=False):
    title: str
    body_md: str
    node_id: str | None
    note_id: str | None
    material_id: str | None
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
    note_id: str | None
    material_id: str | None
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
    created: bool | int
    deduped: bool
    replaced_chunk_ids: list[str]
    tags: list[str]
    open_dialog: ProposalPayload


class CoverageReport(TypedDict, total=False):
    total: int
    covered: int
    missing_ids: list[str]


class MaterialProvenance(TypedDict, total=False):
    generator: str
    source: str
    url: str
    kind: str
    converter: str
    model: str | None
    from_material_id: str
    from_version: int
    coverage: CoverageReport
    needs_review: bool
    practice_items: list[dict[str, Any]]
    source_ref: str | None
    video_id: str
    channel: str
    duration_sec: int
    parse_note: str
    note: str


class ExtractionConfidence(TypedDict, total=False):
    pages: list[dict[str, Any]]
    score: float
    mode: str


type ExternalSourceCursorDocument = dict[str, Any]


class CitationAuthor(TypedDict, total=False):
    name: str
    affiliation: str


type AuthorList = list[CitationAuthor]


class SuggestionMeta(TypedDict, total=False):
    site: str
    mcp: bool
    published: str | None
    doi: str
    authors: list[str]
    year: int
    container: str
    citation_kind: str
    source_id: str
    remote_id: str
    remote_name: str
    remote_state: str
    mime: str | None
    size: int
    attachment_url: str
    discovery_kind: str
    material_kind: str
    enclosure_url: str
    enclosure_type: str | None
    enclosure_oversize: bool


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
    last_tested_at: str
    ok: bool
    error: str | None
    model_count: int | None


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
    "materials.citation_authors": "AuthorList",
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
    "PresetDecisionModel": PresetDecisionModel,
    "PresetModelRef": PresetModelRef,
    "ChatTraceRound": ChatTraceRound,
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
    "CoverageReport": CoverageReport,
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
    "BundleConceptsMap": BundleConceptsMap,
    "BundleCourseMap": BundleCourseMap,
    "BundleHistoryMap": BundleHistoryMap,
    "TurnFailure": TurnFailure,
    "WidgetStateMap": WidgetStateMap,
}
