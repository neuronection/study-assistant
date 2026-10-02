"""empty baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-18

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Alembic's auto-created alembic_version.version_num is VARCHAR(32),
        # but several revision IDs in this chain exceed 32 chars (SQLite
        # does not enforce VARCHAR lengths; PostgreSQL does). The version
        # table exists by the time the first migration runs, so widen it
        # before any long name can be stamped.
        op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")


def downgrade() -> None:
    pass
