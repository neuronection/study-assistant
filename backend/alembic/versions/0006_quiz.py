"""phase 4: activities, questions, attempts, answers, mistakes

Revision ID: 0006_quiz
Revises: 0005_chat_audit
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_quiz"
down_revision: str | None = "0005_chat_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("section_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("generated_from", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_activities_course_id"), ["course_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_activities_profile_id"), ["profile_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_activities_section_id"), ["section_id"], unique=False)
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("stem", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("answer", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("bloom", sa.String(length=20), nullable=True),
        sa.Column("skill", sa.String(length=20), nullable=True),
        sa.Column("concept_ids", sa.JSON(), nullable=True),
        sa.Column("expected_time_sec", sa.Integer(), nullable=True),
        sa.Column("curriculum_code", sa.String(length=120), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=True),
        sa.Column("distractor_misconceptions", sa.JSON(), nullable=True),
        sa.Column("sympy_check", sa.JSON(), nullable=True),
        sa.Column("input_modes", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("flag", sa.String(length=10), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_questions_activity_id"), ["activity_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_questions_parent_id"), ["parent_id"], unique=False)
    op.create_table(
        "attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_attempts_activity_id"), ["activity_id"], unique=False)
    op.create_table(
        "answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("input_mode", sa.String(length=10), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("partial_credit", sa.Float(), nullable=True),
        sa.Column("feedback", sa.JSON(), nullable=True),
        sa.Column("graded_by", sa.String(length=10), nullable=True),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("error_tags", sa.JSON(), nullable=True),
        sa.Column("help_events", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("answers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_answers_attempt_id"), ["attempt_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_answers_question_id"), ["question_id"], unique=False)
    op.create_table(
        "mistakes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("concept_ids", sa.JSON(), nullable=True),
        sa.Column("error_tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("mistakes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mistakes_profile_id"), ["profile_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_mistakes_question_id"), ["question_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("mistakes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mistakes_question_id"))
        batch_op.drop_index(batch_op.f("ix_mistakes_profile_id"))
    op.drop_table("mistakes")
    with op.batch_alter_table("answers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_answers_question_id"))
        batch_op.drop_index(batch_op.f("ix_answers_attempt_id"))
    op.drop_table("answers")
    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_attempts_activity_id"))
    op.drop_table("attempts")
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_questions_parent_id"))
        batch_op.drop_index(batch_op.f("ix_questions_activity_id"))
    op.drop_table("questions")
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_activities_section_id"))
        batch_op.drop_index(batch_op.f("ix_activities_profile_id"))
        batch_op.drop_index(batch_op.f("ix_activities_course_id"))
    op.drop_table("activities")
