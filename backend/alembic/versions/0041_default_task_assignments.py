"""default_task_assignments (per-capability default models for task assignment)

Revision ID: 0041_default_task_assignments
Revises: 0040_chat_warnings
Create Date: 2026-08-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0041_default_task_assignments"
down_revision: str | None = "0040_chat_warnings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "default_task_assignments",
        sa.Column("requires", sa.String(40), primary_key=True),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("models.id"), nullable=True),
        sa.Column(
            "fallback_model_id", sa.Integer(), sa.ForeignKey("models.id"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_table("default_task_assignments")
