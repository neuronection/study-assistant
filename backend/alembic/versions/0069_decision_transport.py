import sqlalchemy as sa

from alembic import op

revision: str = "0069_decision_transport"
down_revision: str | None = "0068_rename_legacy_ca_schemes"
branch_labels = None
depends_on = None

DECISION_SLOTS = (
    "decision:tool-dispatch",
    "decision:boolean-gate",
    "decision:choice",
    "decision:score",
)


def upgrade() -> None:
    op.add_column(
        "models",
        sa.Column("decision_transport", sa.String(length=20), nullable=True),
    )
    bind = op.get_bind()
    for slot in DECISION_SLOTS:
        bind.execute(
            sa.text(
                "INSERT INTO default_task_assignments (requires, model_id, fallback_model_id) "
                "SELECT :slot, NULL, NULL WHERE NOT EXISTS ("
                "SELECT 1 FROM default_task_assignments WHERE requires = :slot)"
            ),
            {"slot": slot},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM default_task_assignments WHERE requires IN "
            "('decision:tool-dispatch', 'decision:boolean-gate', "
            "'decision:choice', 'decision:score')"
        )
    )
    op.drop_column("models", "decision_transport")
