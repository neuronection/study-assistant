"""modular source providers, auth slots and localhost review merge

Plan 86 A/B/E (ADR-214/215/216). Provider identity stays open data
(`external_sources.provider`, validated against the bundled
`source-providers` catalog at registration); the closed `kind` family gains
the adapter-shaped members and `auth_kind` gains its CHECK twin. Review
events pulled from a localhost SRS bridge are union-merged into
`external_review_events`, keyed by (source, remote card, reviewed time), and
local cards carry the remote card key in `exercises.external_uid` so a
recompute can replay the merged log deterministically.

Revision ID: 0007_source_providers
Revises: 0006_vault_notes
Create Date: 2026-10-22
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_source_providers"
down_revision = "0006_vault_notes"
branch_labels = None
depends_on = None

SOURCE_KINDS = (
    "rss",
    "youtube_channel",
    "youtube_playlist",
    "site_search",
    "webdav_folder",
    "cloud_folder",
    "zotero_collection",
    "anki_deck",
)

AUTH_KINDS = ("token", "oauth2", "none")

PROVIDER_BY_KIND = {
    "rss": "rss",
    "youtube_channel": "youtube",
    "youtube_playlist": "youtube",
    "site_search": "site-search",
}


def upgrade() -> None:
    with op.batch_alter_table("external_sources", recreate="always") as batch:
        batch.add_column(sa.Column("provider", sa.String(64), nullable=False, server_default="rss"))
        batch.add_column(
            sa.Column("auth_kind", sa.String(20), nullable=False, server_default="none")
        )
        batch.add_column(sa.Column("account_ref", sa.String(200), nullable=True))
        batch.add_column(
            sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0")
        )
        batch.drop_constraint("kind_allowed", type_="check")
        kind_values = ", ".join(f"'{kind}'" for kind in SOURCE_KINDS)
        batch.create_check_constraint("kind_allowed", f"kind IN ({kind_values})")
        auth_values = ", ".join(f"'{kind}'" for kind in AUTH_KINDS)
        batch.create_check_constraint("auth_kind_allowed", f"auth_kind IN ({auth_values})")

    for kind, provider in PROVIDER_BY_KIND.items():
        op.execute(
            sa.text(
                "UPDATE external_sources SET provider = :provider WHERE kind = :kind"
            ).bindparams(provider=provider, kind=kind)
        )

    with op.batch_alter_table("exercises", recreate="always") as batch:
        batch.add_column(sa.Column("external_uid", sa.String(200), nullable=True))
    op.create_index("ix_exercises_external_uid", "exercises", ["external_uid"])

    op.create_table(
        "external_review_events",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("external_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("remote_card_id", sa.String(64), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("interval_days", sa.Float(), nullable=False),
        sa.Column("elapsed_days", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_external_review_events_source_id", "external_review_events", ["source_id"])
    op.create_index(
        "ix_external_review_events_remote_card", "external_review_events", ["remote_card_id"]
    )
    op.create_index(
        "uq_external_review_events_source_card_time",
        "external_review_events",
        ["source_id", "remote_card_id", "reviewed_at"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_external_review_events_source_card_time", table_name="external_review_events")
    op.drop_index("ix_external_review_events_remote_card", table_name="external_review_events")
    op.drop_index("ix_external_review_events_source_id", table_name="external_review_events")
    op.drop_table("external_review_events")

    op.drop_index("ix_exercises_external_uid", table_name="exercises")
    with op.batch_alter_table("exercises", recreate="always") as batch:
        batch.drop_column("external_uid")

    with op.batch_alter_table("external_sources", recreate="always") as batch:
        batch.drop_constraint("auth_kind_allowed", type_="check")
        batch.drop_constraint("kind_allowed", type_="check")
        kind_values = ", ".join(f"'{kind}'" for kind in SOURCE_KINDS[:4])
        batch.create_check_constraint("kind_allowed", f"kind IN ({kind_values})")
        batch.drop_column("consecutive_failures")
        batch.drop_column("account_ref")
        batch.drop_column("auth_kind")
        batch.drop_column("provider")
