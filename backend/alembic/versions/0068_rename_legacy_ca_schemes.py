"""rename legacy CourseAssistant strings to their StudyAssistant forms

One-shot rewrite of stored strings (plan 20 Phase 6, D10 — no dual-read
compatibility): the `ca-drawing://` / `ca-image://` / `ca-material://`
schemes, the `ca-course/v1|v2` and `caq/v1` format markers, and the
legacy card kinds (`basic` / `cloze` / `reverse`) become `sa-*` /
`card_*`. Application code speaks only the new forms from this revision
on; downgrading restores the old spellings (best-effort).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0068_rename_legacy_ca_schemes"
down_revision: str | None = "0067_auth_session_created_at"

# Every text/JSON column of the schema at this revision (frozen on
# purpose — migrations never chase the live models).
TEXT_COLUMNS: dict[str, Sequence[str]] = {
    "activities": ["config", "generated_from"],
    "ai_interactions": ["direction"],
    "answers": ["response", "feedback", "error_tags", "help_events"],
    "attempts": ["meta"],
    "chat_messages": [
        "blocks",
        "citations",
        "mentions",
        "reads",
        "tool_calls",
        "state",
        "warnings",
        "trace",
    ],
    "chat_proposals": ["payload", "result"],
    "chat_sessions": ["context", "mention_registry", "quiz_pending"],
    "chunks": ["text"],
    "concepts": ["description", "aliases"],
    "course_types": ["description"],
    "courses": ["description", "goals", "tags"],
    "deleted_items": ["payload"],
    "error_patterns": ["description", "example", "detection"],
    "exercise_steps": ["prompt", "expected", "hints_pregenerated", "rubric"],
    "exercises": ["context", "created_from"],
    "external_sources": ["options", "last_scan_error", "cursor"],
    "extractions": ["blocks", "markdown", "confidence"],
    "instance_settings": ["value"],
    "item_stats": ["distractor_selection"],
    "jobs": ["payload", "error"],
    "material_drawings": ["strokes", "view", "ocr_blocks", "ocr_markdown"],
    "material_folder_links": ["rationale"],
    "material_images": ["ocr_markdown"],
    "material_index_cards": ["summary", "topics", "key_terms"],
    "material_links": ["rationale"],
    "material_sources": ["include_globs", "last_scan_error"],
    "material_suggestions": ["snippet", "meta"],
    "materials": ["description", "provenance", "tags"],
    "mistakes": ["concept_ids", "error_tags"],
    "models": ["caps"],
    "note_drawings": ["strokes", "view", "ocr_blocks", "ocr_markdown"],
    "note_versions": ["tags", "body"],
    "notes": ["body", "search_text", "tags"],
    "profiles": ["preferences"],
    "providers": ["status"],
    "questions": [
        "stem",
        "options",
        "answer",
        "explanation",
        "concept_ids",
        "source_refs",
        "distractor_misconceptions",
        "sympy_check",
        "input_modes",
        "tags",
        "provenance",
        "stats",
    ],
    "quiz_help_events": ["markdown", "violations"],
    "skill_versions": ["system_template", "user_template", "params", "contract"],
    "skills": ["description"],
    "step_attempts": ["response", "feedback", "state"],
    "task_assignments": ["params"],
    "tree_nodes": ["summary", "objectives", "ai_hint"],
    "users": ["password_hash"],
}

REWRITES: Sequence[tuple[str, str]] = (
    ("ca-drawing://", "sa-drawing://"),
    ("ca-image://", "sa-image://"),
    ("ca-material://", "sa-material://"),
    ("ca-course/v", "sa-course/v"),
    ("caq/v1", "saq/v1"),
)

# Legacy card kinds -> native card kinds (the LEGACY_CARD_KIND_MAP is gone).
CARD_KIND_REWRITES: Sequence[tuple[str, str]] = (
    ("basic", "card_basic"),
    ("cloze", "card_cloze"),
    ("reverse", "card_reverse"),
)


def _rewrite(table: str, column: str, pairs: Sequence[tuple[str, str]]) -> None:
    expression = f'"{column}"'
    for old, new in pairs:
        expression = f"replace({expression}, '{old}', '{new}')"
    op.execute(sa.text(f'UPDATE "{table}" SET "{column}" = {expression}'))


def upgrade() -> None:
    for table, columns in TEXT_COLUMNS.items():
        for column in columns:
            _rewrite(table, column, REWRITES)
    for old, new in CARD_KIND_REWRITES:
        op.execute(sa.text(f"UPDATE exercises SET kind = '{new}' WHERE kind = '{old}'"))


def downgrade() -> None:
    reverse = tuple((new, old) for old, new in REWRITES)
    for table, columns in TEXT_COLUMNS.items():
        for column in columns:
            _rewrite(table, column, reverse)
    for old, new in CARD_KIND_REWRITES:
        op.execute(sa.text(f"UPDATE exercises SET kind = '{old}' WHERE kind = '{new}'"))
