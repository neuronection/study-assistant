"""AI cost provenance + price overrides (plan 58 P1).

- `ai_interactions`: integer `cost_micros` + provenance; `cost_usd` is
  backfilled once as `legacy`/`pre-contract`, then dropped.
- `models.cost_in/cost_out` become exact `ai_price_overrides` rows (preset
  key, or providerRef when the provider has no preset key), then the float
  columns are dropped.
- `task_assignments.params.monthly_cap_usd` becomes
  `monthly_cap_micros` (half-up), never a second stored field.

Revision ID: 0033_ai_cost_provenance
Revises: 0032_lecture_transcribe_job
Create Date: 2026-11-11
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "0033_ai_cost_provenance"
down_revision = "0032_lecture_transcribe_job"
branch_labels = None
depends_on = None


def _micros(value: float | None) -> int | None:
    if value is None:
        return None
    return int(Decimal(str(value)) * 1_000_000 + Decimal("0.5"))


def upgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table("ai_interactions") as batch:
        batch.add_column(sa.Column("cost_micros", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column(
                "usage_source", sa.String(length=20), nullable=False, server_default="unknown"
            )
        )
        batch.add_column(sa.Column("estimate_method", sa.String(length=40), nullable=True))
        batch.add_column(
            sa.Column(
                "price_source", sa.String(length=20), nullable=False, server_default="unknown"
            )
        )
        batch.add_column(sa.Column("price_version", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("model_external_id", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("provider_key", sa.String(length=40), nullable=True))

    with op.batch_alter_table("ai_interactions") as batch:
        batch.create_check_constraint(
            "usage_source_allowed",
            "usage_source IN ('provider', 'estimated', 'partial', 'unknown')",
        )
        batch.create_check_constraint(
            "price_source_allowed",
            "price_source IN ('user', 'builtin', 'local', 'legacy', 'unknown')",
        )

    op.create_table(
        "ai_price_overrides",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("provider_key", sa.String(length=40), nullable=True),
        sa.Column(
            "provider_ref",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("match", sa.String(length=10), nullable=False, server_default="exact"),
        sa.Column("input_micros_per_million", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_micros_per_million", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("metering", sa.String(length=20), nullable=False, server_default="tokens"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider_key",
            "provider_ref",
            "model",
            "match",
            name="uq_ai_price_overrides_scope",
        ),
        sa.CheckConstraint("match IN ('exact', 'prefix')", name="match_allowed"),
        sa.CheckConstraint(
            "metering IN ('tokens', 'input_only', 'output_only')",
            name="metering_allowed",
        ),
    )

    models = bind.execute(
        sa.text(
            """
            SELECT m.id, m.provider_id, m.external_id, m.cost_in, m.cost_out,
                   p.preset_key
              FROM models m JOIN providers p ON p.id = m.provider_id
             WHERE m.cost_in IS NOT NULL OR m.cost_out IS NOT NULL
            """
        )
    ).mappings()
    now = datetime.now(UTC)
    for row in models:
        cost_in = _micros(row["cost_in"])
        cost_out = _micros(row["cost_out"])
        if cost_in is None and cost_out is None:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO ai_price_overrides
                    (id, provider_key, provider_ref, model, match,
                     input_micros_per_million, output_micros_per_million,
                     metering, created_at, updated_at)
                VALUES
                    (:id, :provider_key, :provider_ref, :model, 'exact',
                     :input, :output, 'tokens', :created_at, :updated_at)
                """
            ),
            {
                "id": str(uuid4()),
                "provider_key": row["preset_key"],
                "provider_ref": None if row["preset_key"] else str(row["provider_id"]),
                "model": row["external_id"],
                "input": cost_in or 0,
                "output": cost_out or 0,
                "created_at": now,
                "updated_at": now,
            },
        )

    bind.execute(
        sa.text(
            """
            UPDATE ai_interactions
               SET cost_micros = CAST(ROUND(cost_usd * 1000000) AS BIGINT),
                   usage_source = 'unknown',
                   price_source = 'legacy',
                   price_version = 'pre-contract'
             WHERE cost_usd IS NOT NULL
            """
        )
    )

    for row in bind.execute(sa.text("SELECT task, params FROM task_assignments")).mappings():
        params = row["params"]
        if isinstance(params, str):
            params = json.loads(params)
        if not isinstance(params, dict) or "monthly_cap_usd" not in params:
            continue
        value = params.pop("monthly_cap_usd")
        if value is not None:
            params["monthly_cap_micros"] = int(Decimal(str(value)) * 1_000_000 + Decimal("0.5"))
        bind.execute(
            sa.text("UPDATE task_assignments SET params = :params WHERE task = :task"),
            {"params": json.dumps(params), "task": row["task"]},
        )

    with op.batch_alter_table("ai_interactions") as batch:
        batch.drop_column("cost_usd")
    with op.batch_alter_table("models") as batch:
        batch.drop_column("cost_in")
        batch.drop_column("cost_out")


def downgrade() -> None:
    with op.batch_alter_table("models") as batch:
        batch.add_column(sa.Column("cost_in", sa.Float(), nullable=True))
        batch.add_column(sa.Column("cost_out", sa.Float(), nullable=True))

    for row in (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT provider_key, provider_ref, model, input_micros_per_million, "
                "output_micros_per_million FROM ai_price_overrides WHERE match = 'exact'"
            )
        )
        .mappings()
    ):
        if row["provider_ref"] is not None:
            continue
        op.get_bind().execute(
            sa.text(
                "UPDATE models SET cost_in = :cost_in, cost_out = :cost_out "
                "WHERE external_id = :model AND provider_id IN "
                "(SELECT id FROM providers WHERE preset_key = :provider_key)"
            ),
            {
                "cost_in": (row["input_micros_per_million"] or 0) / 1_000_000,
                "cost_out": (row["output_micros_per_million"] or 0) / 1_000_000,
                "model": row["model"],
                "provider_key": row["provider_key"],
            },
        )

    with op.batch_alter_table("ai_interactions") as batch:
        batch.add_column(sa.Column("cost_usd", sa.Float(), nullable=True))
    op.get_bind().execute(
        sa.text(
            "UPDATE ai_interactions SET cost_usd = cost_micros / 1000000.0 "
            "WHERE cost_micros IS NOT NULL"
        )
    )
    with op.batch_alter_table("ai_interactions") as batch:
        batch.drop_constraint("usage_source_allowed", type_="check")
        batch.drop_constraint("price_source_allowed", type_="check")
    with op.batch_alter_table("ai_interactions") as batch:
        batch.drop_column("price_version")
        batch.drop_column("estimate_method")
        batch.drop_column("price_source")
        batch.drop_column("usage_source")
        batch.drop_column("provider_key")
        batch.drop_column("model_external_id")
        batch.drop_column("cost_micros")
    op.drop_table("ai_price_overrides")
