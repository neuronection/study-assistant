"""per-course task model overrides"""

import sqlalchemy as sa

from alembic import op

revision = "0042_course_task_assignments"
down_revision = "0041_default_task_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_task_assignments",
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("task", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("fallback_model_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"]),
        sa.ForeignKeyConstraint(["fallback_model_id"], ["models.id"]),
        sa.PrimaryKeyConstraint("course_id", "task"),
    )
    op.create_index(
        "ix_course_task_assignments_course",
        "course_task_assignments",
        ["course_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_course_task_assignments_course", table_name="course_task_assignments"
    )
    op.drop_table("course_task_assignments")
