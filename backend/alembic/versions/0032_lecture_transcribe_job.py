"""Lecture transcription job type (plan 93-B).

Revision ID: 0032_lecture_transcribe_job
Revises: 0031_lecture_sessions
Create Date: 2026-11-11
"""

from typing import Literal

import sqlalchemy as sa

from alembic import op

revision = "0032_lecture_transcribe_job"
down_revision = "0031_lecture_sessions"
branch_labels = None
depends_on = None

JOB_TYPES = (
    "ingest",
    "postprocess",
    "chat_turn",
    "drawing_ocr",
    "image_ocr",
    "genesis",
    "url_import",
    "compose",
    "artifact_render",
    "lecture_transcribe",
    "VECTOR_REINDEX",
    "VECTOR_MAINTENANCE",
    "VECTOR_CUTOVER",
)


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def _recreate_mode() -> Literal["auto", "always"]:
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    op.add_column(
        "lecture_sessions",
        sa.Column("audio_purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("jobs", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("type_allowed", type_="check")
        batch.create_check_constraint("type_allowed", f"type IN ({_values(JOB_TYPES)})")


def downgrade() -> None:
    op.drop_column("lecture_sessions", "audio_purged_at")
    with op.batch_alter_table("jobs", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("type_allowed", type_="check")
        batch.create_check_constraint(
            "type_allowed",
            f"type IN ({_values(tuple(v for v in JOB_TYPES if v != 'lecture_transcribe'))})",
        )
