import sqlalchemy as sa

from alembic import op

revision: str = "0063_external_sources"
down_revision: str | None = "0062_material_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("scan_interval_sec", sa.Integer(), nullable=True),
        sa.Column("last_scan_error", sa.Text(), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_sources_profile_id", "external_sources", ["profile_id"]
    )
    op.create_index(
        "ix_external_sources_course_id", "external_sources", ["course_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_external_sources_course_id", table_name="external_sources")
    op.drop_index("ix_external_sources_profile_id", table_name="external_sources")
    op.drop_table("external_sources")
