"""phase 7 slice 6: skills, skill versions, course types

Revision ID: 0013_skills
Revises: 0012_cost_ledger
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_skills"
down_revision: str | None = "0012_cost_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("course_types", schema=None) as batch_op:
        batch_op.create_index("uq_course_types_key", ["key"], unique=True)
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("skills", schema=None) as batch_op:
        batch_op.create_index("uq_skills_key", ["key"], unique=True)
    op.create_table(
        "skill_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_ref", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_template", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("contract", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("skill_versions", schema=None) as batch_op:
        batch_op.create_index(
            "uq_skill_versions",
            ["skill_id", "scope_type", "scope_ref", "version"],
            unique=True,
        )
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("course_type_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_courses_course_type", "course_types", ["course_type_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.drop_constraint("fk_courses_course_type", type_="foreignkey")
        batch_op.drop_column("course_type_id")
    with op.batch_alter_table("skill_versions", schema=None) as batch_op:
        batch_op.drop_index("uq_skill_versions")
    op.drop_table("skill_versions")
    with op.batch_alter_table("skills", schema=None) as batch_op:
        batch_op.drop_index("uq_skills_key")
    op.drop_table("skills")
    with op.batch_alter_table("course_types", schema=None) as batch_op:
        batch_op.drop_index("uq_course_types_key")
    op.drop_table("course_types")
