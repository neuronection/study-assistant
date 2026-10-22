"""quiz question kinds reuse the exercise engines

Plan 87 B (ADR-217): `QuestionType` gains `matching`, `ordering`, `cloze`
and `essay`; the `questions.type` CHECK twin widens in the same commit
(family data-model §6). SQLite cannot alter a CHECK in place, so the
constraint swaps through `batch_alter_table(recreate="always")`; a row
holding a value the previous vocabulary did not know makes the downgrade
copy fail loudly.

Revision ID: 0008_quiz_question_kinds
Revises: 0007_source_providers
Create Date: 2026-10-22
"""

from alembic import op

revision = "0008_quiz_question_kinds"
down_revision = "0007_source_providers"
branch_labels = None
depends_on = None

BASELINE_TYPES = (
    "single",
    "multi",
    "truefalse",
    "text",
    "numeric",
    "equation",
    "numberline",
    "table_fill",
    "composite",
    "graph_read",
    "code",
)
QUESTION_TYPES = (*BASELINE_TYPES, "matching", "ordering", "cloze", "essay")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    with op.batch_alter_table("questions", recreate="always") as batch:
        batch.drop_constraint("type_allowed", type_="check")
        batch.create_check_constraint("type_allowed", f"type IN ({_values(QUESTION_TYPES)})")


def downgrade() -> None:
    with op.batch_alter_table("questions", recreate="always") as batch:
        batch.drop_constraint("type_allowed", type_="check")
        batch.create_check_constraint("type_allowed", f"type IN ({_values(BASELINE_TYPES)})")
