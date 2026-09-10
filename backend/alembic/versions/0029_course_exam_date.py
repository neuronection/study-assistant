"""plan 22H: courses.exam_date for the exam planner

Revision ID: 0029_course_exam_date
Revises: 0028_deleted_items
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_course_exam_date"
down_revision: str | None = "0028_deleted_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("exam_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("courses", "exam_date")
