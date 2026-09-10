from sqlalchemy import pool
from sqlalchemy.engine import Connection

from alembic import context
from app.core.config import get_settings
from app.domain import models  # noqa: F401
from app.storage.db import Base

config = context.config

if not config.get_main_option("sqlalchemy.url"):
    settings = get_settings()
    settings.ensure_dirs()
    config.set_main_option("sqlalchemy.url", f"sqlite:///{settings.db_path}")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection")
    if connectable is None:
        from sqlalchemy import create_engine

        url = config.get_main_option("sqlalchemy.url")
        if url is None:
            raise RuntimeError("sqlalchemy.url not configured")
        connectable = create_engine(url, poolclass=pool.NullPool)
    if isinstance(connectable, Connection):
        do_run_migrations(connectable)
    else:
        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
