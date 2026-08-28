"""phase 2: chapters, sections, section_materials, material_study_state

Revision ID: 0004_courses_structure
Revises: 0003_folders_providers
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_courses_structure"
down_revision: str | None = "0003_folders_providers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chapters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["chapters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chapters_course_id"), ["course_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_chapters_parent_id"), ["parent_id"], unique=False)
    op.create_table(
        "sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("objectives", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sections", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sections_chapter_id"), ["chapter_id"], unique=False)
    op.create_table(
        "section_materials",
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("extraction_id", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("auto_assigned", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["extraction_id"], ["extractions.id"]),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"]),
        sa.PrimaryKeyConstraint("section_id", "material_id"),
    )
    with op.batch_alter_table("section_materials", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_section_materials_material_id"), ["material_id"], unique=False
        )
    op.create_table(
        "material_study_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("material_study_state", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_study_state_material_id"), ["material_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_material_study_state_profile_id"), ["profile_id"], unique=False
        )
        batch_op.create_index(
            "uq_material_study_state", ["material_id", "profile_id"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("material_study_state", schema=None) as batch_op:
        batch_op.drop_index("uq_material_study_state")
        batch_op.drop_index(batch_op.f("ix_material_study_state_profile_id"))
        batch_op.drop_index(batch_op.f("ix_material_study_state_material_id"))
    op.drop_table("material_study_state")
    with op.batch_alter_table("section_materials", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_section_materials_material_id"))
    op.drop_table("section_materials")
    with op.batch_alter_table("sections", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sections_chapter_id"))
    op.drop_table("sections")
    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chapters_parent_id"))
        batch_op.drop_index(batch_op.f("ix_chapters_course_id"))
    op.drop_table("chapters")
