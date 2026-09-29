"""PostgreSQL twin of the full Alembic chain (ADR-0022 S3 dialect twins).

Skipped unless ``SA_TEST_DATABASE_URL`` points at a disposable PostgreSQL
server. A scratch database is created on that server, migrated to head,
inspected, and dropped again — the caller's database is never touched.
"""

import os
import socket
import tempfile
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from alembic.config import Config
from filelock import FileLock
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, RowMapping, make_url
from sqlalchemy.pool import NullPool

from alembic import command

DATABASE_URL = os.environ.get("SA_TEST_DATABASE_URL", "")

if not DATABASE_URL:
    pytest.skip(
        "SA_TEST_DATABASE_URL is not set — the PostgreSQL migration twin "
        "needs a disposable server",
        allow_module_level=True,
    )


# xdist workers each build their own scratch database; the full Alembic
# chain must not run concurrently on the server or it exhausts PostgreSQL's
# lock table (max_locks_per_transaction).
_MIGRATION_LOCK = FileLock(
    os.path.join(tempfile.gettempdir(), "sa-mig-pg-migrations.lock")
)


@pytest.fixture(scope="module", autouse=True)
def _loopback_sockets() -> Iterator[None]:
    """conftest's session-wide network guard shadows ``socket.socket.connect``
    with a deny function; talking to the PostgreSQL server needs the real
    one back. Restore the guard afterwards so other modules keep it."""
    saved: dict[str, Any] = {
        name: socket.socket.__dict__.get(name) for name in ("connect", "connect_ex")
    }
    for name, original in saved.items():
        if original is not None:
            delattr(socket.socket, name)
    try:
        yield
    finally:
        for name, original in saved.items():
            if original is not None:
                setattr(socket.socket, name, original)


def _columns(engine: Engine, table: str) -> dict[str, RowMapping]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table_name"
            ),
            {"table_name": table},
        ).mappings()
        return {row["column_name"]: row for row in rows}


@pytest.fixture(scope="module")
def migrated_pg(_loopback_sockets: None) -> Iterator[Engine]:
    """A scratch database on the same server, migrated to head."""
    base = make_url(DATABASE_URL)
    scratch = f"{base.database or 'postgres'}_migtest_{uuid.uuid4().hex[:8]}"
    scratch_url = base.set(database=scratch)
    maintenance = create_engine(base.set(database="postgres"), poolclass=NullPool)
    engine: Engine | None = None
    try:
        with maintenance.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'CREATE DATABASE "{scratch}"'))
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option(
            "sqlalchemy.url", scratch_url.render_as_string(hide_password=False)
        )
        with _MIGRATION_LOCK:
            command.upgrade(alembic_cfg, "head")
        engine = create_engine(scratch_url, poolclass=NullPool)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with maintenance.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        maintenance.dispose()


def test_upgrade_reaches_head(migrated_pg: Engine) -> None:
    with migrated_pg.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0066_profile_identity"


def test_material_fts_has_tsvector_column(migrated_pg: Engine) -> None:
    columns = _columns(migrated_pg, "material_fts")
    assert columns["tsv"]["data_type"] == "tsvector"


def test_material_fts_trigram_has_search_text(migrated_pg: Engine) -> None:
    columns = _columns(migrated_pg, "material_fts_trigram")
    assert columns["search_text"]["data_type"] == "text"


def test_pg_trgm_extension_installed(migrated_pg: Engine) -> None:
    with migrated_pg.connect() as conn:
        extensions = {
            row[0] for row in conn.execute(text("SELECT extname FROM pg_extension")).fetchall()
        }
    assert "pg_trgm" in extensions


def test_profiles_shape(migrated_pg: Engine) -> None:
    columns = _columns(migrated_pg, "profiles")
    assert columns["user_id"]["is_nullable"] == "NO"
