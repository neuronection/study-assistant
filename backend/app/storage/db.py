import sqlite3
import time
from pathlib import Path

import sqlite_vec
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

__all__ = ["Base", "Engine", "make_engine", "make_session_factory"]

_WAL_ATTEMPTS = 10
_WAL_RETRY_SEC = 0.25


class Base(DeclarativeBase):
    pass


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA busy_timeout=30000")
        for attempt in range(_WAL_ATTEMPTS):
            try:
                result = cursor.execute("PRAGMA journal_mode=WAL").fetchone()
            except sqlite3.OperationalError:
                if attempt == _WAL_ATTEMPTS - 1:
                    raise
                time.sleep(_WAL_RETRY_SEC)
                continue
            if result is not None and str(result[0]).lower() == "wal":
                break
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
        dbapi_connection.enable_load_extension(True)  # type: ignore[attr-defined]
        sqlite_vec.load(dbapi_connection)
        dbapi_connection.enable_load_extension(False)  # type: ignore[attr-defined]

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
