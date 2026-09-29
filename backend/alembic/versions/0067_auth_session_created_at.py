"""auth_session_created_at — device-list timestamp (identity-auth §12)

Product-added column (identity-auth §5 allows additions):
`auth_sessions.created_at` so `GET /api/v1/me/sessions` can show when
each refresh family was created. Nullable — pre-existing rows carry no
timestamp and dev databases are recreated (greenfield posture).

Revision ID: 0067_auth_session_created_at
Revises: 0066_profile_identity
Create Date: 2026-09-25
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0067_auth_session_created_at"
down_revision: str | None = "0066_profile_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_sessions", "created_at")
