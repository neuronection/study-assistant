"""planner items carry their calendar UID

Plan 85 C (ADR-213): an imported ICS occurrence is a normal planner item with
an `external_uid`, so re-importing the same timetable updates rows instead of
duplicating the week. Business-law uniqueness lives in a partial unique index
(NULL UIDs are ordinary hand-made items and stay NULL-distinct, family
data-model §9).

Revision ID: 0005_plan_item_external_uid
Revises: 0004_citation_metadata
Create Date: 2026-10-22
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_plan_item_external_uid"
down_revision = "0004_citation_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plan_items", sa.Column("external_uid", sa.String(200), nullable=True))
    op.create_index(
        "uq_plan_items_course_external_uid",
        "plan_items",
        ["course_id", "external_uid"],
        unique=True,
        sqlite_where=sa.text("external_uid IS NOT NULL"),
        postgresql_where=sa.text("external_uid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_plan_items_course_external_uid", table_name="plan_items")
    op.drop_column("plan_items", "external_uid")
