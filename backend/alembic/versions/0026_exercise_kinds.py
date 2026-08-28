"""phase 18B: exercises gain kinds; flashcards fold in as card_* kinds (ADR-045)

Revision ID: 0026_exercise_kinds
Revises: 0025_material_provenance
Create Date: 2026-08-21

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_exercise_kinds"
down_revision: str | None = "0025_material_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CARD_KIND_MAP = {"basic": "card_basic", "cloze": "card_cloze", "reverse": "card_reverse"}

FSRS_DDL = """
CREATE TABLE fsrs_states_new (
    id INTEGER NOT NULL PRIMARY KEY,
    card_id INTEGER NOT NULL,
    state VARCHAR(20) DEFAULT 'new' NOT NULL,
    stability FLOAT,
    difficulty FLOAT,
    reps INTEGER DEFAULT '0' NOT NULL,
    lapses INTEGER DEFAULT '0' NOT NULL,
    due_at DATETIME NOT NULL,
    last_review_at DATETIME,
    FOREIGN KEY(card_id) REFERENCES exercises (id)
)
"""

REVIEW_DDL = """
CREATE TABLE review_log_new (
    id INTEGER NOT NULL PRIMARY KEY,
    card_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    interval_days FLOAT NOT NULL,
    elapsed_days FLOAT NOT NULL,
    reviewed_at DATETIME NOT NULL,
    FOREIGN KEY(card_id) REFERENCES exercises (id)
)
"""


def _front_title(front_json: str) -> str:
    blocks = json.loads(front_json) if front_json else []
    parts = [str(block.get("md", "")) for block in blocks if block.get("md")]
    title = " ".join(part.strip() for part in parts if part.strip())
    return title[:300] if title else "Card"


def upgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=30), nullable=False, server_default="multi_step")
        )
        batch_op.add_column(sa.Column("deck_ref", sa.String(length=200), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, profile_id, course_id, node_id, kind, front, back, source, "
            "source_ref, created_at FROM flashcards ORDER BY id"
        )
    ).all()
    for row in rows:
        kind = CARD_KIND_MAP.get(row.kind, "card_basic")
        created_from = {"source": row.source, "source_ref": row.source_ref}
        new_id = bind.execute(
            sa.text(
                "INSERT INTO exercises (profile_id, course_id, node_id, title, kind, "
                "deck_ref, created_from, created_at) VALUES "
                "(:profile_id, :course_id, :node_id, :title, :kind, NULL, :created_from, "
                ":created_at) RETURNING id"
            ),
            {
                "profile_id": row.profile_id,
                "course_id": row.course_id,
                "node_id": row.node_id,
                "title": _front_title(row.front),
                "kind": kind,
                "created_from": json.dumps(created_from),
                "created_at": row.created_at,
            },
        ).scalar_one()
        bind.execute(
            sa.text(
                "INSERT INTO exercise_steps (exercise_id, order_idx, prompt, expected) "
                "VALUES (:exercise_id, 0, :prompt, :expected)"
            ),
            {
                "exercise_id": new_id,
                "prompt": row.front,
                "expected": json.dumps({"kind": kind, "back": json.loads(row.back)}),
            },
        )
        bind.execute(
            sa.text("UPDATE fsrs_states SET card_id = :new_id WHERE card_id = :old_id"),
            {"new_id": new_id, "old_id": row.id},
        )
        bind.execute(
            sa.text("UPDATE review_log SET card_id = :new_id WHERE card_id = :old_id"),
            {"new_id": new_id, "old_id": row.id},
        )

    bind.execute(sa.text("DROP TABLE IF EXISTS fsrs_states_new"))
    bind.execute(sa.text(FSRS_DDL))
    bind.execute(
        sa.text(
            "INSERT INTO fsrs_states_new (id, card_id, state, stability, difficulty, "
            "reps, lapses, due_at, last_review_at) "
            "SELECT id, card_id, state, stability, difficulty, reps, lapses, due_at, "
            "last_review_at FROM fsrs_states"
        )
    )
    bind.execute(sa.text("DROP TABLE fsrs_states"))
    bind.execute(sa.text("ALTER TABLE fsrs_states_new RENAME TO fsrs_states"))
    bind.execute(
        sa.text("CREATE UNIQUE INDEX ix_fsrs_states_card_id ON fsrs_states (card_id)")
    )
    bind.execute(
        sa.text("CREATE INDEX ix_fsrs_states_due_at ON fsrs_states (due_at)")
    )

    bind.execute(sa.text("DROP TABLE IF EXISTS review_log_new"))
    bind.execute(sa.text(REVIEW_DDL))
    bind.execute(
        sa.text(
            "INSERT INTO review_log_new (id, card_id, rating, interval_days, "
            "elapsed_days, reviewed_at) "
            "SELECT id, card_id, rating, interval_days, elapsed_days, reviewed_at "
            "FROM review_log"
        )
    )
    bind.execute(sa.text("DROP TABLE review_log"))
    bind.execute(sa.text("ALTER TABLE review_log_new RENAME TO review_log"))
    bind.execute(
        sa.text("CREATE INDEX ix_review_log_card_id ON review_log (card_id)")
    )

    op.drop_table("flashcards")


def downgrade() -> None:
    op.create_table(
        "flashcards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("front", sa.JSON(), nullable=False),
        sa.Column("back", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_ref", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT e.id, e.profile_id, e.course_id, e.node_id, e.kind, "
            "e.created_from, e.created_at, s.prompt, s.expected FROM exercises e "
            "JOIN exercise_steps s ON s.exercise_id = e.id AND s.order_idx = 0 "
            "WHERE e.kind LIKE 'card_%' ORDER BY e.id"
        )
    ).all()
    for row in rows:
        created_from = json.loads(row.created_from) if row.created_from else {}
        expected = json.loads(row.expected) if row.expected else {}
        bind.execute(
            sa.text(
                "INSERT INTO flashcards (id, profile_id, course_id, node_id, kind, "
                "front, back, source, source_ref, created_at) VALUES "
                "(:id, :profile_id, :course_id, :node_id, :kind, :front, :back, "
                ":source, :source_ref, :created_at)"
            ),
            {
                "id": row.id,
                "profile_id": row.profile_id,
                "course_id": row.course_id,
                "node_id": row.node_id,
                "kind": row.kind.removeprefix("card_"),
                "front": row.prompt,
                "back": json.dumps(expected.get("back", [])),
                "source": created_from.get("source", "note"),
                "source_ref": created_from.get("source_ref"),
                "created_at": row.created_at,
            },
        )
    bind.execute(sa.text("DROP TABLE IF EXISTS fsrs_states_new"))
    bind.execute(
        sa.text(
            "CREATE TABLE fsrs_states_new (id INTEGER NOT NULL PRIMARY KEY, "
            "card_id INTEGER NOT NULL, state VARCHAR(20) DEFAULT 'new' NOT NULL, "
            "stability FLOAT, difficulty FLOAT, reps INTEGER DEFAULT '0' NOT NULL, "
            "lapses INTEGER DEFAULT '0' NOT NULL, due_at DATETIME NOT NULL, "
            "last_review_at DATETIME, FOREIGN KEY(card_id) REFERENCES flashcards (id))"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO fsrs_states_new (id, card_id, state, stability, difficulty, "
            "reps, lapses, due_at, last_review_at) SELECT id, card_id, state, "
            "stability, difficulty, reps, lapses, due_at, last_review_at FROM fsrs_states"
        )
    )
    bind.execute(sa.text("DROP TABLE fsrs_states"))
    bind.execute(sa.text("ALTER TABLE fsrs_states_new RENAME TO fsrs_states"))
    bind.execute(
        sa.text("CREATE UNIQUE INDEX ix_fsrs_states_card_id ON fsrs_states (card_id)")
    )
    bind.execute(
        sa.text("CREATE INDEX ix_fsrs_states_due_at ON fsrs_states (due_at)")
    )

    bind.execute(sa.text("DROP TABLE IF EXISTS review_log_new"))
    bind.execute(
        sa.text(
            "CREATE TABLE review_log_new (id INTEGER NOT NULL PRIMARY KEY, "
            "card_id INTEGER NOT NULL, rating INTEGER NOT NULL, "
            "interval_days FLOAT NOT NULL, elapsed_days FLOAT NOT NULL, "
            "reviewed_at DATETIME NOT NULL, "
            "FOREIGN KEY(card_id) REFERENCES flashcards (id))"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO review_log_new (id, card_id, rating, interval_days, "
            "elapsed_days, reviewed_at) SELECT id, card_id, rating, interval_days, "
            "elapsed_days, reviewed_at FROM review_log"
        )
    )
    bind.execute(sa.text("DROP TABLE review_log"))
    bind.execute(sa.text("ALTER TABLE review_log_new RENAME TO review_log"))
    bind.execute(
        sa.text("CREATE INDEX ix_review_log_card_id ON review_log (card_id)")
    )
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_column("deck_ref")
        batch_op.drop_column("kind")
