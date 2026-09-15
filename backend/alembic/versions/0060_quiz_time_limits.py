import sqlalchemy as sa

from alembic import op

revision: str = "0060_quiz_time_limits"
down_revision: str | None = "0059_study_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("time_limit_sec", sa.Integer(), nullable=True),
    )
    op.add_column(
        "attempts",
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attempts", "deadline_at")
    op.drop_column("activities", "time_limit_sec")
