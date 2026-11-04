"""The schema contract registry: the law half of `docs/dev/schema-contract.md`.

The inventory half is generated from `Base.metadata` by
`scripts/schema_inventory.py`; this module holds the hand-written facts the
metadata cannot express — which columns are closed sets (and their StrEnum
home), what species each JSON column is, how every table is profile-scoped,
and which tables are catalogue/config rather than user data.

Everything here is validated by `tests/test_schema_contract.py`: an entry
that names a missing table/column, an unclassified JSON column, a
closed-set column without a mirrored CHECK, or a table with no scope entry
fails the suite.
"""

from sqlalchemy import CheckConstraint

from ..core.vocab import (
    AttemptMode,
    AuthKind,
    ChatProposalStatus,
    CitationKind,
    ConceptRelation,
    CourseOrigin,
    DegradedReason,
    DiscoveryKind,
    ExerciseKind,
    ExternalSourceKind,
    GoalUnit,
    ItemFlag,
    JobStatus,
    JobType,
    MaterialKind,
    MaterialStatus,
    PlanItemKind,
    PlanItemOrigin,
    ProposalAnchorOp,
    ProposalTargetKind,
    QuestionType,
    QuizVerdict,
    SourcePreset,
    StrVocab,
    StudySessionKind,
    StudySessionSource,
    StudyStatus,
    SuggestionStatus,
)

DOCUMENT = "document"
STATE = "state"
LIST = "list"

CATALOGUE = "catalogue"
INSTANCE = "instance"
IDENTITY = "identity"

CLOSED_SETS: dict[str, type[StrVocab]] = {
    "attempts.mode": AttemptMode,
    "chat_proposal_anchors.op": ProposalAnchorOp,
    "chat_proposals.status": ChatProposalStatus,
    "chat_proposals.target_kind": ProposalTargetKind,
    "chat_quiz_pendings.verdict": QuizVerdict,
    "concept_links.relation": ConceptRelation,
    "courses.origin": CourseOrigin,
    "exercises.kind": ExerciseKind,
    "external_sources.auth_kind": AuthKind,
    "external_sources.kind": ExternalSourceKind,
    "item_stats.flag": ItemFlag,
    "jobs.status": JobStatus,
    "jobs.type": JobType,
    "material_study_state.status": StudyStatus,
    "material_suggestions.kind": DiscoveryKind,
    "material_suggestions.status": SuggestionStatus,
    "materials.kind": MaterialKind,
    "materials.status": MaterialStatus,
    "material_sources.preset": SourcePreset,
    "materials.citation_kind": CitationKind,
    "plan_items.kind": PlanItemKind,
    "plan_items.origin": PlanItemOrigin,
    "questions.flag": ItemFlag,
    "questions.type": QuestionType,
    "retrieval_query_rollups.degraded_reason": DegradedReason,
    "study_goals.unit": GoalUnit,
    "study_sessions.kind": StudySessionKind,
    "study_sessions.source": StudySessionSource,
}

JSON_SPECIES: dict[str, str] = {
    "activities.config": STATE,
    "activities.generated_from": STATE,
    "answers.error_tags": LIST,
    "answers.feedback": DOCUMENT,
    "answers.help_events": DOCUMENT,
    "answers.response": DOCUMENT,
    "attempts.meta": STATE,
    "chat_messages.blocks": DOCUMENT,
    "chat_messages.citations": DOCUMENT,
    "chat_messages.mentions": STATE,
    "chat_messages.reads": STATE,
    "chat_messages.state": STATE,
    "chat_messages.tool_calls": STATE,
    "chat_messages.trace": STATE,
    "chat_messages.warnings": LIST,
    "calendar_links.options": STATE,
    "calendar_links.scopes": LIST,
    "chat_proposals.payload": STATE,
    "chat_proposals.result": STATE,
    "chat_proposals.target_node_path": LIST,
    "chat_quiz_pendings.accept": LIST,
    "chat_quiz_pendings.choices": LIST,
    "chat_sessions.context": STATE,
    "chat_sessions.mention_registry": STATE,
    "concepts.aliases": LIST,
    "courses.goals": LIST,
    "courses.tags": LIST,
    "deleted_items.payload": STATE,
    "error_patterns.detection": STATE,
    "exercise_steps.expected": DOCUMENT,
    "exercise_steps.hints_pregenerated": DOCUMENT,
    "exercise_steps.prompt": DOCUMENT,
    "exercise_steps.rubric": STATE,
    "exercises.context": DOCUMENT,
    "exercises.created_from": STATE,
    "external_sources.cursor": STATE,
    "external_sources.options": STATE,
    "extractions.blocks": DOCUMENT,
    "extractions.confidence": STATE,
    "item_stats.distractor_selection": STATE,
    "jobs.payload": STATE,
    "jobs.result": STATE,
    "material_drawings.ocr_blocks": DOCUMENT,
    "material_drawings.strokes": DOCUMENT,
    "material_index_cards.key_terms": LIST,
    "material_index_cards.topics": LIST,
    "material_sources.include_globs": LIST,
    "material_suggestions.meta": STATE,
    "materials.citation_authors": LIST,
    "materials.provenance": STATE,
    "materials.tags": LIST,
    "mistakes.concept_ids": LIST,
    "mistakes.error_tags": LIST,
    "models.caps": LIST,
    "note_drawings.ocr_blocks": DOCUMENT,
    "note_drawings.strokes": DOCUMENT,
    "note_versions.body": DOCUMENT,
    "note_versions.tags": LIST,
    "notes.body": DOCUMENT,
    "notes.tags": LIST,
    "profiles.preferences": STATE,
    "providers.status": STATE,
    "questions.answer": DOCUMENT,
    "questions.concept_ids": LIST,
    "questions.distractor_misconceptions": STATE,
    "questions.explanation": DOCUMENT,
    "questions.input_modes": LIST,
    "questions.options": DOCUMENT,
    "questions.provenance": STATE,
    "questions.source_refs": LIST,
    "questions.stats": STATE,
    "questions.stem": DOCUMENT,
    "questions.sympy_check": STATE,
    "questions.tags": LIST,
    "retrieval_query_rollups.latency_histogram": STATE,
    "skill_versions.contract": STATE,
    "skill_versions.params": STATE,
    "step_attempts.feedback": DOCUMENT,
    "step_attempts.response": DOCUMENT,
    "step_attempts.state": STATE,
    "task_assignments.params": STATE,
    "tree_nodes.objectives": LIST,
}

PROFILE_SCOPE: dict[str, str] = {
    "activities": "profile_id",
    "ai_interactions": "operational (instance AI telemetry, no user-content record)",
    "answers": "attempt_id → attempts → activities.profile_id",
    "attempts": "activity_id → activities.profile_id",
    "audit_events": IDENTITY,
    "auth_sessions": IDENTITY,
    "blobs": "global content-addressed store",
    "calendar_event_links": "link_id → calendar_links → courses.profile_id",
    "calendar_links": "course_id → courses.profile_id",
    "chat_messages": "session_id → chat_sessions.profile_id",
    "chat_proposal_anchors": (
        "proposal_id → chat_proposals → chat_messages → chat_sessions.profile_id"
    ),
    "chat_proposals": "message_id → chat_messages → chat_sessions.profile_id",
    "chat_quiz_pendings": "session_id → chat_sessions.profile_id",
    "chat_sessions": "profile_id",
    "chunks": "extraction_id → extractions → materials.profile_id",
    "concept_links": "course_id → courses.profile_id",
    "concept_skill_ratings": "profile_id",
    "concept_skill_stats": "profile_id",
    "concepts": "course_id → courses.profile_id",
    "course_default_task_assignments": INSTANCE,
    "course_task_assignments": "course_id → courses.profile_id",
    "course_types": CATALOGUE,
    "courses": "profile_id",
    "daily_rollups": "profile_id",
    "deleted_items": "profile_id",
    "default_task_assignments": INSTANCE,
    "error_patterns": CATALOGUE,
    "exercise_sessions": "exercise_id → exercises.profile_id",
    "exercise_steps": "exercise_id → exercises.profile_id",
    "exercises": "profile_id",
    "external_sources": "profile_id",
    "external_review_events": "source_id → external_sources.profile_id",
    "extractions": "material_id → materials.profile_id",
    "fsrs_states": "card_id → exercises.profile_id",
    "instance_settings": IDENTITY,
    "item_stats": "question_id → questions → activities.profile_id",
    "jobs": "operational (queue state; instance-level by design, no user-content record)",
    "material_drawings": "material_id → materials.profile_id",
    "material_folder_links": "course_id → courses.profile_id",
    "material_folders": "profile_id",
    "material_images": "material_id → materials.profile_id",
    "material_index_cards": "material_id → materials.profile_id",
    "material_links": "course_id → courses.profile_id",
    "material_sources": "profile_id",
    "material_study_state": "profile_id",
    "material_suggestions": "profile_id",
    "materials": "profile_id",
    "mistakes": "profile_id",
    "models": INSTANCE,
    "node_concepts": "node_id → tree_nodes → courses.profile_id",
    "note_drawings": "note_id → notes.profile_id",
    "note_links": "from_note_id → notes.profile_id",
    "note_versions": "profile_id",
    "notes": "profile_id",
    "plan_items": "profile_id",
    "profiles": "own row",
    "providers": INSTANCE,
    "questions": "activity_id → activities.profile_id",
    "quiz_help_events": "attempt_id → attempts → activities.profile_id",
    "quizme_answers": "profile_id",
    "retrieval_coverage_snapshots": (
        "operational (instance vector coverage aggregate, no user-content record)"
    ),
    "retrieval_query_rollups": (
        "operational (instance query-health aggregate, no user-content record)"
    ),
    "review_log": "card_id → exercises.profile_id",
    "skill_versions": (
        "catalogue; course/course_type overrides via scope_ref → courses.id/course_types.id"
    ),
    "skills": CATALOGUE,
    "step_attempts": "session_id → exercise_sessions → exercises.profile_id",
    "study_goals": "profile_id",
    "study_sessions": "profile_id",
    "task_assignments": INSTANCE,
    "tree_nodes": "course_id → courses.profile_id",
    "vector_documents": "profile_id (source material's profile)",
    "vector_records": "document_id → vector_documents.profile_id",
    "vector_spaces": "global derived index configuration (operational)",
    "users": IDENTITY,
}


def split_key(key: str) -> tuple[str, str]:
    table, _, column = key.partition(".")
    return table, column


def vocab_check(column: str, enum: type[StrVocab], *, nullable: bool = False) -> CheckConstraint:
    """A CHECK mirroring an enum's member list.

    The short name (`<column>_allowed`) is what `op.drop_constraint` takes;
    the metadata naming convention renders `ck_<table>_<column>_allowed`.
    """
    values = ", ".join(f"'{member.value}'" for member in enum)
    body = f"{column} IN ({values})"
    if nullable:
        body = f"{column} IS NULL OR {body}"
    return CheckConstraint(body, name=f"{column}_allowed")
