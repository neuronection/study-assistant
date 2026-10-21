"""uuid_identity — every user-data primary key becomes a UUID (plan 81 C, ADR-198)

The identity cut: `users`/`profiles` already carried `Uuid(as_uuid=False)`
identity (CHAR(32) hex on SQLite, native `uuid` on PostgreSQL); every
user-data entity now uses the same convention and the integer surrogate
keys are retired. Every FK that pointed at such a key follows, including
the polymorphic loose references (`notes.owner_id`, `chat_messages.parent_id`,
`skill_versions.scope_ref`, `ai_interactions.context_id`, `*_drawings.ocr_job_id`).

**This migration is destructive.** SQLite cannot convert an `INTEGER`
primary key into the UUID storage shape in place (the rowid alias), so the
whole identity domain is dropped and rebuilt from the model metadata —
children first, then parents (the 0066 pattern). No rows are carried over:
the round's policy is that dev databases are rebuilt, not migrated
(ADR-196). Reindex after upgrading (FTS rows and vectors are cleared).

`downgrade()` restores the pre-0073 *shape* — empty integer-keyed tables —
by rebuilding the same domain from a copy of the metadata with every
identity column typed back to `Integer`. It is a shape restore, not a data
restore.

Revision ID: 0073_uuid_identity
Revises: 0072_vocab_checks
Create Date: 2026-10-21
"""

from contextlib import suppress
from typing import Any

import sqlalchemy as sa
from sqlalchemy.schema import DefaultClause, Table
from sqlalchemy.sql.elements import TextClause

import app.domain.models  # noqa: F401  — registers tables on Base.metadata
from alembic import op
from app.storage.db import Base

revision: str = "0073_uuid_identity"
down_revision: str | None = "0072_vocab_checks"
branch_labels = None
depends_on = None

_UUID = sa.Uuid(as_uuid=False)

_IDENTITY_CORE = frozenset({"users", "profiles", "auth_sessions", "audit_events"})

_LOOSE_INTEGER_COLUMNS: dict[str, tuple[str, ...]] = {
    "ai_interactions": ("context_id", "skill_version_id"),
    "chat_messages": ("active_child_id", "parent_id"),
    "chat_sessions": ("active_root_id",),
    "concept_skill_stats": ("concept_id",),
    "material_drawings": ("ocr_job_id",),
    "material_images": ("ocr_job_id",),
    "material_suggestions": ("node_id",),
    "materials": ("source_id",),
    "note_drawings": ("ocr_job_id",),
    "notes": ("node_id", "owner_id"),
    "skill_versions": ("scope_ref",),
    "tree_nodes": ("parent_id",),
}

_DECISION_SLOTS = (
    "decision:tool-dispatch",
    "decision:boolean-gate",
    "decision:choice",
    "decision:score",
)

_FTS_TABLES = ("material_fts", "material_fts_trigram")
_VECTOR_TABLES = ("chunk_vecs", "chunk_vec_ids")


def _identity_domain() -> list[Table]:
    """Tables whose identity (PK or referencing FK) this revision rewrites.

    Seeded from the tables whose primary key is a UUID — minus the identity
    core, which already was — then closed over every table that references
    the set, because each of those FK columns changed type as well.
    `metadata.sorted_tables` yields parents before children.
    """
    metadata = Base.metadata
    names: set[str] = set()
    for table in metadata.tables.values():
        if table.name in _IDENTITY_CORE:
            continue
        if all(isinstance(column.type, sa.Uuid) for column in table.primary_key.columns):
            names.add(table.name)
    changed = True
    while changed:
        changed = False
        for table in metadata.tables.values():
            if table.name in names:
                continue
            if any(fk.column.table.name in names for fk in table.foreign_keys):
                names.add(table.name)
                changed = True
    return [table for table in metadata.sorted_tables if table.name in names]


def _portable_boolean_defaults() -> list[tuple[sa.Column[Any], Any]]:
    """Rewrite SQLite-idiom boolean server defaults (`text("0")`) so the
    metadata-driven rebuild works on PostgreSQL too (0066 precedent)."""
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


def _reseed_decision_slots(bind: sa.engine.Connection) -> None:
    """`default_task_assignments` is part of the identity domain, so the
    rebuild drops the four decision slot rows seeded by 0069. Restore them:
    `alembic upgrade head` must leave the database in the state the app
    expects (boot seeding is idempotent but not a migration's job)."""
    for slot in _DECISION_SLOTS:
        bind.execute(
            sa.text(
                "INSERT INTO default_task_assignments (requires, model_id, fallback_model_id) "
                "SELECT :slot, NULL, NULL WHERE NOT EXISTS ("
                "SELECT 1 FROM default_task_assignments WHERE requires = :slot)"
            ),
            {"slot": slot},
        )


def _clear_derived_indexes(bind: sa.engine.Connection) -> None:
    for name in (*_FTS_TABLES, *_VECTOR_TABLES):
        with suppress(sa.exc.DBAPIError):
            bind.execute(sa.text(f'DELETE FROM "{name}"'))


def _rebuild_postgres_fts(bind: sa.engine.Connection) -> None:
    """The PostgreSQL FTS twins keyed `material_id BIGINT`; identity moved to
    UUID text, so the generated-column tables are rebuilt empty."""
    bind.execute(sa.text("DROP TABLE IF EXISTS material_fts"))
    bind.execute(sa.text("DROP TABLE IF EXISTS material_fts_trigram"))
    bind.execute(
        sa.text(
            "CREATE TABLE material_fts ("
            "material_id TEXT, "
            "title TEXT, "
            "markdown TEXT, "
            "description TEXT, "
            "topics TEXT, "
            "tsv tsvector GENERATED ALWAYS AS ("
            "  to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(markdown,'') || ' '"
            "    || coalesce(description,'') || ' ' || coalesce(topics,''))"
            ") STORED)"
        )
    )
    bind.execute(sa.text("CREATE INDEX ix_material_fts_tsv ON material_fts USING gin (tsv)"))
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    bind.execute(
        sa.text(
            "CREATE TABLE material_fts_trigram ("
            "material_id TEXT, "
            "title TEXT, markdown TEXT, description TEXT, topics TEXT, "
            "search_text TEXT GENERATED ALWAYS AS "
            "(coalesce(title,'') || ' ' || coalesce(markdown,'')) STORED)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX ix_material_fts_trigram_search_text "
            "ON material_fts_trigram USING gin (search_text gin_trgm_ops)"
        )
    )


def _integer_copy(domain: list[Table]) -> list[Table]:
    """The pre-0073 shape: the same domain with identity columns typed back
    to `Integer`. Seeded tables reference `_UUID` object identity nowhere, so
    a type swap per column is the whole shape difference."""
    names = {table.name for table in domain}
    metadata = sa.MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata)
    for name in names:
        table = metadata.tables[name]
        for column in table.c:
            references_changed = any(
                fk.column.table.name in names and fk.column.table.name not in _IDENTITY_CORE
                for fk in column.foreign_keys
            )
            is_own_key = column.primary_key
            if isinstance(column.type, sa.Uuid) and (
                references_changed
                or is_own_key
                or column.name in _LOOSE_INTEGER_COLUMNS.get(name, ())
            ):
                column.type = sa.Integer()
    return [metadata.tables[table.name] for table in domain]


def upgrade() -> None:
    bind = op.get_bind()
    domain = _identity_domain()
    originals = _portable_boolean_defaults()
    try:
        for table in reversed(domain):
            table.drop(bind=bind, checkfirst=True)
        for table in domain:
            table.create(bind=bind, checkfirst=True)
    finally:
        for column, default in originals:
            column.server_default = default
    _reseed_decision_slots(bind)
    if bind.dialect.name == "postgresql":
        _rebuild_postgres_fts(bind)
    _clear_derived_indexes(bind)


def downgrade() -> None:
    bind = op.get_bind()
    domain = _identity_domain()
    integer_domain = _integer_copy(domain)
    originals = _portable_boolean_defaults()
    try:
        for table in reversed(domain):
            table.drop(bind=bind, checkfirst=True)
        for table in integer_domain:
            table.create(bind=bind, checkfirst=True)
    finally:
        for column, default in originals:
            column.server_default = default
    _clear_derived_indexes(bind)
