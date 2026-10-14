import sqlalchemy as sa

from alembic import op

revision: str = "0070_single_slot_capability_defaults"
down_revision: str | None = "0069_decision_transport"
branch_labels = None
depends_on = None

# Capability defaults: the `decision` default row beside the five
# capability rows — everything except the decision kind overrides.
DECISION_KIND_SLOTS = (
    "decision:tool-dispatch",
    "decision:boolean-gate",
    "decision:choice",
    "decision:score",
)


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    return (
        bind.execute(
            sa.text("SELECT 1 FROM pragma_table_info(:table) WHERE name = :column"),
            {"table": table, "column": column},
        ).first()
        is not None
    )


def upgrade() -> None:
    # ADR-0037: capability defaults (global + per-course) are single-slot.
    # No-backwards-compatibility (owner directive, plan-30): the fallback
    # values on capability rows are retired outright — only decision kind
    # override rows keep theirs verbatim (the column stays: it is theirs).
    kind_list = ", ".join(f"'{slot}'" for slot in DECISION_KIND_SLOTS)
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE default_task_assignments SET fallback_model_id = NULL "
            f"WHERE requires NOT IN ({kind_list})"
        )
    )

    # The course-default table's fallback corner is retired. The column
    # exists on DBs migrated through the pre-0037 ORM (0066 rebuilt the
    # table metadata-driven); on a fresh full rebuild under the new ORM it
    # was never created — dropping only when present.
    if _column_exists(bind, "course_default_task_assignments", "fallback_model_id"):
        op.drop_column("course_default_task_assignments", "fallback_model_id")


def downgrade() -> None:
    if not _column_exists(op.get_bind(), "course_default_task_assignments", "fallback_model_id"):
        op.add_column(
            "course_default_task_assignments",
            sa.Column("fallback_model_id", sa.Integer(), nullable=True),
        )
