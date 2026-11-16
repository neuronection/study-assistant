"""Artifact registry (plan 90-D first cut).

A typed spec row records what was rendered, its status and the output material.
Audio briefs are the first consumer; the existing Studio/Exam tables stay until
their follow-up migration onto this registry.

Revision ID: 0029_artifacts
Revises: 0028_studio_artifacts
Create Date: 2026-11-11
"""

from typing import Literal

import sqlalchemy as sa

from alembic import op

revision = "0029_artifacts"
down_revision = "0028_studio_artifacts"
branch_labels = None
depends_on = None

KINDS = ("audio_brief", "slide_deck", "handout", "infographic", "exam_paper")
STATUSES = ("pending", "rendering", "ready", "failed", "stale")
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
    "VECTOR_REINDEX",
    "VECTOR_MAINTENANCE",
    "VECTOR_CUTOVER",
)


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def _recreate_mode() -> Literal["auto", "always"]:
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="audio_brief"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("spec_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("output_material_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("job_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("voice", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["output_material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.CheckConstraint(f"kind IN ({_values(KINDS)})", name="kind_allowed"),
        sa.CheckConstraint(f"status IN ({_values(STATUSES)})", name="status_allowed"),
    )
    op.create_index("ix_artifacts_profile_id", "artifacts", ["profile_id"])
    op.create_index("ix_artifacts_course_id", "artifacts", ["course_id"])
    op.create_index("ix_artifacts_profile_created", "artifacts", ["profile_id", "created_at"])
    op.create_index(
        "ix_artifacts_course_node_kind", "artifacts", ["course_id", "node_id", "kind"]
    )
    with op.batch_alter_table("jobs", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("type_allowed", type_="check")
        batch.create_check_constraint("type_allowed", f"type IN ({_values(JOB_TYPES)})")


def downgrade() -> None:
    with op.batch_alter_table("jobs", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("type_allowed", type_="check")
        batch.create_check_constraint(
            "type_allowed",
            f"type IN ({_values(tuple(job for job in JOB_TYPES if job != 'artifact_render'))})",
        )
    op.drop_index("ix_artifacts_course_node_kind", table_name="artifacts")
    op.drop_index("ix_artifacts_profile_created", table_name="artifacts")
    op.drop_index("ix_artifacts_course_id", table_name="artifacts")
    op.drop_index("ix_artifacts_profile_id", table_name="artifacts")
    op.drop_table("artifacts")
