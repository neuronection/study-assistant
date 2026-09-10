"""phase 9a: unified node tree (ADR-039)

Revision ID: 0019_tree_nodes
Revises: 0018_concepts
Create Date: 2026-08-19

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0019_tree_nodes"
down_revision: str | None = "0018_concepts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _seg(order_idx: int) -> str:
    return f"{(order_idx or 0):06d}/"


def _recompute_paths(bind: sa.Connection) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT id, parent_id, order_idx, is_root FROM tree_nodes ORDER BY depth, id"
        )
    ).all()
    paths: dict[int, tuple[str, str]] = {}
    for node_id, parent_id, order_idx, is_root in rows:
        if is_root:
            paths[node_id] = (f"/{node_id}/", "/")
            continue
        parent_path, parent_sort = paths.get(parent_id or -1, ("/", "/"))
        paths[node_id] = (f"{parent_path}{node_id}/", f"{parent_sort}{_seg(order_idx)}")
    if not paths:
        return
    bind.execute(
        sa.text("UPDATE tree_nodes SET path = :path, sort_path = :sort WHERE id = :id"),
        [
            {"path": value[0], "sort": value[1], "id": node_id}
            for node_id, value in paths.items()
        ],
    )


def _insert_node(
    bind: sa.Connection,
    *,
    course_id: int,
    parent_id: int | None,
    title: str,
    summary: str | None,
    objectives: str | None,
    order_idx: int,
    depth: int,
    is_root: bool = False,
) -> int:
    return int(
        bind.execute(
            sa.text(
                "INSERT INTO tree_nodes (course_id, parent_id, title, summary, objectives, "
                "order_idx, depth, path, sort_path, is_root, created_at) VALUES ("
                ":course_id, :parent_id, :title, :summary, :objectives, :order_idx, "
                ":depth, '/', '/', :is_root, CURRENT_TIMESTAMP) RETURNING id"
            ),
            {
                "course_id": course_id,
                "parent_id": parent_id,
                "title": title,
                "summary": summary,
                "objectives": objectives,
                "order_idx": order_idx,
                "depth": depth,
                "is_root": is_root,
            },
        ).scalar_one()
    )


def _add_placement(table: str, section_index: str | None) -> None:
    with op.batch_alter_table(table) as batch_op:
        batch_op.add_column(sa.Column("node_id", sa.Integer(), nullable=True))
    bind = op.get_bind()
    if table in ("activities", "exercises", "flashcards"):
        bind.execute(
            sa.text(
                f"UPDATE {table} SET node_id = ("
                " SELECT m.new_node_id FROM _section_map m WHERE m.old_id = section_id)"
                " WHERE section_id IS NOT NULL"
            )
        )
    if table == "notes":
        bind.execute(
            sa.text(
                "UPDATE notes SET node_id = ("
                " SELECT m.new_node_id FROM _section_map m WHERE m.old_id = notes.owner_id), "
                "owner_type = 'standalone', owner_id = NULL "
                "WHERE owner_type = 'section'"
            )
        )
    bind.execute(
        sa.text(
            f"UPDATE {table} SET node_id = ("
            " SELECT r.id FROM tree_nodes r"
            f" WHERE r.course_id = {table}.course_id AND r.is_root = 1)"
            " WHERE node_id IS NULL AND course_id IS NOT NULL"
        )
    )
    with op.batch_alter_table(table) as batch_op:
        if table in ("activities", "exercises", "flashcards"):
            if section_index:
                batch_op.drop_index(section_index)
            batch_op.drop_column("section_id")
        batch_op.create_foreign_key(
            f"fk_{table}_node", "tree_nodes", ["node_id", "course_id"], ["id", "course_id"]
        )
        batch_op.create_index(f"ix_{table}_node_id", ["node_id"])


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "tree_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("objectives", sa.JSON(), nullable=True),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("sort_path", sa.String(length=1000), nullable=False),
        sa.Column("is_root", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(
            ["parent_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name="fk_tree_nodes_parent_course",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "course_id", name="uq_tree_nodes_id_course"),
        sa.CheckConstraint("depth >= 0 AND depth <= 4", name="ck_tree_nodes_depth"),
    )
    op.create_index("ix_tree_nodes_course_id", "tree_nodes", ["course_id"])
    op.create_index("ix_tree_nodes_course_parent", "tree_nodes", ["course_id", "parent_id"])
    op.create_index(
        "uq_tree_nodes_root",
        "tree_nodes",
        ["course_id"],
        unique=True,
        sqlite_where=sa.text("is_root = 1"),
    )

    for course_id, title, description in bind.execute(
        sa.text("SELECT id, title, description FROM courses")
    ).all():
        _insert_node(
            bind,
            course_id=course_id,
            parent_id=None,
            title=title,
            summary=description,
            objectives=None,
            order_idx=0,
            depth=0,
            is_root=True,
        )

    bind.execute(
        sa.text(
            "CREATE TEMP TABLE _chapter_map (old_id INTEGER PRIMARY KEY, new_node_id INTEGER)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE TEMP TABLE _section_map (old_id INTEGER PRIMARY KEY, new_node_id INTEGER)"
        )
    )
    chapters: list[tuple[Any, ...]] = [tuple(row) for row in bind.execute(
        sa.text(
            "SELECT id, course_id, parent_id, title, summary, order_idx, created_at "
            "FROM chapters ORDER BY id"
        )
    ).all()]
    chapter_map: dict[int, int] = {}
    pending = list(chapters)
    while pending:
        progressed = False
        remaining: list[tuple[Any, ...]] = []
        for row in pending:
            chapter_id, course_id, parent_id, title, summary, order_idx, _created = row
            if parent_id is None:
                root_id = bind.execute(
                    sa.text(
                        "SELECT id FROM tree_nodes WHERE course_id = :cid AND is_root = 1"
                    ),
                    {"cid": course_id},
                ).scalar_one()
                node_id = _insert_node(
                    bind,
                    course_id=course_id,
                    parent_id=root_id,
                    title=title,
                    summary=summary,
                    objectives=None,
                    order_idx=order_idx * 1000,
                    depth=1,
                )
                chapter_map[chapter_id] = node_id
                progressed = True
            elif parent_id in chapter_map:
                parent_node = bind.execute(
                    sa.text(
                        "SELECT course_id, depth FROM tree_nodes WHERE id = :nid"
                    ),
                    {"nid": chapter_map[parent_id]},
                ).one()
                node_id = _insert_node(
                    bind,
                    course_id=parent_node.course_id,
                    parent_id=chapter_map[parent_id],
                    title=title,
                    summary=summary,
                    objectives=None,
                    order_idx=order_idx * 1000,
                    depth=parent_node.depth + 1,
                )
                chapter_map[chapter_id] = node_id
                progressed = True
            else:
                remaining.append(row)
        if not progressed:
            break
        pending = remaining
    for chapter_id, node_id in chapter_map.items():
        bind.execute(
            sa.text("INSERT INTO _chapter_map (old_id, new_node_id) VALUES (:o, :n)"),
            {"o": chapter_id, "n": node_id},
        )
    for section_id, chapter_id, title, objectives, summary, order_idx in bind.execute(
        sa.text(
            "SELECT id, chapter_id, title, objectives, summary, order_idx "
            "FROM sections ORDER BY chapter_id, order_idx, id"
        )
    ).all():
        mapped = bind.execute(
            sa.text(
                "SELECT tn.course_id, tn.depth FROM _chapter_map m "
                "JOIN tree_nodes tn ON tn.id = m.new_node_id WHERE m.old_id = :cid"
            ),
            {"cid": chapter_id},
        ).first()
        if mapped is None:
            continue
        node_id = _insert_node(
            bind,
            course_id=mapped.course_id,
            parent_id=chapter_map[chapter_id],
            title=title,
            summary=summary,
            objectives=objectives,
            order_idx=order_idx * 1000,
            depth=mapped.depth + 1,
        )
        bind.execute(
            sa.text("INSERT INTO _section_map (old_id, new_node_id) VALUES (:o, :n)"),
            {"o": section_id, "n": node_id},
        )
    _recompute_paths(bind)
    op.create_index("uq_tree_nodes_path", "tree_nodes", ["path"], unique=True)

    op.create_table(
        "material_links_new",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("extraction_id", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("auto_assigned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["extraction_id"], ["extractions.id"]),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "material_id"),
    )
    bind.execute(
        sa.text(
            "INSERT INTO material_links_new "
            "(course_id, node_id, material_id, extraction_id, rationale, "
            "auto_assigned, confidence, created_at) "
            "SELECT mat.course_id, "
            "CASE ml.owner_type "
            "  WHEN 'course' THEN (SELECT r.id FROM tree_nodes r "
            "    WHERE r.course_id = ml.owner_id AND r.is_root = 1) "
            "  WHEN 'chapter' THEN (SELECT m.new_node_id FROM _chapter_map m "
            "    WHERE m.old_id = ml.owner_id) "
            "  ELSE (SELECT m.new_node_id FROM _section_map m WHERE m.old_id = ml.owner_id) "
            "END, "
            "ml.material_id, ml.extraction_id, ml.rationale, ml.auto_assigned, "
            "ml.confidence, ml.created_at "
            "FROM material_links ml JOIN materials mat ON mat.id = ml.material_id"
        )
    )
    bind.execute(sa.text("DROP TABLE material_links"))
    bind.execute(sa.text("ALTER TABLE material_links_new RENAME TO material_links"))
    op.create_index("ix_material_links_material_id", "material_links", ["material_id"])
    op.create_index("ix_material_links_course_id", "material_links", ["course_id"])
    op.create_index("ix_material_links_node", "material_links", ["node_id"])

    op.create_table(
        "node_concepts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["tree_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "concept_id"),
    )
    op.create_index("ix_node_concepts_node_id", "node_concepts", ["node_id"])
    bind.execute(
        sa.text(
            "INSERT INTO node_concepts (node_id, concept_id, weight) "
            "SELECT m.new_node_id, sc.concept_id, sc.weight "
            "FROM section_concepts sc JOIN _section_map m ON m.old_id = sc.section_id"
        )
    )
    op.drop_table("section_concepts")

    _add_placement("activities", section_index="ix_activities_section_id")
    _add_placement("exercises", section_index="ix_exercises_section_id")
    _add_placement("flashcards", section_index=None)
    _add_placement("notes", section_index=None)
    _add_placement("chat_sessions", section_index=None)

    op.drop_table("sections")
    op.drop_table("chapters")

    bind.execute(sa.text("DROP TABLE _chapter_map"))
    bind.execute(sa.text("DROP TABLE _section_map"))


def downgrade() -> None:
    raise NotImplementedError(
        "0019 restructures chapters/sections into tree_nodes; downgrade is not supported"
    )
