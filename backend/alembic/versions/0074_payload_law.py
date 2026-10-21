"""payload_law — typed state out of JSON, versioned content documents (plan 81 D, ADR-200)

Known-shape state leaves JSON:

* `chat_proposals` gains the uniform, queryable card state as columns
  (`target_kind`, `target_name`, `target_node_id`, `target_node_path`,
  `original_md`) and its ordered anchored edits move to
  `chat_proposal_anchors`; the per-action instruction document stays JSON in
  `chat_proposals.payload` behind `payload_schema_version`.
* `chat_sessions.quiz_pending` becomes the one-row `chat_quiz_pendings`
  table (grading state included).
* `material_drawings.view` / `note_drawings.view` become
  `view_x`/`view_y`/`view_width`/`view_height` columns.

Canonical content documents keep their JSON shape and gain a
`<column>_schema_version` sibling validated at the write boundary:
`notes.body`, `note_versions.body`, `chat_messages.blocks`,
`extractions.blocks`, drawing `strokes`/`ocr_blocks`.

Data moves run in Python (dialect-agnostic JSON handling) before the old
columns are dropped. `downgrade()` restores the previous columns, their
documents and the proposal payload shape — a real round-trip, not a no-op.

Every step is guarded because 0073 rebuilds the identity domain from the
*current* model metadata: on a fresh chain the new shape already exists when
this revision runs (nothing to change), while a database that sat at 0073
before this model change still carries the old columns and is migrated.

Revision ID: 0074_payload_law
Revises: 0073_uuid_identity
Create Date: 2026-10-21
"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "0074_payload_law"
down_revision: str | None = "0073_uuid_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.Uuid(as_uuid=False)

_DOCUMENT_VERSION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("chat_messages", "blocks_schema_version"),
    ("extractions", "blocks_schema_version"),
    ("material_drawings", "ocr_blocks_schema_version"),
    ("material_drawings", "strokes_schema_version"),
    ("note_drawings", "ocr_blocks_schema_version"),
    ("note_drawings", "strokes_schema_version"),
    ("note_versions", "body_schema_version"),
    ("notes", "body_schema_version"),
)

_PROPOSAL_COLUMNS: tuple[Any, ...] = (
    sa.Column("target_kind", sa.String(20), nullable=True),
    sa.Column("target_name", sa.String(300), nullable=True),
    sa.Column(
        "target_node_id",
        _UUID,
        sa.ForeignKey("tree_nodes.id", ondelete="SET NULL"),
        nullable=True,
    ),
    sa.Column("target_node_path", sa.JSON(), nullable=True),
    sa.Column("original_md", sa.Text(), nullable=True),
    sa.Column("payload_schema_version", sa.Integer(), nullable=False, server_default=text("1")),
    sa.Column("result_schema_version", sa.Integer(), nullable=False, server_default=text("1")),
)

_VIEW_COLUMNS: tuple[Any, ...] = (
    sa.Column("view_x", sa.Float(), nullable=True),
    sa.Column("view_y", sa.Float(), nullable=True),
    sa.Column("view_width", sa.Float(), nullable=True),
    sa.Column("view_height", sa.Float(), nullable=True),
)


def _payload_document(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
        except ValueError:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _loads(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except ValueError:
            return None
    return None


def _split_proposals(bind: sa.Connection) -> None:
    rows = bind.execute(text("SELECT id, payload FROM chat_proposals")).mappings().all()
    node_ids = {
        str(value) for value in bind.execute(text("SELECT id FROM tree_nodes")).scalars().all()
    }
    anchors: list[dict[str, Any]] = []
    for row in rows:
        document = _payload_document(row["payload"])
        target_kind = document.pop("target_kind", None)
        target_name = document.pop("target_name", None)
        target_node_id = document.pop("target_node_id", None)
        target_node_path = document.pop("target_node_path", None)
        original_md = document.pop("original_md", None)
        text_edits = document.pop("text_edits", None)
        node_id = str(target_node_id) if target_node_id in node_ids else None
        if node_id is None:
            target_node_path = None
        bind.execute(
            text(
                "UPDATE chat_proposals SET target_kind = :target_kind, "
                "target_name = :target_name, target_node_id = :target_node_id, "
                "target_node_path = :target_node_path, original_md = :original_md, "
                "payload = :payload WHERE id = :id"
            ).bindparams(
                sa.bindparam("target_node_path", type_=sa.JSON()),
                sa.bindparam("payload", type_=sa.JSON()),
            ),
            {
                "target_kind": str(target_kind) if isinstance(target_kind, str) else None,
                "target_name": str(target_name) if isinstance(target_name, str) else None,
                "target_node_id": node_id,
                "target_node_path": target_node_path
                if isinstance(target_node_path, list)
                else None,
                "original_md": str(original_md) if isinstance(original_md, str) else None,
                "payload": document,
                "id": row["id"],
            },
        )
        if isinstance(text_edits, list):
            for position, edit in enumerate(text_edits):
                if not isinstance(edit, dict):
                    continue
                op_value = edit.get("op")
                if op_value not in ("replace", "append", "prepend"):
                    continue
                find_text = edit.get("find")
                anchor_text = edit.get("text", "")
                anchors.append(
                    {
                        "proposal_id": row["id"],
                        "position": position,
                        "op": op_value,
                        "find_text": find_text if isinstance(find_text, str) else None,
                        "text": anchor_text if isinstance(anchor_text, str) else "",
                    }
                )
    if anchors:
        bind.execute(
            text(
                "INSERT INTO chat_proposal_anchors "
                "(proposal_id, position, op, find_text, text) VALUES "
                "(:proposal_id, :position, :op, :find_text, :text)"
            ),
            anchors,
        )


def _merge_proposals(bind: sa.Connection) -> None:
    rows = (
        bind.execute(
            text(
                "SELECT id, payload, target_kind, target_name, target_node_id, "
                "target_node_path, original_md FROM chat_proposals"
            )
        )
        .mappings()
        .all()
    )
    anchor_rows = (
        bind.execute(
            text(
                "SELECT proposal_id, position, op, find_text, text "
                "FROM chat_proposal_anchors ORDER BY proposal_id, position"
            )
        )
        .mappings()
        .all()
    )
    by_proposal: dict[str, list[dict[str, Any]]] = {}
    for anchor in anchor_rows:
        by_proposal.setdefault(str(anchor["proposal_id"]), []).append(
            {
                "op": anchor["op"],
                "find": anchor["find_text"],
                "text": anchor["text"],
            }
        )
    for row in rows:
        document = _payload_document(row["payload"])
        document["original_md"] = row["original_md"]
        document["target_kind"] = row["target_kind"]
        document["target_name"] = row["target_name"]
        document["target_node_id"] = row["target_node_id"]
        document["target_node_path"] = _loads(row["target_node_path"])
        document["text_edits"] = by_proposal.get(str(row["id"]), [])
        bind.execute(
            text("UPDATE chat_proposals SET payload = :payload WHERE id = :id").bindparams(
                sa.bindparam("payload", type_=sa.JSON())
            ),
            {"payload": document, "id": row["id"]},
        )


def _move_quiz_pending(bind: sa.Connection) -> None:
    rows = (
        bind.execute(text("SELECT id, quiz_pending, created_at FROM chat_sessions"))
        .mappings()
        .all()
    )
    payloads: list[dict[str, Any]] = []
    for row in rows:
        pending = _loads(row["quiz_pending"])
        if not isinstance(pending, dict) or not pending.get("question"):
            continue
        choices = pending.get("choices")
        accept = pending.get("accept")
        verdict = pending.get("verdict")
        payloads.append(
            {
                "session_id": row["id"],
                "question": str(pending["question"]),
                "choices": [str(choice) for choice in choices]
                if isinstance(choices, list)
                else None,
                "expected_index": pending.get("expected_index")
                if isinstance(pending.get("expected_index"), int)
                else None,
                "expected_latex": pending.get("expected_latex")
                if isinstance(pending.get("expected_latex"), str)
                else None,
                "expected_text": pending.get("expected_text")
                if isinstance(pending.get("expected_text"), str)
                else None,
                "accept": [str(entry) for entry in accept] if isinstance(accept, list) else None,
                "awaiting_answer": bool(pending.get("awaiting_answer")),
                "verdict": verdict if verdict in ("correct", "incorrect") else None,
                "verdict_detail": pending.get("verdict_detail")
                if isinstance(pending.get("verdict_detail"), str)
                else None,
                "student_answer": pending.get("student_answer")
                if isinstance(pending.get("student_answer"), str)
                else None,
                "created_at": row["created_at"],
            }
        )
    if payloads:
        bind.execute(
            text(
                "INSERT INTO chat_quiz_pendings "
                "(session_id, question, choices, expected_index, expected_latex, "
                "expected_text, accept, awaiting_answer, verdict, verdict_detail, "
                "student_answer, created_at) VALUES "
                "(:session_id, :question, :choices, :expected_index, :expected_latex, "
                ":expected_text, :accept, :awaiting_answer, :verdict, :verdict_detail, "
                ":student_answer, :created_at)"
            ).bindparams(
                sa.bindparam("choices", type_=sa.JSON()),
                sa.bindparam("accept", type_=sa.JSON()),
            ),
            payloads,
        )


def _restore_quiz_pending(bind: sa.Connection) -> None:
    rows = (
        bind.execute(
            text(
                "SELECT session_id, question, choices, expected_index, expected_latex, "
                "expected_text, accept, awaiting_answer, verdict, verdict_detail, "
                "student_answer FROM chat_quiz_pendings"
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        pending: dict[str, Any] = {"question": row["question"]}
        choices = _loads(row["choices"])
        if isinstance(choices, list):
            pending["choices"] = choices
        if row["expected_index"] is not None:
            pending["expected_index"] = row["expected_index"]
        if row["expected_latex"]:
            pending["expected_latex"] = row["expected_latex"]
        if row["expected_text"]:
            pending["expected_text"] = row["expected_text"]
        accept = _loads(row["accept"])
        if isinstance(accept, list):
            pending["accept"] = accept
        pending["awaiting_answer"] = bool(row["awaiting_answer"])
        if row["verdict"] is not None:
            pending["verdict"] = row["verdict"]
            pending["verdict_detail"] = row["verdict_detail"]
            pending["student_answer"] = row["student_answer"]
        bind.execute(
            text("UPDATE chat_sessions SET quiz_pending = :pending WHERE id = :id").bindparams(
                sa.bindparam("pending", type_=sa.JSON())
            ),
            {"pending": pending, "id": row["session_id"]},
        )


def _move_views(bind: sa.Connection, table: str) -> None:
    if not _has_column(bind, table, "view"):
        return
    rows = bind.execute(text(f"SELECT id, view FROM {table}")).mappings().all()
    for row in rows:
        view = _loads(row["view"])
        if not isinstance(view, dict):
            continue
        bind.execute(
            text(
                f"UPDATE {table} SET view_x = :x, view_y = :y, "
                "view_width = :width, view_height = :height WHERE id = :id"
            ),
            {
                "x": _number(view.get("x")),
                "y": _number(view.get("y")),
                "width": _number(view.get("width")),
                "height": _number(view.get("height")),
                "id": row["id"],
            },
        )


def _restore_views(bind: sa.Connection, table: str) -> None:
    if not _has_column(bind, table, "view_x"):
        return
    rows = (
        bind.execute(
            text(
                f"SELECT id, view_x, view_y, view_width, view_height FROM {table} "
                "WHERE view_x IS NOT NULL"
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        view = {
            "x": row["view_x"],
            "y": row["view_y"],
            "width": row["view_width"],
            "height": row["view_height"],
        }
        bind.execute(
            text(f"UPDATE {table} SET view = :view WHERE id = :id").bindparams(
                sa.bindparam("view", type_=sa.JSON())
            ),
            {"view": view, "id": row["id"]},
        )


def _has_table(bind: sa.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _has_column(bind: sa.Connection, table: str, column: str) -> bool:
    if not _has_table(bind, table):
        return False
    return column in {str(item["name"]) for item in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "chat_proposals", "target_kind"):
        with op.batch_alter_table("chat_proposals", recreate="always") as batch:
            for column in _PROPOSAL_COLUMNS:
                batch.add_column(column)
            batch.create_check_constraint(
                "target_kind_allowed",
                "target_kind IS NULL OR target_kind IN ('note', 'material', 'concept', 'link')",
            )

    if not _has_table(bind, "chat_proposal_anchors"):
        op.create_table(
            "chat_proposal_anchors",
            sa.Column(
                "proposal_id",
                _UUID,
                sa.ForeignKey("chat_proposals.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("position", sa.Integer(), primary_key=True),
            sa.Column("op", sa.String(10), nullable=False),
            sa.Column("find_text", sa.Text(), nullable=True),
            sa.Column("text", sa.Text(), nullable=False, server_default=""),
            sa.CheckConstraint(
                "op IN ('replace', 'append', 'prepend')",
                name="ck_chat_proposal_anchors_op_allowed",
            ),
        )
        op.create_index(
            "ix_chat_proposal_anchors_proposal",
            "chat_proposal_anchors",
            ["proposal_id", "position"],
        )

    if not _has_table(bind, "chat_quiz_pendings"):
        op.create_table(
            "chat_quiz_pendings",
            sa.Column(
                "session_id",
                _UUID,
                sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("choices", sa.JSON(), nullable=True),
            sa.Column("expected_index", sa.Integer(), nullable=True),
            sa.Column("expected_latex", sa.String(500), nullable=True),
            sa.Column("expected_text", sa.String(500), nullable=True),
            sa.Column("accept", sa.JSON(), nullable=True),
            sa.Column("awaiting_answer", sa.Boolean(), nullable=False, server_default=text("0")),
            sa.Column("verdict", sa.String(20), nullable=True),
            sa.Column("verdict_detail", sa.String(500), nullable=True),
            sa.Column("student_answer", sa.String(1000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "verdict IS NULL OR verdict IN ('correct', 'incorrect')",
                name="ck_chat_quiz_pendings_verdict_allowed",
            ),
        )

    for table in ("material_drawings", "note_drawings"):
        for column in _VIEW_COLUMNS:
            if not _has_column(bind, table, column.name):
                op.add_column(table, column)

    for table, column in _DOCUMENT_VERSION_COLUMNS:
        if not _has_column(bind, table, column):
            op.add_column(
                table,
                sa.Column(column, sa.Integer(), nullable=False, server_default=text("1")),
            )

    if _has_column(bind, "chat_sessions", "quiz_pending"):
        _move_quiz_pending(bind)
        op.drop_column("chat_sessions", "quiz_pending")
    if _has_column(bind, "chat_proposals", "original_md"):
        _split_proposals(bind)
    for table in ("material_drawings", "note_drawings"):
        if _has_column(bind, table, "view"):
            _move_views(bind, table)
            op.drop_column(table, "view")


def downgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "chat_sessions", "quiz_pending"):
        op.add_column("chat_sessions", sa.Column("quiz_pending", sa.JSON(), nullable=True))
    for table in ("material_drawings", "note_drawings"):
        if not _has_column(bind, table, "view"):
            op.add_column(table, sa.Column("view", sa.JSON(), nullable=True))

    if _has_table(bind, "chat_quiz_pendings"):
        _restore_quiz_pending(bind)
    for table in ("material_drawings", "note_drawings"):
        _restore_views(bind, table)
    if _has_table(bind, "chat_proposal_anchors"):
        _merge_proposals(bind)

    if _has_table(bind, "chat_quiz_pendings"):
        op.drop_table("chat_quiz_pendings")
    if _has_table(bind, "chat_proposal_anchors"):
        op.drop_index("ix_chat_proposal_anchors_proposal", table_name="chat_proposal_anchors")
        op.drop_table("chat_proposal_anchors")

    if _has_column(bind, "chat_proposals", "target_kind"):
        with op.batch_alter_table("chat_proposals", recreate="always") as batch:
            batch.drop_constraint("target_kind_allowed", type_="check")
            for column in reversed(_PROPOSAL_COLUMNS):
                batch.drop_column(column.name)

    for table, column in reversed(_DOCUMENT_VERSION_COLUMNS):
        if _has_column(bind, table, column):
            op.drop_column(table, column)

    for table in ("material_drawings", "note_drawings"):
        for column in reversed(_VIEW_COLUMNS):
            if _has_column(bind, table, column.name):
                op.drop_column(table, column.name)
