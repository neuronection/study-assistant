"""citation metadata on materials

Plan 85 B (ADR-212): a link material can be a paper — queryable citation
facts become typed columns (ADR-200), the ordered authors list stays a
validated JSON document behind the `AuthorList` payload type, and
`citation_kind` carries the `CitationKind` StrEnum's CHECK twin (nullable:
ordinary materials have no citation).

Revision ID: 0004_citation_metadata
Revises: 0003_discovery_kinds
Create Date: 2026-10-22
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_citation_metadata"
down_revision = "0003_discovery_kinds"
branch_labels = None
depends_on = None

CITATION_KINDS = (
    "article",
    "book",
    "chapter",
    "conference",
    "preprint",
    "thesis",
    "report",
    "dataset",
    "other",
)


def _recreate_mode() -> str:
    """SQLite copies the table; PostgreSQL alters it in place.

    A PostgreSQL ``recreate="always"`` copy drops the primary key and fails
    while dependent foreign keys still reference it.
    """
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    with op.batch_alter_table("materials", recreate=_recreate_mode()) as batch:
        batch.add_column(sa.Column("citation_title", sa.String(500), nullable=True))
        batch.add_column(sa.Column("citation_authors", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("citation_year", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("citation_doi", sa.String(255), nullable=True))
        batch.add_column(sa.Column("citation_container", sa.String(300), nullable=True))
        batch.add_column(sa.Column("citation_kind", sa.String(30), nullable=True))
        values = ", ".join(f"'{kind}'" for kind in CITATION_KINDS)
        batch.create_check_constraint(
            "citation_kind_allowed",
            f"citation_kind IS NULL OR citation_kind IN ({values})",
        )


def downgrade() -> None:
    with op.batch_alter_table("materials", recreate=_recreate_mode()) as batch:
        batch.drop_constraint("citation_kind_allowed", type_="check")
        batch.drop_column("citation_kind")
        batch.drop_column("citation_container")
        batch.drop_column("citation_doi")
        batch.drop_column("citation_year")
        batch.drop_column("citation_authors")
        batch.drop_column("citation_title")
