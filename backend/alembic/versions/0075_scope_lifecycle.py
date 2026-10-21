"""scope_lifecycle — dead schema out, scope & lifecycle law (plan 81 E, ADR-201)

* `material_groups` and `materials.group_id` are deleted. The table was a P0
  feature (plan 01 A4) that shipped as tables only — no CRUD, no UI, no
  service. Grouping is served by node placement (`material_links`) plus
  material folders; a real group feature would arrive with its own plan.
* `skill_versions.scope_ref` becomes `Uuid(as_uuid=False)`: its values are
  `courses.id`/`course_types.id` UUIDs (C retyped every reader and the docs
  but missed this column, which stayed `Integer` and would reject UUID text
  on PostgreSQL).
* `skill_versions` gains the nullable-unique law (constitution §9): a
  partial unique index on `(skill_id, scope_type, version) WHERE
  scope_ref IS NULL`, so global-scope versions are unique on both dialects
  (the plain unique index treats NULLs as distinct on SQLite and PG).

Every step is guarded: 0073 rebuilds the identity domain from the *current*
model metadata, so on a fresh chain the material tables are already rebuilt
without `group_id`/`material_groups` and `scope_ref` is already UUID. A
database that sat at 0074 before this model change still carries the old
columns and is migrated.

`downgrade()` restores the previous *shape* — the empty `material_groups`
table, `materials.group_id` with its FK/index, and the integer
`skill_versions.scope_ref` (values become NULL on PostgreSQL where an
integer column could never have held UUIDs; SQLite keeps the text values).
No data path: dev databases are rebuilt, not migrated (ADR-196).

Revision ID: 0075_scope_lifecycle
Revises: 0074_payload_law
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0075_scope_lifecycle"
down_revision: str | None = "0074_payload_law"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.Uuid(as_uuid=False)

_SKILL_UNIQUE = "uq_skill_versions"
_SKILL_GLOBAL_UNIQUE = "uq_skill_versions_global"


def _has_table(bind: sa.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _has_column(bind: sa.Connection, table: str, column: str) -> bool:
    if not _has_table(bind, table):
        return False
    return column in {str(item["name"]) for item in sa.inspect(bind).get_columns(table)}


def _has_index(bind: sa.Connection, table: str, index: str) -> bool:
    if not _has_table(bind, table):
        return False
    return index in {str(item["name"]) for item in sa.inspect(bind).get_indexes(table)}


def _rename_global_duplicates(bind: sa.Connection) -> None:
    rows = (
        bind.execute(
            sa.text(
                "SELECT skill_id, scope_type, version, count(*) AS n "
                "FROM skill_versions WHERE scope_ref IS NULL "
                "GROUP BY skill_id, scope_type, version HAVING count(*) > 1"
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        keep = (
            bind.execute(
                sa.text(
                    "SELECT id FROM skill_versions WHERE skill_id = :skill_id "
                    "AND scope_type = :scope_type AND version = :version "
                    "AND scope_ref IS NULL ORDER BY created_at, id"
                ),
                {
                    "skill_id": row["skill_id"],
                    "scope_type": row["scope_type"],
                    "version": row["version"],
                },
            )
            .scalars()
            .all()
        )
        max_version = (
            bind.execute(
                sa.text(
                    "SELECT max(version) FROM skill_versions WHERE skill_id = :skill_id "
                    "AND scope_type = :scope_type AND scope_ref IS NULL"
                ),
                {"skill_id": row["skill_id"], "scope_type": row["scope_type"]},
            ).scalar_one()
            or 0
        )
        for offset, row_id in enumerate(keep[1:], start=1):
            bind.execute(
                sa.text("UPDATE skill_versions SET version = :version WHERE id = :id"),
                {"version": int(max_version) + offset, "id": row_id},
            )


def upgrade() -> None:
    bind = op.get_bind()

    if _has_column(bind, "materials", "group_id"):
        if _has_index(bind, "materials", "ix_materials_group_id"):
            op.drop_index("ix_materials_group_id", table_name="materials")
        with op.batch_alter_table("materials", recreate="always") as batch:
            batch.drop_column("group_id")
    if _has_table(bind, "material_groups"):
        op.drop_table("material_groups")

    if _has_table(bind, "skill_versions"):
        columns = {
            str(item["name"]): item["type"]
            for item in sa.inspect(bind).get_columns("skill_versions")
        }
        if isinstance(columns.get("scope_ref"), sa.Integer):
            bind.execute(
                sa.text(
                    "UPDATE skill_versions SET scope_ref = replace(scope_ref, '-', '') "
                    "WHERE scope_ref IS NOT NULL"
                )
            )
            with op.batch_alter_table("skill_versions", recreate="always") as batch:
                batch.alter_column(
                    "scope_ref",
                    existing_type=sa.Integer(),
                    type_=_UUID,
                    existing_nullable=True,
                    postgresql_using="scope_ref::text::uuid",
                )

        if _has_index(bind, "skill_versions", _SKILL_GLOBAL_UNIQUE):
            op.drop_index(_SKILL_GLOBAL_UNIQUE, table_name="skill_versions")
        if _has_index(bind, "skill_versions", _SKILL_UNIQUE):
            op.drop_index(_SKILL_UNIQUE, table_name="skill_versions")
        _rename_global_duplicates(bind)
        op.create_index(
            _SKILL_UNIQUE,
            "skill_versions",
            ["skill_id", "scope_type", "scope_ref", "version"],
            unique=True,
        )
        op.create_index(
            _SKILL_GLOBAL_UNIQUE,
            "skill_versions",
            ["skill_id", "scope_type", "version"],
            unique=True,
            sqlite_where=sa.text("scope_ref IS NULL"),
            postgresql_where=sa.text("scope_ref IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "skill_versions"):
        if _has_index(bind, "skill_versions", _SKILL_GLOBAL_UNIQUE):
            op.drop_index(_SKILL_GLOBAL_UNIQUE, table_name="skill_versions")
        if _has_index(bind, "skill_versions", _SKILL_UNIQUE):
            op.drop_index(_SKILL_UNIQUE, table_name="skill_versions")
        columns = {
            str(item["name"]): item["type"]
            for item in sa.inspect(bind).get_columns("skill_versions")
        }
        if not isinstance(columns.get("scope_ref"), sa.Integer):
            with op.batch_alter_table("skill_versions", recreate="always") as batch:
                batch.alter_column(
                    "scope_ref",
                    existing_type=_UUID,
                    type_=sa.Integer(),
                    existing_nullable=True,
                    postgresql_using="NULL",
                )
        op.create_index(
            _SKILL_UNIQUE,
            "skill_versions",
            ["skill_id", "scope_type", "scope_ref", "version"],
            unique=True,
        )

    if not _has_table(bind, "material_groups"):
        op.create_table(
            "material_groups",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column(
                "profile_id",
                _UUID,
                sa.ForeignKey("profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "course_id",
                _UUID,
                sa.ForeignKey("courses.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False, server_default="image-set"),
            sa.Column("order_idx", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_material_groups_profile_id", "material_groups", ["profile_id"])
        op.create_index("ix_material_groups_course_id", "material_groups", ["course_id"])

    if not _has_column(bind, "materials", "group_id"):
        with op.batch_alter_table("materials", recreate="always") as batch:
            batch.add_column(sa.Column("group_id", _UUID, nullable=True))
            batch.create_foreign_key(
                "fk_materials_group_id",
                "material_groups",
                ["group_id"],
                ["id"],
                ondelete="CASCADE",
            )
        op.create_index("ix_materials_group_id", "materials", ["group_id"])
