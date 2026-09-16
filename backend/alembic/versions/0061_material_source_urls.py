import sqlalchemy as sa

from alembic import op

revision: str = "0061_material_source_urls"
down_revision: str | None = "0060_quiz_time_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "materials",
        sa.Column("source_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "materials",
        sa.Column("source_url_norm", sa.String(length=2048), nullable=True),
    )
    op.create_index(
        "ix_materials_source_url",
        "materials",
        ["source_url"],
        unique=False,
        sqlite_where=sa.text("source_url IS NOT NULL"),
    )
    op.create_index(
        "uq_materials_course_source_url_norm",
        "materials",
        ["course_id", "source_url_norm"],
        unique=True,
        sqlite_where=sa.text("kind = 'link' AND source_url_norm IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_materials_course_source_url_norm", table_name="materials")
    op.drop_index("ix_materials_source_url", table_name="materials")
    op.drop_column("materials", "source_url_norm")
    op.drop_column("materials", "source_url")
