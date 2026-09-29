"""profile_identity — family `profiles` schema (identity-auth §5)

S2b (plan 16). Destructive greenfield alignment (2026-09-24): the whole
profile domain is rebuilt from the aligned model metadata —

- `profiles`: UUID `id`, `user_id` (FK users, NOT NULL, CASCADE),
  `is_default`, `updated_at`, plus product columns `color` and
  `last_used_at` (§6 "last-used profile remembered per user");
- every `profile_id` column becomes UUID with ON DELETE CASCADE.

No rows are carried over and **downgrade is irreversible** — there is no
backwards compatibility (user directive): recreate dev databases.
Every SQLite virtual table (fts5/vec0 derived search + vector state) is
cleared; reindex after upgrading.

Revision ID: 0066_profile_identity
Revises: 0065_identity_core
Create Date: 2026-09-24
"""

from contextlib import suppress
from typing import Any

import sqlalchemy as sa
from sqlalchemy.schema import DefaultClause, Table
from sqlalchemy.sql.elements import TextClause

import app.domain.models  # noqa: F401  — registers tables on Base.metadata
from alembic import op
from app.storage.db import Base

revision: str = "0066_profile_identity"
down_revision: str | None = "0065_identity_core"
branch_labels = None
depends_on = None


def _profile_domain() -> list[Table]:
    """The rebuild set: `profiles`, every table carrying `profile_id`,
    and every table that references those transitively (children must
    drop before their parents or FK enforcement blocks the rebuild)."""
    metadata = Base.metadata
    names: set[str] = {"profiles"}
    names.update(
        table.name for table in metadata.tables.values() if "profile_id" in table.c
    )
    changed = True
    while changed:
        changed = False
        for table in metadata.tables.values():
            if table.name in names:
                continue
            if any(
                fk.column.table.name in names for fk in table.foreign_keys
            ):  # pragma: no cover - trivial loop
                names.add(table.name)
                changed = True
    return [table for table in metadata.sorted_tables if table.name in names]


def _clear_derived_indexes(bind: sa.engine.Connection) -> None:
    """Wipe sqlite-vec / fts5 virtual tables (derived state)."""
    if bind.dialect.name != "sqlite":
        return
    rows = bind.execute(
        sa.text(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND sql LIKE 'CREATE VIRTUAL TABLE%'"
        )
    ).fetchall()
    for (name,) in rows:
        with suppress(sa.exc.DBAPIError):  # pragma: no cover - virtual table quirks
            bind.execute(sa.text(f'DELETE FROM "{name}"'))


def _portable_boolean_defaults() -> list[tuple[sa.Column[Any], Any]]:
    """Rewrite SQLite-idiom boolean server defaults in the model DDL
    (`server_default=text("0")`) so the metadata-driven recreate works on
    PostgreSQL too: `DEFAULT 0` is an integer literal and PG rejects it on
    BOOLEAN columns (`DatatypeMismatch`). `sa.false()`/`sa.true()` render
    identically to the old text on SQLite (`0`/`1`). Returns the originals
    for restoration after the recreate."""
    originals: list[tuple[sa.Column[Any], Any]] = []
    for table in Base.metadata.tables.values():
        for column in table.c:
            if not isinstance(column.type, sa.Boolean):
                continue
            arg = getattr(column.server_default, "arg", None)
            if not isinstance(arg, TextClause):
                continue
            literal = str(arg).strip()
            if literal == "0":
                originals.append((column, column.server_default))
                column.server_default = DefaultClause(sa.false())
            elif literal == "1":
                originals.append((column, column.server_default))
                column.server_default = DefaultClause(sa.true())
    return originals


def upgrade() -> None:
    bind = op.get_bind()
    ordered = _profile_domain()
    originals = _portable_boolean_defaults()
    try:
        for table in reversed(ordered):
            table.drop(bind=bind, checkfirst=True)
        for table in ordered:
            table.create(bind=bind, checkfirst=True)
    finally:
        for column, default in originals:
            column.server_default = default
    _clear_derived_indexes(bind)


def downgrade() -> None:
    raise NotImplementedError(
        "0066_profile_identity is irreversible — greenfield schema "
        "alignment (no backwards compatibility); recreate the database"
    )
