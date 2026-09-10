"""chat message branches (parent tree + active-path pointers)

Revision ID: 0044_chat_branches
Revises: 0043_course_default_task_assignments
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0044_chat_branches"
down_revision: str | None = "0043_course_default_task_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("active_root_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column("parent_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_chat_messages_parent_id", "chat_messages", ["parent_id"]
    )
    op.add_column(
        "chat_messages",
        sa.Column("active_child_id", sa.Integer(), nullable=True),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, session_id FROM chat_messages ORDER BY session_id, id")
    ).fetchall()
    previous: tuple[int, int] | None = None
    for row in rows:
        message_id, chat_session_id = int(row.id), int(row.session_id)
        parent: int | None = None
        if previous is not None and previous[0] == chat_session_id:
            parent = previous[1]
            bind.execute(
                sa.text(
                    "UPDATE chat_messages SET active_child_id = :child WHERE id = :prev"
                ),
                {"child": message_id, "prev": parent},
            )
        else:
            bind.execute(
                sa.text(
                    "UPDATE chat_sessions SET active_root_id = :root WHERE id = :sid"
                ),
                {"root": message_id, "sid": chat_session_id},
            )
        bind.execute(
            sa.text("UPDATE chat_messages SET parent_id = :parent WHERE id = :mid"),
            {"parent": parent, "mid": message_id},
        )
        previous = (chat_session_id, message_id)


def downgrade() -> None:
    op.drop_column("chat_messages", "active_child_id")
    op.drop_index("ix_chat_messages_parent_id", table_name="chat_messages")
    op.drop_column("chat_messages", "parent_id")
    op.drop_column("chat_sessions", "active_root_id")
