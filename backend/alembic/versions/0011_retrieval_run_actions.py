"""retrieval action runtime: idempotency, single-run lock and heartbeat

Plan 51 Q3b. Adds the runtime handles the action API needs on ``jobs``:

* ``idempotency_key`` — a client request-replay key (8-120 chars), unique per
  ``type`` while the row is queued/running. Terminal rows release the index
  slot; the service also replays terminal rows inside the contract's 24 hour
  window before enqueueing anything new.
* ``lock_key`` — the single-active-run lock (``vector_space:<space_id>``),
  unique while queued/running. A terminal row releases the slot, so cancel,
  retry and the stale-heartbeat reaper never block forever.
* ``heartbeat_at`` — written by the job runner's progress checkpoints and read
  by the bounded stale reaper (15 minute window from the family contract).
* ``cancel_requested`` — the honest "cancellation asked for, worker has not
  observed it yet" flag the run view renders.

Both unique indexes are partial over the two active statuses only. The
generic job enqueue path is untouched: keys are null for every other job
family, so the indexes never apply to them.

Downgrade drops both indexes and the four columns; run history keeps its
status/result.

Revision ID: 0011_retrieval_run_actions
Revises: 0010_retrieval_ops
Create Date: 2026-11-04
"""

from typing import Literal

import sqlalchemy as sa

from alembic import op

revision = "0011_retrieval_run_actions"
down_revision = "0010_retrieval_ops"
branch_labels = None
depends_on = None

_ACTIVE = "status IN ('queued', 'running')"
_IDEMPOTENCY_WHERE = sa.text(f"idempotency_key IS NOT NULL AND {_ACTIVE}")
_LOCK_KEY_WHERE = sa.text(f"lock_key IS NOT NULL AND {_ACTIVE}")


def _recreate_mode() -> Literal["always", "auto", "never"]:
    """SQLite copies the table; PostgreSQL alters it in place.

    A PostgreSQL ``recreate="always"`` copy drops the primary key and fails
    while dependent foreign keys still reference it.
    """
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("idempotency_key", sa.String(length=120), nullable=True))
    op.add_column("jobs", sa.Column("lock_key", sa.String(length=120), nullable=True))
    op.add_column("jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_index(
        "uq_jobs_idempotency_active",
        "jobs",
        ["type", "idempotency_key"],
        unique=True,
        postgresql_where=_IDEMPOTENCY_WHERE,
        sqlite_where=_IDEMPOTENCY_WHERE,
    )
    op.create_index(
        "uq_jobs_lock_key_active",
        "jobs",
        ["lock_key"],
        unique=True,
        postgresql_where=_LOCK_KEY_WHERE,
        sqlite_where=_LOCK_KEY_WHERE,
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_lock_key_active", table_name="jobs")
    op.drop_index("uq_jobs_idempotency_active", table_name="jobs")
    with op.batch_alter_table("jobs", recreate=_recreate_mode()) as batch:
        batch.drop_column("cancel_requested")
        batch.drop_column("heartbeat_at")
        batch.drop_column("lock_key")
        batch.drop_column("idempotency_key")
