"""scratchpad course origin + hidden flag

Revision ID: 0053_scratchpad
Revises: 0052_material_description
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0053_scratchpad"
down_revision: str | None = "0052_material_description"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column(
            "origin", sa.String(length=20), nullable=False, server_default="manual"
        ),
    )
    op.add_column(
        "courses",
        sa.Column(
            "hidden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "uq_courses_profile_scratch",
        "courses",
        ["profile_id"],
        unique=True,
        sqlite_where=sa.text("origin = 'scratch'"),
    )


def downgrade() -> None:
    op.drop_index("uq_courses_profile_scratch", table_name="courses")
    op.drop_column("courses", "hidden")
    op.drop_column("courses", "origin")
