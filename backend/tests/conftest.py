import os
import socket
import sqlite3
import tempfile
from collections.abc import Iterator, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

# Test boot context (study's equivalent of career's `.env.test`
# APP_ENV=test): the family boot guards (nx_auth.boot) otherwise assume
# production and demand pinned keys. Forced — tests must be hermetic;
# the boot-guard cases override per-Settings.
os.environ["SA_APP_ENV"] = "test"
# Hermetic §8 key resolution: the at-rest cipher resolves its KeyRing
# through `get_settings()`, so without an explicit config dir the suite
# would read (or first-run generate!) `auth_keys.json` in the real user
# config dir. Every Settings-built-from-env points here instead;
# fixtures that pass an explicit tmp config_dir override it.
os.environ.setdefault("SA_CONFIG_DIR", tempfile.mkdtemp(prefix="sa-test-config-"))

import fastapi.testclient as fastapi_testclient
import keyring
import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from filelock import FileLock
from keyring.backend import KeyringBackend
from nx_auth.instance import IdentityMode
from nx_auth.passwords import hash_password
from nx_auth.tokens import AuthMode, TokenKind, mint_token
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession

import app.main as app_main
from alembic import command
from app.auth.stores import StudyUserStore
from app.core.config import Settings
from app.main import create_app
from app.storage.db import make_engine, make_session_factory


class TestKeyring(KeyringBackend):
    priority = 99

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


keyring.set_keyring(TestKeyring())


@pytest.fixture(scope="session", autouse=True)
def _structlog_to_stdlib() -> None:
    import logging

    import structlog

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.KeyValueRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        cache_logger_on_first_use=True,
    )


@pytest.fixture(autouse=True)
def _reset_native_tools_degradation() -> Iterator[None]:
    from app.ai.chat_models import _NATIVE_TOOLS_DEGRADED

    _NATIVE_TOOLS_DEGRADED.clear()
    yield
    _NATIVE_TOOLS_DEGRADED.clear()


@pytest.fixture(autouse=True)
def _fresh_atrest_key_material() -> Iterator[None]:
    """Per-test at-rest key resolution (tests pin/rotate keys between
    cases; the underlying auth_keys.json in the scratch config dir is
    shared per process, so untouched tests see one stable key)."""
    from app.core import keys
    from app.core import secrets as app_secrets

    keys.reset_keyring_cache()
    app_secrets.reset_secret_caches()
    yield
    keys.reset_keyring_cache()
    app_secrets.reset_secret_caches()


def _block_network() -> None:
    def _deny(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access during tests is forbidden — inject an httpx transport")

    socket.socket.connect = _deny  # type: ignore[method-assign]
    socket.socket.connect_ex = _deny  # type: ignore[method-assign, assignment]
    socket.create_connection = _deny  # type: ignore[assignment]


@pytest.fixture(autouse=True, scope="session")
def _no_network() -> None:
    _block_network()


@pytest.fixture(scope="session")
def migrated_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template = tmp_path_factory.getbasetemp().parent / "migrated_template.db"
    with FileLock(f"{template}.lock"):
        if not template.exists():
            # Build on a staging path and publish atomically: a reader must
            # never observe the template mid-migration (that produces
            # "no such table" copies), and the WAL is checkpointed so the
            # published file is complete on its own.
            staging = template.with_suffix(".building")
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{staging}")
            command.upgrade(alembic_cfg, "head")
            with sqlite3.connect(staging) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            os.replace(staging, template)
    return template


def _clone_template(template: Path, database: str | Path) -> None:
    """Consistent snapshot of the migrated template (SQLite backup API).

    `shutil.copyfile` copies the main file only and truncates a WAL'd
    template — the backup API serializes page-by-page into the target.
    """
    src = sqlite3.connect(f"file:{template}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(database))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


@pytest.fixture(autouse=True)
def _fresh_test_db(migrated_db_template: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every app gets a migrated database (D6: `create_app` never migrates).

    SQLite: clone the migrated template when the DB file is missing (the
    old fast path). Other dialects: migrate the engine's database with a
    connection-scoped `alembic upgrade head` — parity with the pre-split
    behavior (PG tests that pre-migrate scratch DBs see a no-op).
    """
    real_make_engine = app_main.make_engine  # type: ignore[attr-defined]

    def make_engine_migrated(url: str) -> Engine:
        engine = real_make_engine(url)
        database = engine.url.database
        if engine.dialect.name == "sqlite" and database and not Path(database).exists():
            _clone_template(migrated_db_template, Path(database))
        elif engine.dialect.name != "sqlite":
            from app.local import run_migrations

            run_migrations(engine)
        return engine

    monkeypatch.setattr(app_main, "make_engine", make_engine_migrated)


@lru_cache(maxsize=1)
def _fixture_password_hash() -> str:
    """One bcrypt round per test session, not one per test."""
    return hash_password("fixture-password-study")


def mint_session(app: FastAPI, email: str = "session@study.local") -> tuple[str, str, str]:
    """(cookie_header, csrf, profile_id) for an app — creates the admin
    fixture user directly (no HTTP register, one cached bcrypt hash);
    user creation auto-provisions the Default profile (§6)."""
    import secrets

    from nx_auth.cookies import cookie_names

    from app.services.platform.profiles import get_or_create_default

    factory = app.state.session_factory
    users = StudyUserStore(factory)
    user = users.get_by_email(email) or users.create(
        email=email, password_hash=_fixture_password_hash(), is_admin=True
    )
    with factory() as session:
        profile_id = str(get_or_create_default(session, user.id).id)
    kit = app.state.auth
    token = mint_token(
        kit.ring,
        kit.config,
        kind=TokenKind.SESSION,
        sub=user.id,
        ver=user.token_version,
        auth_mode=AuthMode.PASSWORD,
    )
    csrf = secrets.token_urlsafe(32)
    access_name = cookie_names(kit.config).access
    return f"{access_name}={token}; nx_csrf={csrf}", csrf, profile_id


class AuthedTestClient(TestClient):
    """Session-injecting TestClient (S4b enforcement needs a cookie on
    every /api request; ~90 test files build clients via helpers).

    - `__init__` mints a session into the default headers unless the
      caller passes an explicit Cookie (anonymous/instance tests do);
    - WebSocket handshakes carry the same cookie (browsers cannot set
      WS headers — this mirrors how the SPA connects);
    - unauthenticated flows use `AnonymousTestClient` / `raw_client`.
    """

    session_cookie: str = ""

    def __init__(self, app: Any, **kwargs: Any) -> None:
        headers: dict[str, str] = dict(kwargs.pop("headers", None) or {})
        if (
            isinstance(app, FastAPI)
            and getattr(app.state, "auth", None) is not None
            and "Cookie" not in headers
        ):
            cookie, csrf, profile_id = mint_session(app)
            headers.setdefault("Cookie", cookie)
            headers.setdefault("X-CSRF-Token", csrf)
            headers.setdefault("X-Profile-Id", profile_id)
            self.session_cookie = cookie
        super().__init__(app, headers=headers, **kwargs)

    def websocket_connect(
        self, url: str, subprotocols: Sequence[str] | None = None, **kwargs: Any
    ) -> WebSocketTestSession:
        explicit = dict(kwargs.pop("headers", None) or {})
        if self.session_cookie and "Cookie" not in explicit:
            explicit["Cookie"] = self.session_cookie
        kwargs["headers"] = explicit
        return super().websocket_connect(url, subprotocols=subprotocols, **kwargs)


# conftest imports first: every test module's `from fastapi.testclient
# import TestClient` binds the authorizing class. conftest's own
# `TestClient` name stays the anonymous original (bound above).
AnonymousTestClient = TestClient
fastapi_testclient.TestClient = AuthedTestClient  # type: ignore[misc, assignment]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
    )


@pytest.fixture
def raw_client(tmp_path: Path) -> Iterator[TestClient]:
    """Anonymous client — for auth-flow tests that must observe
    first-user-admin and unauthenticated states."""
    app = create_app(_settings(tmp_path))
    with AnonymousTestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Auto-authorized client (session minted by AuthedTestClient)."""
    app = create_app(_settings(tmp_path))
    with AuthedTestClient(app) as authorized:
        yield authorized


@pytest.fixture
def desktop_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # SA_SHELL=1 = the shell.py attachment flag; without it create_app
    # leaves the §11 gate unarmed (shell-less desktop dev, ADR-0023).
    monkeypatch.setenv("SA_SHELL", "1")
    settings = Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
        identity_mode=IdentityMode.DESKTOP,
        shell_secret="test-shell-secret",
    )
    app = create_app(settings)
    with AuthedTestClient(app, headers={"X-Shell-Token": "test-shell-secret"}) as desktop:
        yield desktop


@pytest.fixture
def db_session(tmp_path: Path, migrated_db_template: Path) -> Iterator[Session]:
    db_path = tmp_path / "study.sqlite3"
    # Share the app's database (same data_dir file) — clone only when no
    # app has created it yet. Overwriting a live DB was always wrong: it
    # only ever "worked" because shutil.copyfile left the app's WAL
    # sidecar behind, which replayed the clobbered rows back in.
    if not db_path.exists():
        _clone_template(migrated_db_template, db_path)
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def owner(db_session: Session) -> Any:
    """A user row for direct-ORM tests (profiles FK to users — §5)."""
    from uuid import uuid4

    from app.domain.models import User

    row = User(id=str(uuid4()), email="owner@test.local", password_hash=None)
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture
def profile_id(client: TestClient) -> str:
    """The fixture user's auto-provisioned Default profile id (§6) —
    use this instead of hardcoded ids when seeding rows directly."""
    listed = client.get("/api/v1/profiles")
    assert listed.status_code == 200, listed.text
    profiles = listed.json()
    assert profiles, "the fixture user must have an auto-provisioned profile"
    return str(profiles[0]["id"])
