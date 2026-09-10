"""phase 8D: concepts, concept links, section concepts

Revision ID: 0018_concepts
Revises: 0017_note_tags
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_concepts"
down_revision: str | None = "0017_note_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "concepts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "name"),
    )
    op.create_index("ix_concepts_course_id", "concepts", ["course_id"])
    op.create_table(
        "concept_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("from_concept_id", sa.Integer(), nullable=False),
        sa.Column("to_concept_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["from_concept_id"], ["concepts.id"]),
        sa.ForeignKeyConstraint(["to_concept_id"], ["concepts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_concept_id", "to_concept_id", "relation"
        ),
    )
    op.create_index(
        "ix_concept_links_course_id", "concept_links", ["course_id"]
    )
    op.create_table(
        "section_concepts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"]),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("section_id", "concept_id"),
    )
    op.create_index(
        "ix_section_concepts_section_id", "section_concepts", ["section_id"]
    )
    with op.batch_alter_table("concept_skill_stats") as batch_op:
        batch_op.add_column(sa.Column("concept_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("concept_skill_stats") as batch_op:
        batch_op.drop_column("concept_id")
    op.drop_index(
        "ix_section_concepts_section_id", table_name="section_concepts"
    )
    op.drop_table("section_concepts")
    op.drop_index("ix_concept_links_course_id", table_name="concept_links")
    op.drop_table("concept_links")
    op.drop_index("ix_concepts_course_id", table_name="concepts")
    op.drop_table("concepts")
