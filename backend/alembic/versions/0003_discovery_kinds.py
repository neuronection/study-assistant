"""scholarly discovery kinds on the suggestion funnel

Plan 85 A (ADR-211): arXiv, OpenAlex and Crossref suggestions carry
`DiscoveryKind.paper | dataset | reference`, so the `material_suggestions.kind`
CHECK twin widens in the same commit as the StrEnum (family data-model §6).
SQLite cannot alter a CHECK in place, so the constraint swaps through
`batch_alter_table(recreate="always")`; a row holding a value the previous
vocabulary did not know makes the downgrade copy fail loudly.

Revision ID: 0003_discovery_kinds
Revises: 0002_vocab_sweep
Create Date: 2026-10-22
"""

from alembic import op

revision = "0003_discovery_kinds"
down_revision = "0002_vocab_sweep"
branch_labels = None
depends_on = None

SCOPE_KINDS = (
    "video",
    "course",
    "article",
    "exercise",
    "paper",
    "dataset",
    "reference",
    "other",
)
BASELINE_KINDS = ("video", "course", "article", "exercise", "other")


def _values(members: tuple[str, ...]) -> str:
    return ", ".join(f"'{member}'" for member in members)


def upgrade() -> None:
    with op.batch_alter_table("material_suggestions", recreate="always") as batch:
        batch.drop_constraint("kind_allowed", type_="check")
        batch.create_check_constraint("kind_allowed", f"kind IN ({_values(SCOPE_KINDS)})")


def downgrade() -> None:
    with op.batch_alter_table("material_suggestions", recreate="always") as batch:
        batch.drop_constraint("kind_allowed", type_="check")
        batch.create_check_constraint("kind_allowed", f"kind IN ({_values(BASELINE_KINDS)})")
