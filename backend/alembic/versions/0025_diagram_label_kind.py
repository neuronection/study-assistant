"""Diagram-label exercise kind (plan 95-A).

Widens ``exercises.kind`` with ``diagram_label``. The payload lives in
``exercise_steps.expected`` (image sha + labelled hotspots); grading is
deterministic region/label matching, so no new table is needed.

Revision ID: 0025_diagram_label_kind
Revises: 0024_plan_generated
Create Date: 2026-11-11
"""

from typing import Literal

from alembic import op

revision = "0025_diagram_label_kind"
down_revision = "0024_plan_generated"
branch_labels = None
depends_on = None

KINDS = (
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
    "diagram_label",
)


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def _recreate_mode() -> Literal["auto", "always"]:
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    with op.batch_alter_table("exercises", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("kind_allowed", type_="check")
        batch.create_check_constraint("kind_allowed", f"kind IN ({_values(KINDS)})")


def downgrade() -> None:
    with op.batch_alter_table("exercises", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("kind_allowed", type_="check")
        batch.create_check_constraint(
            "kind_allowed",
            f"kind IN ({_values(tuple(kind for kind in KINDS if kind != 'diagram_label'))})",
        )
