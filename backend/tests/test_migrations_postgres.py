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
from contextlib import contextmanager
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from filelock import FileLock
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, RowMapping, make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app.domain.models import (
    Chunk,
    Course,
    Extraction,
    Material,
    Profile,
    User,
    VectorSpace,
)
from app.storage import vectors
from app.storage.vector_contract import content_hash, space_key
from app.storage.vector_schema import index_table_name

# gate-allow: DATABASE_URL (module local; the env read is SA_TEST_DATABASE_URL)
DATABASE_URL = os.environ.get("SA_TEST_DATABASE_URL", "")

if not DATABASE_URL:
    pytest.skip(
        "SA_TEST_DATABASE_URL is not set — the PostgreSQL migration twin needs a disposable server",
        allow_module_level=True,
    )


# xdist workers each build their own scratch database; the full Alembic
# chain must not run concurrently on the server or it exhausts PostgreSQL's
# lock table (max_locks_per_transaction).
_MIGRATION_LOCK = FileLock(os.path.join(tempfile.gettempdir(), "sa-mig-pg-migrations.lock"))


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


def _scalar(engine: Engine, statement: str, params: dict[str, Any] | None = None) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(statement), params or {}).scalar()


def _relation_exists(engine: Engine, name: str) -> bool:
    return _scalar(engine, "SELECT to_regclass(:name)", {"name": name}) is not None


def _rows(engine: Engine, statement: str) -> list[RowMapping]:
    with engine.connect() as conn:
        return list(conn.execute(text(statement)).mappings())


@contextmanager
def _scratch_database() -> Iterator[tuple[Config, Engine]]:
    """A throwaway database on the configured server plus an alembic config."""
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
        engine = create_engine(scratch_url, poolclass=NullPool)
        yield alembic_cfg, engine
    finally:
        if engine is not None:
            engine.dispose()
        with maintenance.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        maintenance.dispose()


def _seed_legacy_store(engine: Engine) -> dict[str, Any]:
    """Seed the pre-0012 shape (ORM rows + the runtime legacy vector tables)."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        user = User(email="pg-migration@test.local", password_hash=None)
        session.add(user)
        session.flush()
        profile = Profile(user_id=user.id, name="Default", is_default=True)
        session.add(profile)
        session.flush()
        course = Course(profile_id=profile.id, title="PostgreSQL migration")
        session.add(course)
        session.flush()
        material = Material(
            profile_id=profile.id,
            course_id=course.id,
            kind="md",
            title="Notes",
            filename="notes.md",
            status="ready",
        )
        session.add(material)
        session.flush()
        extraction = Extraction(
            material_id=material.id,
            extractor="test",
            blocks=[{"type": "text", "md": "alpha\n\nbeta"}],
            markdown="alpha\n\nbeta",
        )
        session.add(extraction)
        session.flush()
        chunks = [
            Chunk(extraction_id=extraction.id, ordinal=0, text="alpha"),
            Chunk(extraction_id=extraction.id, ordinal=1, text="beta"),
        ]
        session.add_all(chunks)
        session.commit()
        chunk_ids = [str(chunk.id) for chunk in chunks]
        vectors.store(
            session,
            chunk_ids,
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
            "legacy-model",
        )
        session.commit()
        return {
            "profile_id": str(profile.id),
            "material_id": str(material.id),
            "chunk_ids": chunk_ids,
        }


@pytest.fixture(scope="module")
def migrated_pg(_loopback_sockets: None) -> Iterator[Engine]:
    """A scratch database on the same server, migrated to head."""
    with _scratch_database() as (alembic_cfg, engine):
        with _MIGRATION_LOCK:
            command.upgrade(alembic_cfg, "head")
        yield engine


@pytest.fixture(scope="module")
def seeded_vector_pg(
    _loopback_sockets: None,
) -> Iterator[tuple[Config, Engine, dict[str, Any]]]:
    """A scratch database at 0011 with a real legacy store, migrated to head."""
    with _scratch_database() as (alembic_cfg, engine):
        with _MIGRATION_LOCK:
            command.upgrade(alembic_cfg, "0011_retrieval_run_actions")
        seeded = _seed_legacy_store(engine)
        with _MIGRATION_LOCK:
            command.upgrade(alembic_cfg, "head")
        yield alembic_cfg, engine, seeded


def test_upgrade_reaches_head(migrated_pg: Engine) -> None:
    """The migrated database sits at alembic's *current* head.

    The expected revision is derived from the migration scripts, never
    hardcoded — landing a new migration must not require editing tests.
    """
    expected = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    with migrated_pg.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == expected


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


def test_retrieval_ops_tables_and_job_result(migrated_pg: Engine) -> None:
    rollups = _columns(migrated_pg, "retrieval_query_rollups")
    assert rollups["space_id"]["is_nullable"] == "NO"
    assert rollups["latency_histogram"]["data_type"] == "json"
    assert rollups["latency_histogram_schema_version"]["is_nullable"] == "NO"
    snapshots = _columns(migrated_pg, "retrieval_coverage_snapshots")
    assert snapshots["ann_recall"]["is_nullable"] == "YES"
    assert snapshots["probe_size"]["is_nullable"] == "YES"
    jobs = _columns(migrated_pg, "jobs")
    assert jobs["result"]["data_type"] == "json"
    with migrated_pg.connect() as conn:
        check = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_jobs_type_allowed'"
            )
        ).scalar_one()
    assert "VECTOR_REINDEX" in check
    assert "VECTOR_MAINTENANCE" in check
    assert "VECTOR_CUTOVER" in check


def test_alerts_and_generation_tag_tables(migrated_pg: Engine) -> None:
    interactions = _columns(migrated_pg, "ai_interactions")
    assert interactions["metadata"]["data_type"] == "json"
    assert interactions["metadata"]["is_nullable"] == "NO"
    assert interactions["metadata_schema_version"]["data_type"] == "smallint"
    assert interactions["metadata_schema_version"]["is_nullable"] == "NO"
    for table in ("notification_kinds", "notifications"):
        assert _relation_exists(migrated_pg, table)
    assert _columns(migrated_pg, "notifications")["dedup_key"]["is_nullable"] == "YES"
    with migrated_pg.connect() as conn:
        index = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = "
                "'uq_notifications_dedup_key'"
            )
        ).scalar_one()
    assert "UNIQUE" in index
    assert "WHERE" in index
    assert "dedup_key IS NOT NULL" in index


def test_baseline_boolean_defaults_are_dialect_portable(migrated_pg: Engine) -> None:
    """Boolean ``server_default=0/1`` is a PostgreSQL DDL error.

    The pre-0012 chain shipped five such defaults in the baseline and one in
    ``0009_calendar_links``; a fresh PostgreSQL upgrade failed at
    ``CREATE TABLE courses``. They are SQLAlchemy ``false()``/``true()`` now.
    """
    expected = {
        ("courses", "hidden"): "false",
        ("material_sources", "mirror_subdirs"): "false",
        ("chat_sessions", "quizme"): "false",
        ("chat_quiz_pendings", "awaiting_answer"): "false",
        ("materials", "starred"): "false",
        ("calendar_links", "enabled"): "true",
    }
    with migrated_pg.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name, column_default "
                "FROM information_schema.columns WHERE table_schema = 'public'"
            )
        ).mappings()
        defaults = {(row["table_name"], row["column_name"]): row["column_default"] for row in rows}
    for column, value in expected.items():
        assert defaults[column] == value


def test_decision_slots_seed_on_postgres(migrated_pg: Engine) -> None:
    """The slot seed reuses one bind parameter in target and predicate.

    PostgreSQL type-deduced the two occurrences as ``text`` vs
    ``character varying`` and rejected the statement; both are cast now.
    """
    slots = {
        row["requires"]
        for row in _rows(migrated_pg, "SELECT requires FROM default_task_assignments")
    }
    assert {
        "decision:tool-dispatch",
        "decision:boolean-gate",
        "decision:choice",
        "decision:score",
    } <= slots


def test_vector_space_backfill_shape_and_round_trip(
    seeded_vector_pg: tuple[Config, Engine, dict[str, Any]],
) -> None:
    """0012 maps the legacy store on PostgreSQL and survives downgrade/upgrade."""
    alembic_cfg, engine, seeded = seeded_vector_pg
    chunk_ids: list[str] = seeded["chunk_ids"]

    assert _relation_exists(engine, "chunk_vecs")
    assert _relation_exists(engine, "chunk_vec_ids")
    assert _scalar(engine, "SELECT count(*) FROM chunk_vecs") == 2

    space = _rows(
        engine, "SELECT id, name, model, dim, index_table, status, normalize FROM vector_spaces"
    )[0]
    physical = index_table_name("legacy-chunk-vecs")
    assert physical == "vec_dfbcce9b"
    assert space["id"] == "legacy-chunk-vecs"
    assert space["name"] == "content"
    assert space["model"] == "legacy-model"
    assert space["dim"] == 4
    assert space["index_table"] == physical
    assert space["status"] == "active"
    assert space["normalize"] is True
    assert _relation_exists(engine, physical)
    assert _scalar(engine, f"SELECT count(*) FROM {physical}") == 2
    assert _scalar(
        engine,
        f"SELECT count(*) FROM {physical} v JOIN vector_records r ON r.id = v.record_id",
    ) == 2
    assert _scalar(
        engine,
        "SELECT 1 FROM pg_indexes WHERE tablename = :table AND indexname = :index",
        {"table": physical, "index": f"ix_{physical}_hnsw"},
    ) == 1
    assert _scalar(engine, "SELECT count(*) FROM chunk_vecs") == 2

    legacy_meta = {
        row["key"]: row["value"] for row in _rows(engine, "SELECT key, value FROM vec_meta")
    }
    assert legacy_meta["model"] == space["model"]
    assert int(legacy_meta["dim"]) == space["dim"]

    document = _rows(
        engine, "SELECT id, space_id, kind, source_id, profile_id FROM vector_documents"
    )[0]
    assert str(document["id"]) == seeded["material_id"]
    assert document["space_id"] == "legacy-chunk-vecs"
    assert document["kind"] == "material"
    assert document["source_id"] == seeded["material_id"]
    assert str(document["profile_id"]) == seeded["profile_id"]

    records = _rows(
        engine,
        "SELECT id, document_id, space_id, view, chunk_index, rowid, "
        "content_hash, embedding FROM vector_records ORDER BY chunk_index",
    )
    assert len(records) == 2
    assert {str(record["id"]) for record in records} == set(chunk_ids)
    assert {str(record["document_id"]) for record in records} == {seeded["material_id"]}
    assert {record["space_id"] for record in records} == {"legacy-chunk-vecs"}
    assert {record["view"] for record in records} == {"body"}
    assert [record["chunk_index"] for record in records] == [0, 1]
    assert [record["content_hash"] for record in records] == [
        content_hash("alpha"),
        content_hash("beta"),
    ]
    assert [record["embedding"] for record in records] == [None, None]

    legacy_rowids = {int(row["rowid"]) for row in _rows(engine, "SELECT rowid FROM chunk_vec_ids")}
    metadata_rowids = {int(record["rowid"]) for record in records}
    assert (
        metadata_rowids == legacy_rowids == {vectors.rowid_for(chunk_id) for chunk_id in chunk_ids}
    )

    assert _scalar(engine, "SELECT count(*) FROM retrieval_coverage_snapshots") == 0

    with engine.connect() as conn:
        constraints: dict[str, str] = {
            str(row[0]): str(row[1])
            for row in conn.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname IN ('uq_vector_records_rowid', 'uq_vector_documents_source', "
                    "'ck_vector_spaces_status_allowed', 'ck_vector_records_view_allowed')"
                )
            )
        }
        indexes: dict[str, str] = {
            str(row[0]): str(row[1])
            for row in conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE indexname IN ('uq_vector_spaces_name_active', "
                    "'uq_jobs_idempotency_active', 'uq_jobs_lock_key_active')"
                )
            )
        }
    assert "UNIQUE" in constraints["uq_vector_records_rowid"]
    assert "UNIQUE" in constraints["uq_vector_documents_source"]
    assert "active" in constraints["ck_vector_spaces_status_allowed"]
    assert "body" in constraints["ck_vector_records_view_allowed"]
    assert "UNIQUE" in indexes["uq_vector_spaces_name_active"]
    for name in ("uq_jobs_idempotency_active", "uq_jobs_lock_key_active"):
        assert "UNIQUE" in indexes[name]
        assert "WHERE" in indexes[name]
        assert "queued" in indexes[name]
        assert "running" in indexes[name]
    assert _columns(engine, "jobs")["cancel_requested"]["is_nullable"] == "NO"

    with _MIGRATION_LOCK:
        command.downgrade(alembic_cfg, "0011_retrieval_run_actions")
    for table in ("vector_spaces", "vector_documents", "vector_records"):
        assert not _relation_exists(engine, table)
    assert not _relation_exists(engine, physical)
    assert _scalar(engine, "SELECT count(*) FROM chunk_vecs") == 2
    assert _scalar(engine, "SELECT count(*) FROM chunk_vec_ids") == 2
    assert _scalar(engine, "SELECT value FROM vec_meta WHERE key = 'model'") == "legacy-model"

    with _MIGRATION_LOCK:
        command.upgrade(alembic_cfg, "head")
    assert _scalar(engine, "SELECT count(*) FROM vector_spaces") == 1
    assert _scalar(engine, "SELECT count(*) FROM vector_documents") == 1
    assert _scalar(engine, "SELECT count(*) FROM vector_records") == 2
    assert _scalar(engine, "SELECT count(*) FROM retrieval_coverage_snapshots") == 0
    assert _relation_exists(engine, physical)
    assert _scalar(engine, f"SELECT count(*) FROM {physical}") == 2
    assert _rows(engine, "SELECT index_table FROM vector_spaces")[0]["index_table"] == physical


def test_vector_space_key_and_token_columns_round_trip(
    seeded_vector_pg: tuple[Config, Engine, dict[str, Any]],
) -> None:
    """0016 stamps populated keys; 0017 drops only the token columns."""
    alembic_cfg, engine, _seeded = seeded_vector_pg
    with _MIGRATION_LOCK:
        command.downgrade(alembic_cfg, "0015_retrieval_alerts")
    assert "space_key" not in _columns(engine, "vector_spaces")
    assert "tokenizer_kind" not in _columns(engine, "vector_spaces")

    space_id = str(uuid.uuid4())
    name = f"pg-key-{uuid.uuid4().hex[:8]}"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO vector_spaces "
                "(id, name, provider, model, dim, metric, normalize, "
                " chunker_version, composer_version, index_table, status, "
                " created_at, updated_at) "
                "VALUES (:id, :name, 'openai', 'text-embedding-3-small', 384, "
                "        'cosine', true, '1', '1', NULL, 'building', now(), now())"
            ),
            {"id": space_id, "name": name},
        )

    with _MIGRATION_LOCK:
        command.upgrade(alembic_cfg, "head")

    expected = space_key(
        "openai", "text-embedding-3-small", 384, True, None, None, "1", "1"
    )
    stored = {
        str(row["id"]): str(row["space_key"])
        for row in _rows(engine, "SELECT id, space_key FROM vector_spaces")
    }
    assert stored[space_id] == expected
    assert stored["legacy-chunk-vecs"] == space_key(
        "unassigned", "legacy-model", 4, True, None, None, "1", "1"
    )
    for column in (
        "tokenizer_kind",
        "tokenizer_identifier",
        "tokenizer_revision",
        "tokenizer_artifact_sha256",
        "tokenizer_exact",
        "max_input_tokens",
        "chunk_max_tokens",
        "chunk_overlap_tokens",
        "chunk_max_chars",
    ):
        assert _columns(engine, "vector_spaces")[column]["is_nullable"] == "YES"
    for column in ("token_count", "token_start", "token_end"):
        assert _columns(engine, "vector_records")[column]["is_nullable"] == "YES"
    assert (
        _scalar(engine, "SELECT count(*) FROM vector_spaces WHERE tokenizer_kind IS NOT NULL")
        == 0
    )
    assert (
        _scalar(engine, "SELECT count(*) FROM vector_records WHERE token_count IS NOT NULL")
        == 0
    )

    with engine.connect() as conn:
        constraints = {
            str(row[0])
            for row in conn.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conname IN ("
                    "'ck_vector_spaces_tokenizer_group_all_or_none', "
                    "'ck_vector_records_token_fields_consistent')"
                )
            )
        }
    assert constraints == {
        "ck_vector_spaces_tokenizer_group_all_or_none",
        "ck_vector_records_token_fields_consistent",
    }

    with _MIGRATION_LOCK:
        command.downgrade(alembic_cfg, "0016_vector_space_stored_key")
    assert "tokenizer_kind" not in _columns(engine, "vector_spaces")
    assert "token_count" not in _columns(engine, "vector_records")
    assert (
        _scalar(
            engine,
            "SELECT space_key FROM vector_spaces WHERE id = :id",
            {"id": space_id},
        )
        == expected
    )

    with _MIGRATION_LOCK:
        command.upgrade(alembic_cfg, "head")

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        row = VectorSpace(
            id=str(uuid.uuid4()),
            name=f"pg-new-{uuid.uuid4().hex[:8]}",
            provider="openai",
            model="text-embedding-3-small",
            dim=4,
            normalize=True,
            chunker_version="1",
            composer_version="1",
            status="building",
        )
        session.add(row)
        session.commit()
        new_key = row.space_key
        new_id = row.id
    assert new_key == space_key(
        "openai", "text-embedding-3-small", 4, True, None, None, "1", "1"
    )
    assert _scalar(
        engine,
        "SELECT space_key FROM vector_spaces WHERE id = :id",
        {"id": new_id},
    ) == new_key


def test_job_progress_detail_round_trip(migrated_pg: Engine) -> None:
    """0019 adds/drops the nullable JSON counters document on PostgreSQL."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option(
        "sqlalchemy.url", migrated_pg.url.render_as_string(hide_password=False)
    )
    assert _columns(migrated_pg, "jobs")["progress_detail"]["data_type"] == "json"
    assert _columns(migrated_pg, "jobs")["progress_detail"]["is_nullable"] == "YES"

    with migrated_pg.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO jobs (id, type, status, progress, progress_detail, created_at) "
                "VALUES (:id, 'VECTOR_REINDEX', 'running', 42, "
                "        '{\"phase\": \"embedding\", \"processed_documents\": 2}', now())"
            ),
            {"id": str(uuid.uuid4())},
        )
    assert (
        _scalar(migrated_pg, "SELECT count(*) FROM jobs WHERE progress_detail IS NOT NULL")
        == 1
    )

    with _MIGRATION_LOCK:
        command.downgrade(alembic_cfg, "0018_vector_record_token_windows")
    assert "progress_detail" not in _columns(migrated_pg, "jobs")

    with _MIGRATION_LOCK:
        command.upgrade(alembic_cfg, "head")
    assert "progress_detail" in _columns(migrated_pg, "jobs")
