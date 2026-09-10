"""phase 8a: per-course materials, material_links, per-course folders (ADR-036)

Revision ID: 0014_course_materials
Revises: 0013_skills
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_course_materials"
down_revision: str | None = "0013_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNSORTED_TITLE = "Unsorted"


def _unsorted_course_id(bind: sa.Connection, profile_id: int) -> int:
    existing = bind.execute(
        sa.text(
            "SELECT id FROM courses WHERE profile_id = :profile_id AND title = :title"
        ),
        {"profile_id": profile_id, "title": UNSORTED_TITLE},
    ).scalar()
    if existing is not None:
        return int(existing)
    new_id = bind.execute(
        sa.text(
            "INSERT INTO courses (profile_id, title, description, created_at, updated_at) "
            "VALUES (:profile_id, :title, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
            "RETURNING id"
        ),
        {"profile_id": profile_id, "title": UNSORTED_TITLE},
    ).scalar_one()
    return int(new_id)

def upgrade() -> None:
    op.create_table(
        "material_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_type", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("extraction_id", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("auto_assigned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["extraction_id"], ["extractions.id"]),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_type", "owner_id", "material_id"),
    )
    op.create_index("ix_material_links_material_id", "material_links", ["material_id"])
    op.create_index("ix_material_links_owner", "material_links", ["owner_type", "owner_id"])
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO material_links "
            "(owner_type, owner_id, material_id, extraction_id, rationale, "
            "auto_assigned, confidence, created_at) "
            "SELECT 'section', section_id, material_id, extraction_id, rationale, "
            "auto_assigned, confidence, CURRENT_TIMESTAMP "
            "FROM section_materials"
        )
    )
    op.drop_table("section_materials")

    op.drop_index("uq_material_folders_profile_path", table_name="material_folders")
    with op.batch_alter_table("material_folders") as batch_op:
        batch_op.add_column(sa.Column("course_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_material_folders_course_id", "courses", ["course_id"], ["id"]
        )

    profile_ids = list(bind.execute(sa.text("SELECT id FROM profiles")).scalars())
    for profile_id in profile_ids:
        orphan_count = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM materials "
                "WHERE profile_id = :profile_id AND course_id IS NULL"
            ),
            {"profile_id": profile_id},
        ).scalar()
        unsorted_id: int | None = None
        if orphan_count:
            unsorted_id = _unsorted_course_id(bind, profile_id)
            bind.execute(
                sa.text(
                    "UPDATE materials SET course_id = :course_id "
                    "WHERE profile_id = :profile_id AND course_id IS NULL"
                ),
                {"course_id": unsorted_id, "profile_id": profile_id},
            )
        source_count = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM material_sources "
                "WHERE profile_id = :profile_id AND course_id IS NULL"
            ),
            {"profile_id": profile_id},
        ).scalar()
        if source_count:
            if unsorted_id is None:
                unsorted_id = _unsorted_course_id(bind, profile_id)
            bind.execute(
                sa.text(
                    "UPDATE material_sources SET course_id = :course_id "
                    "WHERE profile_id = :profile_id AND course_id IS NULL"
                ),
                {"course_id": unsorted_id, "profile_id": profile_id},
            )
        if not bind.execute(
            sa.text("SELECT COUNT(*) FROM material_folders WHERE profile_id = :profile_id"),
            {"profile_id": profile_id},
        ).scalar():
            continue
        if unsorted_id is None:
            unsorted_id = _unsorted_course_id(bind, profile_id)
        folder_courses: dict[int, set[int]] = {}
        for row in bind.execute(
            sa.text(
                "SELECT folder_id, course_id FROM materials "
                "WHERE profile_id = :profile_id AND folder_id IS NOT NULL"
            ),
            {"profile_id": profile_id},
        ).mappings():
            courses = folder_courses.setdefault(int(row["folder_id"]), set())
            if row["course_id"] is not None:
                courses.add(int(row["course_id"]))
        folders = list(
            bind.execute(
                sa.text(
                    "SELECT id, parent_id FROM material_folders "
                    "WHERE profile_id = :profile_id ORDER BY path"
                ),
                {"profile_id": profile_id},
            ).mappings()
        )
        children: dict[int | None, list[int]] = {}
        for folder in folders:
            children.setdefault(folder["parent_id"], []).append(int(folder["id"]))

        def subtree_courses(
            folder_id: int,
            *,
            direct: dict[int, set[int]],
            tree: dict[int | None, list[int]],
        ) -> set[int]:
            courses = set(direct.get(folder_id, set()))
            for child_id in tree.get(folder_id, []):
                courses |= subtree_courses(child_id, direct=direct, tree=tree)
            return courses

        for folder in folders:
            folder_id = int(folder["id"])
            courses = subtree_courses(folder_id, direct=folder_courses, tree=children)
            course_id = next(iter(courses)) if len(courses) == 1 else unsorted_id
            bind.execute(
                sa.text(
                    "UPDATE material_folders SET course_id = :course_id WHERE id = :id"
                ),
                {"course_id": course_id, "id": folder_id},
            )
        for row in bind.execute(
            sa.text(
                "SELECT m.id, m.folder_id, m.course_id FROM materials m "
                "JOIN material_folders f ON f.id = m.folder_id "
                "WHERE m.profile_id = :profile_id AND f.course_id != m.course_id"
            ),
            {"profile_id": profile_id},
        ).mappings():
            bind.execute(
                sa.text("UPDATE materials SET folder_id = NULL WHERE id = :id"),
                {"id": int(row["id"])},
            )

    with op.batch_alter_table("material_folders") as batch_op:
        batch_op.alter_column("course_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_material_folders_profile_course_path", ["profile_id", "course_id", "path"]
        )
        batch_op.create_index("ix_material_folders_course_id", ["course_id"])
    with op.batch_alter_table("material_sources") as batch_op:
        batch_op.alter_column("course_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("materials") as batch_op:
        batch_op.alter_column("course_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    unsorted_ids = list(
        bind.execute(
            sa.text("SELECT id FROM courses WHERE title = :title"), {"title": UNSORTED_TITLE}
        ).scalars()
    )
    for course_id in unsorted_ids:
        bind.execute(
            sa.text("UPDATE materials SET course_id = NULL WHERE course_id = :course_id"),
            {"course_id": course_id},
        )
        bind.execute(
            sa.text("UPDATE material_sources SET course_id = NULL WHERE course_id = :course_id"),
            {"course_id": course_id},
        )
        bind.execute(
            sa.text("DELETE FROM material_folders WHERE course_id = :course_id"),
            {"course_id": course_id},
        )
        bind.execute(
            sa.text(
                "DELETE FROM courses WHERE id = :course_id "
                "AND NOT EXISTS (SELECT 1 FROM materials WHERE course_id = :course_id)"
            ),
            {"course_id": course_id},
        )
    with op.batch_alter_table("materials") as batch_op:
        batch_op.alter_column("course_id", existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table("material_sources") as batch_op:
        batch_op.alter_column("course_id", existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table("material_folders") as batch_op:
        batch_op.drop_index("ix_material_folders_course_id")
        batch_op.drop_constraint("uq_material_folders_profile_course_path", type_="unique")
        batch_op.drop_column("course_id")
    op.create_index(
        "uq_material_folders_profile_path", "material_folders", ["profile_id", "path"], unique=True
    )
    op.create_table(
        "section_materials",
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("extraction_id", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("auto_assigned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["extraction_id"], ["extractions.id"]),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"]),
        sa.PrimaryKeyConstraint("section_id", "material_id"),
    )
    bind.execute(
        sa.text(
            "INSERT INTO section_materials "
            "(section_id, material_id, extraction_id, rationale, auto_assigned, confidence) "
            "SELECT owner_id, material_id, extraction_id, rationale, auto_assigned, confidence "
            "FROM material_links WHERE owner_type = 'section'"
        )
    )
    op.drop_index("ix_material_links_owner", table_name="material_links")
    op.drop_index("ix_material_links_material_id", table_name="material_links")
    op.drop_table("material_links")
