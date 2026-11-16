"""Capture intake kernel — staged, source-attributed uploads (plan 90-A).

Creates the two tables the capture kernel owns. Staging is a row in front of the
existing upload/ingest path: the bytes land in the ordinary content-addressed
blob store, commit delegates to ``MaterialsService.upload`` and only then marks
the row committed. Expiry is a status transition (never a blob delete), so the
immortal blob store and trash restore keep their guarantees (ADR-201).

``capture_tokens`` is the profile-bound device credential for external capture
sources (share target/clipper, plan 92). Plaintext tokens are never stored —
only their SHA-256 hash, the closed scope and revoke metadata.

Revision ID: 0020_capture_staging
Revises: 0019_job_progress_detail
Create Date: 2026-11-10
"""

import sqlalchemy as sa

from alembic import op

revision = "0020_capture_staging"
down_revision = "0019_job_progress_detail"
branch_labels = None
depends_on = None

CAPTURE_KINDS = ("upload", "camera", "clipboard", "drop", "share", "clipper")
CAPTURE_STATUSES = ("staged", "committed", "discarded", "expired")
CAPTURE_SCOPES = ("capture:stage", "capture:clip")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    op.create_table(
        "capture_staging",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="staged"),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=True),
        sa.Column("blob_sha", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=True),
        sa.Column("client_op_id", sa.String(length=120), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blob_sha"], ["blobs.sha256"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            f"source_kind IN ({_values(CAPTURE_KINDS)})", name="source_kind_allowed"
        ),
        sa.CheckConstraint(f"status IN ({_values(CAPTURE_STATUSES)})", name="status_allowed"),
    )
    op.create_index("ix_capture_staging_profile_id", "capture_staging", ["profile_id"])
    op.create_index(
        "ix_capture_staging_profile_status",
        "capture_staging",
        ["profile_id", "status"],
    )
    op.create_index("ix_capture_staging_group_id", "capture_staging", ["group_id"])
    op.create_index("ix_capture_staging_material_id", "capture_staging", ["material_id"])
    op.create_index(
        "uq_capture_staging_client_op",
        "capture_staging",
        ["profile_id", "client_op_id"],
        unique=True,
        postgresql_where=sa.text("client_op_id IS NOT NULL"),
        sqlite_where=sa.text("client_op_id IS NOT NULL"),
    )

    op.create_table(
        "capture_tokens",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.CheckConstraint(f"scope IN ({_values(CAPTURE_SCOPES)})", name="scope_allowed"),
    )
    op.create_index("ix_capture_tokens_profile_id", "capture_tokens", ["profile_id"])
    op.create_index(
        "ix_capture_tokens_profile_revoked",
        "capture_tokens",
        ["profile_id", "revoked_at"],
    )
    op.create_index("uq_capture_tokens_hash", "capture_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_capture_tokens_hash", table_name="capture_tokens")
    op.drop_index("ix_capture_tokens_profile_revoked", table_name="capture_tokens")
    op.drop_index("ix_capture_tokens_profile_id", table_name="capture_tokens")
    op.drop_table("capture_tokens")
    op.drop_index("uq_capture_staging_client_op", table_name="capture_staging")
    op.drop_index("ix_capture_staging_material_id", table_name="capture_staging")
    op.drop_index("ix_capture_staging_group_id", table_name="capture_staging")
    op.drop_index("ix_capture_staging_profile_status", table_name="capture_staging")
    op.drop_index("ix_capture_staging_profile_id", table_name="capture_staging")
    op.drop_table("capture_staging")
