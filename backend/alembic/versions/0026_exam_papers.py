"""Exam papers (plan 96-A).

A paper is an ``Activity`` (type ``exam``) plus a typed ``PaperDocument``
describing sections, marks and the ordered question ids. Questions are copied
from the bank at assembly time, so later bank edits never change a paper
already sat (snapshot immutability by construction).

Revision ID: 0026_exam_papers
Revises: 0025_diagram_label_kind
Create Date: 2026-11-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0026_exam_papers"
down_revision = "0025_diagram_label_kind"
branch_labels = None
depends_on = None

SOURCES = ("bank", "document")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    op.create_table(
        "exam_papers",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("activity_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("instructions_md", sa.Text(), nullable=True),
        sa.Column("duration_min", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("total_marks", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("grade_bands", sa.JSON(), nullable=True),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="bank"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"source IN ({_values(SOURCES)})", name="source_allowed"),
        sa.CheckConstraint("duration_min > 0", name="duration_positive"),
        sa.CheckConstraint("total_marks > 0", name="marks_positive"),
    )
    op.create_index("ix_exam_papers_profile_id", "exam_papers", ["profile_id"])
    op.create_index("ix_exam_papers_course_id", "exam_papers", ["course_id"])
    op.create_index(
        "ix_exam_papers_profile_created", "exam_papers", ["profile_id", "created_at"]
    )
    op.create_index("ix_exam_papers_course", "exam_papers", ["course_id", "created_at"])
    op.create_index("uq_exam_papers_activity", "exam_papers", ["activity_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_exam_papers_activity", table_name="exam_papers")
    op.drop_index("ix_exam_papers_course", table_name="exam_papers")
    op.drop_index("ix_exam_papers_profile_created", table_name="exam_papers")
    op.drop_index("ix_exam_papers_course_id", table_name="exam_papers")
    op.drop_index("ix_exam_papers_profile_id", table_name="exam_papers")
    op.drop_table("exam_papers")
