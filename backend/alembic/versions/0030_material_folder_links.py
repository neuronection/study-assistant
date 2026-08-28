"""plan 25A: material_folder_links (folder assignment to nodes, ADR-058)

Revision ID: 0030_material_folder_links
Revises: 0029_course_exam_date
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_material_folder_links"
down_revision: str | None = "0029_course_exam_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_folder_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("folder_id", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("auto_assigned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["folder_id"], ["material_folders.id"]),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "folder_id"),
    )
    op.create_index("ix_material_folder_links_course_id", "material_folder_links", ["course_id"])
    op.create_index("ix_material_folder_links_folder_id", "material_folder_links", ["folder_id"])
    op.create_index("ix_material_folder_links_node_id", "material_folder_links", ["node_id"])


def downgrade() -> None:
    op.drop_index("ix_material_folder_links_node_id", table_name="material_folder_links")
    op.drop_index("ix_material_folder_links_folder_id", table_name="material_folder_links")
    op.drop_index("ix_material_folder_links_course_id", table_name="material_folder_links")
    op.drop_table("material_folder_links")
