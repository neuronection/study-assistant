import shutil
import socket
from collections.abc import Iterator
from pathlib import Path

import keyring
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from filelock import FileLock
from keyring.backend import KeyringBackend
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.main as app_main
from alembic import command
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


def _block_network() -> None:
    def _deny(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "network access during tests is forbidden — inject an httpx transport"
        )

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
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{template}")
            command.upgrade(alembic_cfg, "head")
    return template


@pytest.fixture(autouse=True)
def _fast_fresh_db_migrations(
    migrated_db_template: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_run_migrations = app_main._run_migrations

    def fast_or_real(engine: Engine) -> None:
        database = engine.url.database
        if database and not Path(database).exists():
            shutil.copyfile(migrated_db_template, database)
            return
        real_run_migrations(engine)

    monkeypatch.setattr(app_main, "_run_migrations", fast_or_real)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(tmp_path: Path, migrated_db_template: Path) -> Iterator[Session]:
    db_path = tmp_path / "app.db"
    shutil.copyfile(migrated_db_template, db_path)
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    with factory() as session:
        yield session
    engine.dispose()
