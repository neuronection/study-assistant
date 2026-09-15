import sqlalchemy as sa

from alembic import op

revision: str = "0058_source_mirror_subdirs"
down_revision: str | None = "0057_material_tags_starred"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "material_sources",
        sa.Column("mirror_subdirs", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("material_sources", "mirror_subdirs")
