import sqlalchemy as sa

from alembic import op

revision: str = "0059_study_sessions"
down_revision: str | None = "0058_source_mirror_subdirs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "profile_id", sa.Integer(), sa.ForeignKey("profiles.id"), nullable=False
        ),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("entity_ref", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_beat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_study_sessions_profile_id", "study_sessions", ["profile_id"]
    )
    op.create_index(
        "ix_study_sessions_course_id", "study_sessions", ["course_id"]
    )
    op.create_index(
        "ix_study_sessions_profile_started",
        "study_sessions",
        ["profile_id", "started_at"],
    )
    op.add_column(
        "daily_rollups",
        sa.Column(
            "study_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "study_goals",
        sa.Column(
            "unit",
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'answers'"),
        ),
    )
    op.add_column(
        "study_goals",
        sa.Column(
            "minutes_per_day",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
    )


def downgrade() -> None:
    op.drop_column("study_goals", "minutes_per_day")
    op.drop_column("study_goals", "unit")
    op.drop_column("daily_rollups", "study_seconds")
    op.drop_index(
        "ix_study_sessions_profile_started", table_name="study_sessions"
    )
    op.drop_index("ix_study_sessions_course_id", table_name="study_sessions")
    op.drop_index("ix_study_sessions_profile_id", table_name="study_sessions")
    op.drop_table("study_sessions")
