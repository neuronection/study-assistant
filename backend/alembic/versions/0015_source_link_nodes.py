"""phase 8B L1: linked sources as symlink-style folder nodes (ADR-037)

Revision ID: 0015_source_link_nodes
Revises: 0014_course_materials
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_source_link_nodes"
down_revision: str | None = "0014_course_materials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _name_taken(bind: sa.Connection, course_id: int, name: str) -> bool:
    count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM material_folders "
            "WHERE course_id = :course_id AND parent_id IS NULL AND name = :name"
        ),
        {"course_id": course_id, "name": name},
    )
    return int(count.scalar_one()) > 0


def _unique_name(bind: sa.Connection, course_id: int, base: str) -> str:
    name = base[:200]
    index = 2
    while _name_taken(bind, course_id, name):
        name = f"{base[:190]} ({index})"
        index += 1
        if index > 999:
            break
    return name


def upgrade() -> None:
    with op.batch_alter_table("material_folders") as batch_op:
        batch_op.add_column(sa.Column("source_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_material_folders_source_id", "material_sources", ["source_id"], ["id"]
        )
        batch_op.create_unique_constraint("uq_material_folders_source_id", ["source_id"])
    bind = op.get_bind()
    sources = list(
        bind.execute(
            sa.text("SELECT id, profile_id, course_id, label FROM material_sources")
        ).mappings()
    )
    for source in sources:
        base = (source["label"] or "link").replace("/", "-").strip()[:200] or "link"
        name = _unique_name(bind, int(source["course_id"]), base)
        bind.execute(
            sa.text(
                "INSERT INTO material_folders "
                "(profile_id, course_id, parent_id, name, path, source_id, created_at) "
                "VALUES (:profile_id, :course_id, NULL, :name, :name, :source_id, "
                "CURRENT_TIMESTAMP)"
            ),
            {
                "profile_id": source["profile_id"],
                "course_id": source["course_id"],
                "name": name,
                "source_id": source["id"],
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM material_folders WHERE source_id IS NOT NULL")
    )
    with op.batch_alter_table("material_folders") as batch_op:
        batch_op.drop_constraint("uq_material_folders_source_id", type_="unique")
        batch_op.drop_constraint("fk_material_folders_source_id", type_="foreignkey")
        batch_op.drop_column("source_id")
