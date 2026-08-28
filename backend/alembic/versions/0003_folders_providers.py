"""phase 1: material folders, providers, models, task assignments

Revision ID: 0003_folders_providers
Revises: 13c777fc9e3e
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_folders_providers"
down_revision: str | None = "13c777fc9e3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_folders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["material_folders.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("material_folders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_folders_parent_id"), ["parent_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_material_folders_profile_id"), ["profile_id"], unique=False
        )
        batch_op.create_index(
            "uq_material_folders_profile_path", ["profile_id", "path"], unique=True
        )
    with op.batch_alter_table("materials", schema=None) as batch_op:
        batch_op.add_column(sa.Column("folder_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_materials_folder_id", "material_folders", ["folder_id"], ["id"]
        )
        batch_op.create_index(batch_op.f("ix_materials_folder_id"), ["folder_id"], unique=False)
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("base_url", sa.String(length=300), nullable=False),
        sa.Column("keyring_ref", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("caps", sa.JSON(), nullable=False),
        sa.Column("ctx_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_in", sa.Float(), nullable=True),
        sa.Column("cost_out", sa.Float(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("missing", sa.Boolean(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_models_provider_id"), ["provider_id"], unique=False)
        batch_op.create_index(
            "uq_models_provider_external", ["provider_id", "external_id"], unique=True
        )
    op.create_table(
        "task_assignments",
        sa.Column("task", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("fallback_model_id", sa.Integer(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["fallback_model_id"], ["models.id"]),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"]),
        sa.PrimaryKeyConstraint("task"),
    )


def downgrade() -> None:
    op.drop_table("task_assignments")
    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.drop_index("uq_models_provider_external")
        batch_op.drop_index(batch_op.f("ix_models_provider_id"))
    op.drop_table("models")
    op.drop_table("providers")
    with op.batch_alter_table("materials", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_materials_folder_id"))
        batch_op.drop_constraint("fk_materials_folder_id", type_="foreignkey")
        batch_op.drop_column("folder_id")
    with op.batch_alter_table("material_folders", schema=None) as batch_op:
        batch_op.drop_index("uq_material_folders_profile_path")
        batch_op.drop_index(batch_op.f("ix_material_folders_profile_id"))
        batch_op.drop_index(batch_op.f("ix_material_folders_parent_id"))
    op.drop_table("material_folders")
