"""phase 1 core tables + material_fts

Revision ID: 13c777fc9e3e
Revises: 0001_baseline
Create Date: 2026-08-18 20:26:19.004555

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "13c777fc9e3e"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blobs",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("rel_path", sa.String(length=500), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sha256"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=120), nullable=True),
        sa.Column("level", sa.String(length=120), nullable=True),
        sa.Column("goals", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_courses_profile_id"), ["profile_id"], unique=False)
    op.create_table(
        "material_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("material_groups", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_groups_course_id"), ["course_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_material_groups_profile_id"), ["profile_id"], unique=False
        )
    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("blob_sha", sa.String(length=64), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("phash", sa.String(length=24), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("external_path", sa.String(length=1000), nullable=True),
        sa.Column("file_mtime", sa.Float(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["blob_sha"], ["blobs.sha256"]),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["material_groups.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("materials", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_materials_content_hash"), ["content_hash"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_materials_course_id"), ["course_id"], unique=False)
        batch_op.create_index("ix_materials_course_status", ["course_id", "status"], unique=False)
        batch_op.create_index(batch_op.f("ix_materials_group_id"), ["group_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_materials_profile_id"), ["profile_id"], unique=False)
    op.create_table(
        "extractions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("extractor", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("blocks", sa.JSON(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("confidence", sa.JSON(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("token_in", sa.Integer(), nullable=True),
        sa.Column("token_out", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("edited_by_user", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_extractions_material_id"), ["material_id"], unique=False
        )
    op.create_table(
        "material_index_cards",
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("key_terms", sa.JSON(), nullable=True),
        sa.Column("reading_minutes", sa.Integer(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.PrimaryKeyConstraint("material_id"),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("extraction_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["extraction_id"], ["extractions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chunks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chunks_extraction_id"), ["extraction_id"], unique=False
        )
    op.execute(
        "CREATE VIRTUAL TABLE material_fts USING fts5("
        "title, markdown, description, topics, material_id UNINDEXED)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE material_fts")
    with op.batch_alter_table("chunks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chunks_extraction_id"))
    op.drop_table("chunks")
    op.drop_table("material_index_cards")
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_extractions_material_id"))
    op.drop_table("extractions")
    with op.batch_alter_table("materials", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_materials_profile_id"))
        batch_op.drop_index(batch_op.f("ix_materials_group_id"))
        batch_op.drop_index("ix_materials_course_status")
        batch_op.drop_index(batch_op.f("ix_materials_course_id"))
        batch_op.drop_index(batch_op.f("ix_materials_content_hash"))
    op.drop_table("materials")
    with op.batch_alter_table("material_groups", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_material_groups_profile_id"))
        batch_op.drop_index(batch_op.f("ix_material_groups_course_id"))
    op.drop_table("material_groups")
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_courses_profile_id"))
    op.drop_table("courses")
    op.drop_table("profiles")
    op.drop_table("jobs")
    op.drop_table("blobs")
