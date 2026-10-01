# ruff: noqa: E501 -- frozen schema map lines; reflow when touched
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

# Every text/JSON column of the schema at this revision, tagged by
# storage kind (frozen on purpose — migrations never chase the live models).
TEXT_COLUMNS: dict[str, dict[str, str]] = {
"activities": {"config": "json", "generated_from": "json"},
    "ai_interactions": {"direction": "text"},
    "answers": {"response": "json", "feedback": "json", "error_tags": "json", "help_events": "json"},
    "attempts": {"meta": "json"},
    "chat_messages": {"blocks": "json", "citations": "json", "mentions": "json", "reads": "json", "tool_calls": "json", "state": "json", "warnings": "json", "trace": "json"},
    "chat_proposals": {"payload": "json", "result": "json"},
    "chat_sessions": {"context": "json", "mention_registry": "json", "quiz_pending": "json"},
    "chunks": {"text": "text"},
    "concepts": {"description": "text", "aliases": "json"},
    "course_types": {"description": "text"},
    "courses": {"description": "text", "goals": "json", "tags": "json"},
    "deleted_items": {"payload": "json"},
    "error_patterns": {"description": "text", "example": "text", "detection": "json"},
    "exercise_steps": {"prompt": "json", "expected": "json", "hints_pregenerated": "json", "rubric": "json"},
    "exercises": {"context": "json", "created_from": "json"},
    "external_sources": {"options": "json", "last_scan_error": "text", "cursor": "json"},
    "extractions": {"blocks": "json", "markdown": "text", "confidence": "json"},
    "instance_settings": {"value": "text"},
    "item_stats": {"distractor_selection": "json"},
    "jobs": {"payload": "json", "error": "text"},
    "material_drawings": {"strokes": "json", "view": "json", "ocr_blocks": "json", "ocr_markdown": "text"},
    "material_folder_links": {"rationale": "text"},
    "material_images": {"ocr_markdown": "text"},
    "material_index_cards": {"summary": "text", "topics": "json", "key_terms": "json"},
    "material_links": {"rationale": "text"},
    "material_sources": {"include_globs": "json", "last_scan_error": "text"},
    "material_suggestions": {"snippet": "text", "meta": "json"},
    "materials": {"description": "text", "provenance": "json", "tags": "json"},
    "mistakes": {"concept_ids": "json", "error_tags": "json"},
    "models": {"caps": "json"},
    "note_drawings": {"strokes": "json", "view": "json", "ocr_blocks": "json", "ocr_markdown": "text"},
    "note_versions": {"tags": "json", "body": "json"},
    "notes": {"body": "json", "search_text": "text", "tags": "json"},
    "profiles": {"preferences": "json"},
    "providers": {"status": "json"},
    "questions": {"stem": "json", "options": "json", "answer": "json", "explanation": "json", "concept_ids": "json", "source_refs": "json", "distractor_misconceptions": "json", "sympy_check": "json", "input_modes": "json", "tags": "json", "provenance": "json", "stats": "json"},
    "quiz_help_events": {"markdown": "text", "violations": "text"},
    "skill_versions": {"system_template": "text", "user_template": "text", "params": "json", "contract": "json"},
    "skills": {"description": "text"},
    "step_attempts": {"response": "json", "feedback": "json", "state": "json"},
    "task_assignments": {"params": "json"},
    "tree_nodes": {"summary": "text", "objectives": "json", "ai_hint": "text"},
    "users": {"password_hash": "text"},
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


def _rewrite(table: str, column: str, kind: str, pairs: Sequence[tuple[str, str]]) -> None:
    # SQLite coerces every column to text for replace(); PostgreSQL needs
    # the json columns cast to text and back (replace() has no json form).
    cast_in = f'CAST("{column}" AS TEXT)' if kind == "json" else f'"{column}"'
    expression = cast_in
    for old, new in pairs:
        expression = f"replace({expression}, '{old}', '{new}')"
    if kind == "json" and op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f'UPDATE "{table}" SET "{column}" = ({expression})::json'))
    else:
        op.execute(sa.text(f'UPDATE "{table}" SET "{column}" = {expression}'))


def upgrade() -> None:
    for table, columns in TEXT_COLUMNS.items():
        for column, kind in columns.items():
            _rewrite(table, column, kind, REWRITES)
    for old, new in CARD_KIND_REWRITES:
        op.execute(sa.text(f"UPDATE exercises SET kind = '{new}' WHERE kind = '{old}'"))


def downgrade() -> None:
    reverse = tuple((new, old) for old, new in REWRITES)
    for table, columns in TEXT_COLUMNS.items():
        for column, kind in columns.items():
            _rewrite(table, column, kind, reverse)
    for old, new in CARD_KIND_REWRITES:
        op.execute(sa.text(f"UPDATE exercises SET kind = '{old}' WHERE kind = '{new}'"))
