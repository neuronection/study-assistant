"""phase 3: chat sessions, messages, ai audit log

Revision ID: 0005_chat_audit
Revises: 0004_courses_structure
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_chat_audit"
down_revision: str | None = "0004_courses_structure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_sessions_course_id"), ["course_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_chat_sessions_profile_id"), ["profile_id"], unique=False
        )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("grounded", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_messages_session_id"), ["session_id"], unique=False
        )
    op.create_table(
        "ai_interactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("context_type", sa.String(length=30), nullable=False),
        sa.Column("context_id", sa.Integer(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("skill_version_id", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_ai_interactions_context", ["context_type", "context_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
        batch_op.drop_index("ix_ai_interactions_context")
    op.drop_table("ai_interactions")
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_messages_session_id"))
    op.drop_table("chat_messages")
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_sessions_profile_id"))
        batch_op.drop_index(batch_op.f("ix_chat_sessions_course_id"))
    op.drop_table("chat_sessions")
