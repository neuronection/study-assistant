"""Plan 52 T5c — bounded live indexing progress on ``jobs``.

Adds the nullable ``progress_detail`` document next to ``progress``/``stage``.
Vector handlers write a bounded counters object with the existing per-document
progress UPDATE, so a run shows processed/total documents and chunks,
embedded/skipped/failed and tokens instead of only a percentage. The column is
nullable: every other job family keeps its current progress semantics, and the
detail is pruned when the final ``result`` commits (the result stays
authoritative).

No table, index or backfill: existing rows read as ``NULL`` (no live detail).
Downgrade drops the column; the detail is live telemetry, never audit data.

Revision ID: 0019_job_progress_detail
Revises: 0018_vector_record_token_windows
Create Date: 2026-11-05
"""

from typing import Literal

import sqlalchemy as sa

from alembic import op

revision = "0019_job_progress_detail"
down_revision = "0018_vector_record_token_windows"
branch_labels = None
depends_on = None


def _recreate_mode() -> Literal["auto", "always"]:
    """SQLite copies the table; PostgreSQL alters it in place."""
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("progress_detail", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs", recreate=_recreate_mode()) as batch:
        batch.drop_column("progress_detail")
