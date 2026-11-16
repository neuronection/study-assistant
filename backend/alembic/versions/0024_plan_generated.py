"""Generated plan items (plan 99-C).

Widens ``plan_items.origin`` with ``generated`` so the adaptive weekly plan is
distinguishable from manual rows and old per-course drafts (which remain
``draft``). A generated row is replaced as a block on the next commit; manual
rows are never touched.

Revision ID: 0024_plan_generated
Revises: 0023_review_filters
Create Date: 2026-11-11
"""

from typing import Literal

from alembic import op

revision = "0024_plan_generated"
down_revision = "0023_review_filters"
branch_labels = None
depends_on = None

ORIGINS = ("manual", "draft", "generated", "calendar")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def _recreate_mode() -> Literal["auto", "always"]:
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    with op.batch_alter_table("plan_items", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("origin_allowed", type_="check")
        batch.create_check_constraint("origin_allowed", f"origin IN ({_values(ORIGINS)})")


def downgrade() -> None:
    with op.batch_alter_table("plan_items", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("origin_allowed", type_="check")
        batch.create_check_constraint(
            "origin_allowed", f"origin IN ({_values(('manual', 'draft', 'calendar'))})"
        )
