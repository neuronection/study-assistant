"""PostgreSQL twins for backup/restore and checkpointer pruning (ADR-0022 S3).

Skipped unless ``SA_TEST_DATABASE_URL`` points at a disposable PostgreSQL
server. Scratch databases are created on that server, exercised, and dropped
again — the caller's database is never touched.
"""

import json
import os
import socket
import time
import uuid
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.pool import NullPool

from alembic import command
from app.ai.graphs.checkpointer import prune_checkpoints
from app.services.platform.backup import (
    DB_KIND_POSTGRES,
    DB_NAME,
    DB_NAME_PG,
    MANIFEST_NAME,
    DatabaseDump,
    build_backup,
    database_is_healthy,
    read_archive,
    restore_database_pg,
)

# gate-allow: DATABASE_URL (module local; the env read is SA_TEST_DATABASE_URL)
DATABASE_URL = os.environ.get("SA_TEST_DATABASE_URL", "")

if not DATABASE_URL:
    pytest.skip(
        "SA_TEST_DATABASE_URL is not set — the PostgreSQL backup twins "
        "need a disposable server",
        allow_module_level=True,
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


def _create_database(base: URL, name: str) -> None:
    maintenance = create_engine(base.set(database="postgres"), poolclass=NullPool)
    try:
        with maintenance.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        maintenance.dispose()


def _drop_database(base: URL, name: str) -> None:
    maintenance = create_engine(base.set(database="postgres"), poolclass=NullPool)
    try:
        with maintenance.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        maintenance.dispose()


def _engine_url(engine: Engine) -> str:
    return engine.url.render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def migrated_pg(_loopback_sockets: None) -> Iterator[Engine]:
    """A scratch database on the same server, migrated to head."""
    base = make_url(DATABASE_URL)
    scratch = f"{base.database or 'postgres'}_baktest_{uuid.uuid4().hex[:8]}"
    _create_database(base, scratch)
    scratch_url = base.set(database=scratch)
    engine: Engine | None = None
    try:
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option(
            "sqlalchemy.url", scratch_url.render_as_string(hide_password=False)
        )
        command.upgrade(alembic_cfg, "head")
        engine = create_engine(scratch_url, poolclass=NullPool)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(base, scratch)


@pytest.fixture(scope="module")
def checkpoints_pg(_loopback_sockets: None) -> Iterator[Engine]:
    """A scratch database with the LangGraph checkpoint table shape
    (`checkpoints` / `checkpoint_writes`) created via raw SQL."""
    base = make_url(DATABASE_URL)
    scratch = f"{base.database or 'postgres'}_ckpttest_{uuid.uuid4().hex[:8]}"
    _create_database(base, scratch)
    engine = create_engine(base.set(database=scratch), poolclass=NullPool)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE checkpoints ("
                    "thread_id text NOT NULL, "
                    "checkpoint_ns text NOT NULL, "
                    "checkpoint_id text NOT NULL)"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE checkpoint_writes ("
                    "thread_id text NOT NULL, "
                    "checkpoint_ns text NOT NULL, "
                    "checkpoint_id text NOT NULL, "
                    "task_id text NOT NULL, "
                    "idx integer NOT NULL)"
                )
            )
        yield engine
    finally:
        engine.dispose()
        _drop_database(base, scratch)


def test_build_backup_uses_pg_dump_member(
    migrated_pg: Engine, tmp_path: Path
) -> None:
    blobs_dir = tmp_path / "blobs"
    blobs_dir.mkdir()
    (blobs_dir / "note.bin").write_bytes(b"blob-bytes")

    package = build_backup(
        tmp_path / "study.sqlite3", blobs_dir, database_url=_engine_url(migrated_pg)
    )

    with zipfile.ZipFile(BytesIO(package)) as archive:
        names = archive.namelist()
    assert MANIFEST_NAME in names
    assert DB_NAME_PG in names
    assert DB_NAME not in names

    database, blobs = read_archive(package)
    assert database.kind == DB_KIND_POSTGRES
    assert blobs == {"note.bin": b"blob-bytes"}
    assert database_is_healthy(database)


def test_pg_dump_restore_round_trip(migrated_pg: Engine, tmp_path: Path) -> None:
    url = _engine_url(migrated_pg)
    seeded = {"aaa@example.org", "bbb@example.org"}
    with migrated_pg.begin() as conn:
        for email in sorted(seeded):
            conn.execute(
                text(
                    "INSERT INTO users (id, email, full_name, is_active, is_admin, "
                    "failed_login_attempts, token_version, created_at, updated_at) "
                    "VALUES (:id, :email, '', true, false, 0, 1, now(), now())"
                ),
                {"id": str(uuid.uuid4()), "email": email},
            )

    package = build_backup(tmp_path / "study.sqlite3", tmp_path / "blobs", database_url=url)
    database, _blobs = read_archive(package)
    assert database.kind == DB_KIND_POSTGRES

    with migrated_pg.begin() as conn:
        conn.execute(text("DELETE FROM users"))
        remaining = conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
    assert remaining == 0

    restore_database_pg(url, database.data)

    with migrated_pg.connect() as conn:
        emails = {
            row[0]
            for row in conn.execute(text("SELECT email FROM users")).fetchall()
        }
    assert emails == seeded


def test_garbage_pg_dump_is_not_healthy() -> None:
    assert database_is_healthy(DatabaseDump(DB_KIND_POSTGRES, b"garbage")) is False

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(MANIFEST_NAME, json.dumps({"format": "sa-backup/v1"}))
        archive.writestr(DB_NAME_PG, b"garbage")
    database, _blobs = read_archive(buffer.getvalue())
    assert database.kind == DB_KIND_POSTGRES
    assert database_is_healthy(database) is False


def test_prune_checkpoints_engine_removes_stale_threads(
    checkpoints_pg: Engine,
) -> None:
    stale_id = str(uuid.UUID(int=0))  # hex prefix far below any recent cutoff
    fresh_id = str(uuid.UUID(int=(1 << 128) - 1))  # far above it
    with checkpoints_pg.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id) "
                "VALUES ('t-stale', '', :cid)"
            ),
            {"cid": stale_id},
        )
        conn.execute(
            text(
                "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id) "
                "VALUES ('t-fresh', '', :cid)"
            ),
            {"cid": fresh_id},
        )
        conn.execute(
            text(
                "INSERT INTO checkpoint_writes (thread_id, checkpoint_ns, "
                "checkpoint_id, task_id, idx) "
                "VALUES ('t-stale', '', :cid, 'task-1', 0)"
            ),
            {"cid": stale_id},
        )
        conn.execute(
            text(
                "INSERT INTO checkpoint_writes (thread_id, checkpoint_ns, "
                "checkpoint_id, task_id, idx) "
                "VALUES ('t-fresh', '', :cid, 'task-1', 0)"
            ),
            {"cid": fresh_id},
        )
        conn.execute(
            text(
                "INSERT INTO checkpoint_writes (thread_id, checkpoint_ns, "
                "checkpoint_id, task_id, idx) "
                "VALUES ('t-fresh', '', 'orphan-checkpoint', 'task-2', 0)"
            )
        )

    deleted = prune_checkpoints(
        Path("unused-sqlite-path"),
        ttl_days=14,
        now_ms=int(time.time() * 1000),
        engine=checkpoints_pg,
    )
    assert deleted == 1

    with checkpoints_pg.connect() as conn:
        checkpoints = {
            (row[0], row[2])
            for row in conn.execute(
                text("SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoints")
            ).fetchall()
        }
        writes = {
            (row[0], row[2], row[3])
            for row in conn.execute(
                text(
                    "SELECT thread_id, checkpoint_ns, checkpoint_id, task_id FROM checkpoint_writes"
                )
            ).fetchall()
        }
    assert checkpoints == {("t-fresh", fresh_id)}
    # stale thread's write row and the orphaned write row are both gone
    assert writes == {("t-fresh", fresh_id, "task-1")}

    assert (
        prune_checkpoints(
            Path("unused-sqlite-path"),
            ttl_days=14,
            now_ms=int(time.time() * 1000),
            engine=checkpoints_pg,
        )
        == 0
    )
