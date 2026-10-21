"""vocab sweep: CHECK twins for questions.type and exercises.kind

Plan 82 C (ADR-204): `QUESTION_TYPES` became the `QuestionType` StrEnum and
the exercise-kind constants became `ExerciseKind`, so the two columns those
vocabularies describe gain their DB CHECK twins in the same round
(family data-model §6). `exercises.kind` also carries the flashcard kinds
(`card_basic` / `card_cloze` / `card_reverse`) — cards are exercise rows.

SQLite cannot add a CHECK to an existing table, so both constraints land
through `batch_alter_table(recreate="always")`; a row carrying a value the
enum does not know makes the copy fail loudly rather than silently keeping
an unrepresentable value. The downgrade drops both constraints and recreates
the previous shape.

Revision ID: 0002_vocab_sweep
Revises: 0001_baseline
Create Date: 2026-10-21
"""

from alembic import op

revision = "0002_vocab_sweep"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

QUESTION_TYPES = (
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
EXERCISE_KINDS = (
    "multi_step",
    "card_basic",
    "card_reverse",
    "card_cloze",
    "matching",
    "ordering",
    "categorize",
    "fill_blank",
    "explain",
    "error_spot",
    "correct_solution",
)


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    with op.batch_alter_table("questions", recreate="always") as batch:
        batch.create_check_constraint("type_allowed", f"type IN ({_values(QUESTION_TYPES)})")
    with op.batch_alter_table("exercises", recreate="always") as batch:
        batch.create_check_constraint("kind_allowed", f"kind IN ({_values(EXERCISE_KINDS)})")


def downgrade() -> None:
    with op.batch_alter_table("exercises", recreate="always") as batch:
        batch.drop_constraint("kind_allowed", type_="check")
    with op.batch_alter_table("questions", recreate="always") as batch:
        batch.drop_constraint("type_allowed", type_="check")
