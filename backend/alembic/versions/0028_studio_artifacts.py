"""Studio artifact specs (plan 98-D/E first cut).

A slide deck or handout is a typed spec plus a generated markdown material in
the library. The spec is the editable/print contract; the material is the
searchable/readable artifact. Deleting either side leaves the other intact
(the FK is SET NULL).

Revision ID: 0028_studio_artifacts
Revises: 0027_solve_entries
Create Date: 2026-11-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0028_studio_artifacts"
down_revision = "0027_solve_entries"
branch_labels = None
depends_on = None

KINDS = ("slide_deck", "handout")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    op.create_table(
        "studio_artifacts",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="slide_deck"),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("source_material_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.CheckConstraint(f"kind IN ({_values(KINDS)})", name="kind_allowed"),
    )
    op.create_index("ix_studio_artifacts_profile_id", "studio_artifacts", ["profile_id"])
    op.create_index("ix_studio_artifacts_course_id", "studio_artifacts", ["course_id"])
    op.create_index(
        "ix_studio_artifacts_profile_created", "studio_artifacts", ["profile_id", "created_at"]
    )
    op.create_index(
        "ix_studio_artifacts_course", "studio_artifacts", ["course_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_studio_artifacts_course", table_name="studio_artifacts")
    op.drop_index("ix_studio_artifacts_profile_created", table_name="studio_artifacts")
    op.drop_index("ix_studio_artifacts_course_id", table_name="studio_artifacts")
    op.drop_index("ix_studio_artifacts_profile_id", table_name="studio_artifacts")
    op.drop_table("studio_artifacts")
