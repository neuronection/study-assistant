"""phase 9f: study content requires a course (ADR-040)

Revision ID: 0020_course_required
Revises: 0019_tree_nodes
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_course_required"
down_revision: str | None = "0019_tree_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNSORTED_TITLE = "Unsorted"

TABLES = ("notes", "activities", "exercises", "flashcards")


def _unsorted_course_id(bind: sa.Connection, profile_id: int) -> int:
    existing = bind.execute(
        sa.text(
            "SELECT id FROM courses WHERE profile_id = :profile_id AND title = :title"
        ),
        {"profile_id": profile_id, "title": UNSORTED_TITLE},
    ).scalar()
    if existing is not None:
        return int(existing)
    return int(
        bind.execute(
            sa.text(
                "INSERT INTO courses (profile_id, title, description, created_at, updated_at) "
                "VALUES (:profile_id, :title, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
                "RETURNING id"
            ),
            {"profile_id": profile_id, "title": UNSORTED_TITLE},
        ).scalar_one()
    )


def _root_node_id(bind: sa.Connection, course_id: int) -> int:
    existing = bind.execute(
        sa.text("SELECT id FROM tree_nodes WHERE course_id = :cid AND is_root = 1"),
        {"cid": course_id},
    ).scalar()
    if existing is not None:
        return int(existing)
    node_id = int(
        bind.execute(
            sa.text(
                "INSERT INTO tree_nodes (course_id, parent_id, title, order_idx, depth, "
                "path, sort_path, is_root, created_at) VALUES ("
                ":cid, NULL, :title, 0, 0, '/', '/', 1, CURRENT_TIMESTAMP) RETURNING id"
            ),
            {"cid": course_id, "title": UNSORTED_TITLE},
        ).scalar_one()
    )
    bind.execute(
        sa.text("UPDATE tree_nodes SET path = :p WHERE id = :id"),
        {"p": f"/{node_id}/", "id": node_id},
    )
    return node_id


def upgrade() -> None:
    bind = op.get_bind()
    profile_ids = list(bind.execute(sa.text("SELECT id FROM profiles")).scalars())
    for profile_id in profile_ids:
        orphans: dict[str, int] = {}
        for table in TABLES:
            count = bind.execute(
                sa.text(
                    f"SELECT COUNT(*) FROM {table} "
                    "WHERE profile_id = :pid AND course_id IS NULL"
                ),
                {"pid": profile_id},
            ).scalar()
            if count:
                orphans[table] = int(count)
        if not orphans:
            continue
        course_id = _unsorted_course_id(bind, profile_id)
        root_id = _root_node_id(bind, course_id)
        for table in orphans:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET course_id = :cid, node_id = :nid "
                    "WHERE profile_id = :pid AND course_id IS NULL"
                ),
                {"cid": course_id, "nid": root_id, "pid": profile_id},
            )
    for table in TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "course_id", existing_type=sa.Integer(), nullable=False
            )


def downgrade() -> None:
    raise NotImplementedError(
        "0020 makes study content course-required; downgrade is not supported"
    )
