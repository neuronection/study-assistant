"""Lecture recording sessions and ordered chunks (plan 93-A).

The session records consent, retention, status and the final material. Chunks
are ordered byte ranges of one logical recording; each row stores the
content-addressed blob sha and byte size for idempotent, gap-checked finalize.

Revision ID: 0031_lecture_sessions
Revises: 0030_media_segments
Create Date: 2026-11-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0031_lecture_sessions"
down_revision = "0030_media_segments"
branch_labels = None
depends_on = None

STATUSES = ("recording", "paused", "uploading", "transcribing", "ready", "failed", "cancelled")
RETENTIONS = ("audio_and_text", "text_only")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    op.create_table(
        "lecture_sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="recording"),
        sa.Column(
            "retention", sa.String(length=20), nullable=False, server_default="audio_and_text"
        ),
        sa.Column("mime", sa.String(length=120), nullable=False, server_default="audio/webm"),
        sa.Column("consent_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.CheckConstraint(f"status IN ({_values(STATUSES)})", name="status_allowed"),
        sa.CheckConstraint(f"retention IN ({_values(RETENTIONS)})", name="retention_allowed"),
    )
    op.create_index("ix_lecture_sessions_profile_id", "lecture_sessions", ["profile_id"])
    op.create_index("ix_lecture_sessions_course_id", "lecture_sessions", ["course_id"])
    op.create_index(
        "ix_lecture_sessions_profile_created", "lecture_sessions", ["profile_id", "created_at"]
    )
    op.create_index("ix_lecture_sessions_course", "lecture_sessions", ["course_id", "created_at"])

    op.create_table(
        "lecture_chunks",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_lecture_chunks_session_id", "lecture_chunks", ["session_id"])
    op.create_index(
        "uq_lecture_chunks_seq", "lecture_chunks", ["session_id", "seq"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_lecture_chunks_seq", table_name="lecture_chunks")
    op.drop_index("ix_lecture_chunks_session_id", table_name="lecture_chunks")
    op.drop_table("lecture_chunks")
    op.drop_index("ix_lecture_sessions_course", table_name="lecture_sessions")
    op.drop_index("ix_lecture_sessions_profile_created", table_name="lecture_sessions")
    op.drop_index("ix_lecture_sessions_course_id", table_name="lecture_sessions")
    op.drop_index("ix_lecture_sessions_profile_id", table_name="lecture_sessions")
    op.drop_table("lecture_sessions")
