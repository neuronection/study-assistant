import sqlalchemy as sa

from alembic import op

revision: str = "0057_material_tags_starred"
down_revision: str | None = "0056_quizme_answers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("materials", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column(
        "materials",
        sa.Column("starred", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_materials_starred",
        "materials",
        ["starred"],
        sqlite_where=sa.text("starred = 1"),
    )


def downgrade() -> None:
    op.drop_index("ix_materials_starred", table_name="materials")
    op.drop_column("materials", "starred")
    op.drop_column("materials", "tags")
