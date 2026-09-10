"""phase 5: exercises, steps, sessions, step attempts

Revision ID: 0007_exercises
Revises: 0006_quiz
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_exercises"
down_revision: str | None = "0006_quiz"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("section_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("created_from", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("exercises", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_exercises_course_id"), ["course_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_exercises_profile_id"), ["profile_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_exercises_section_id"), ["section_id"], unique=False)
    op.create_table(
        "exercise_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.JSON(), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=True),
        sa.Column("hints_pregenerated", sa.JSON(), nullable=True),
        sa.Column("rubric", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("exercise_steps", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_exercise_steps_exercise_id"), ["exercise_id"], unique=False
        )
    op.create_table(
        "exercise_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("current_step_idx", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("socratic", sa.Boolean(), nullable=False),
        sa.Column("independence_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("exercise_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_exercise_sessions_exercise_id"), ["exercise_id"], unique=False
        )
    op.create_table(
        "step_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("step_idx", sa.Integer(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("hint_level_used", sa.Integer(), nullable=True),
        sa.Column("error_class", sa.String(length=30), nullable=True),
        sa.Column("feedback", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["exercise_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("step_attempts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_step_attempts_session_id"), ["session_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("step_attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_step_attempts_session_id"))
    op.drop_table("step_attempts")
    with op.batch_alter_table("exercise_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exercise_sessions_exercise_id"))
    op.drop_table("exercise_sessions")
    with op.batch_alter_table("exercise_steps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exercise_steps_exercise_id"))
    op.drop_table("exercise_steps")
    with op.batch_alter_table("exercises", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exercises_section_id"))
        batch_op.drop_index(batch_op.f("ix_exercises_profile_id"))
        batch_op.drop_index(batch_op.f("ix_exercises_course_id"))
    op.drop_table("exercises")
