import sqlalchemy as sa

from alembic import op

revision: str = "0062_material_suggestions"
down_revision: str | None = "0061_material_source_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("url_norm", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_material_suggestions_profile_id",
        "material_suggestions",
        ["profile_id"],
    )
    op.create_index(
        "ix_material_suggestions_course_id",
        "material_suggestions",
        ["course_id"],
    )
    op.create_index(
        "uq_material_suggestions_profile_url",
        "material_suggestions",
        ["profile_id", "url_norm"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_material_suggestions_profile_url", table_name="material_suggestions"
    )
    op.drop_index(
        "ix_material_suggestions_course_id", table_name="material_suggestions"
    )
    op.drop_index(
        "ix_material_suggestions_profile_id", table_name="material_suggestions"
    )
    op.drop_table("material_suggestions")
