import sqlite3
import threading
import time
from pathlib import Path

import sqlite_vec
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

__all__ = ["Base", "Engine", "make_engine", "make_session_factory"]

_WAL_ATTEMPTS = 10
_WAL_RETRY_SEC = 0.25
# journal_mode is a file-level property; the first-connect switch is the
# only write in the pragma listener, and concurrent first connects race
# it (SQLAlchemy pools open several at once — app startup + background
# job runners). Serialize it in-process; across processes the busy
# timeout + retries below cover the rest.
_WAL_SWITCH_LOCK = threading.Lock()


class Base(DeclarativeBase):
    pass


def make_engine(db_path: Path | str) -> Engine:
    """Engine for either datastore (ADR-0022): SQLite (desktop + tests)
    gets the desktop pragmas and sqlite-vec; PostgreSQL 16 (web/server)
    gets pre-ping pooling."""
    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
    else:
        url = db_path
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA busy_timeout=30000")
        # WAL is a file-level property — skip the switch when the database
        # already is WAL (or is :memory:, which never can be): the switch
        # is a write, and racing it across the pool's first connects can
        # exhaust the retry budget under load ("database is locked").
        current = cursor.execute("PRAGMA journal_mode").fetchone()
        if current is None or str(current[0]).lower() not in ("wal", "memory"):
            with _WAL_SWITCH_LOCK:
                for attempt in range(_WAL_ATTEMPTS):
                    try:
                        result = cursor.execute("PRAGMA journal_mode=WAL").fetchone()
                    except sqlite3.OperationalError:
                        if attempt == _WAL_ATTEMPTS - 1:
                            raise
                        time.sleep(_WAL_RETRY_SEC)
                        continue
                    if result is not None and str(result[0]).lower() in ("wal", "memory"):
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
