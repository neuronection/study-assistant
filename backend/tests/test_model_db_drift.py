"""The model⇄DB drift gate (plan 81 D, family constitution §3).

A migrated empty database is reflected and compared with the declarative
metadata using Alembic's own autogenerate engine (`compare_metadata` closes
over exactly what `alembic revision --autogenerate` would emit). The diff
must be empty: every schema change is model-first or this test goes red.

Scope: model-owned DDL only. The FTS5 shadow tables (`material_fts*`) and the
runtime-created sqlite-vec tables are extension objects that autogenerate
cannot model; they are excluded by table name, and their own tests verify
them (constitution §3 note). A model table that is missing from the database
still produces `add_table`, because only reflected tables outside the
metadata are filtered.
"""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from alembic import command
from app.domain import models  # noqa: F401
from app.storage.db import Base

EXTENSION_TABLES = frozenset(
    {
        "material_fts",
        "material_fts_config",
        "material_fts_content",
        "material_fts_data",
        "material_fts_docsize",
        "material_fts_idx",
        "material_fts_trigram",
        "material_fts_trigram_config",
        "material_fts_trigram_content",
        "material_fts_trigram_data",
        "material_fts_trigram_docsize",
        "material_fts_trigram_idx",
        "chunk_vecs",
        "chunk_vec_ids",
        "vec_meta",
    }
)


def _cfg(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    del obj, compare_to
    if not reflected:
        return True
    return not (type_ == "table" and name in EXTENSION_TABLES)


def test_autogenerate_diff_is_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "drift.db"
    command.upgrade(_cfg(db_path), "head")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "include_object": _include_object,
                    "compare_type": True,
                    "compare_server_default": False,
                },
            )
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], (
        "model and migrated database have drifted — every shape change is "
        f"model-first (plan 81 D drift gate): {diff}"
    )
