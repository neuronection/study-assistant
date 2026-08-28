import sqlite3
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError as SAOperationalError

from app.storage.db import make_engine


def _seed_delete_mode_db(db_path: Path) -> sqlite3.Connection:
    holder = sqlite3.connect(db_path, check_same_thread=False)
    holder.execute("PRAGMA journal_mode=DELETE")
    holder.execute("CREATE TABLE t (x INTEGER)")
    holder.execute("INSERT INTO t VALUES (1)")
    holder.commit()
    return holder


def _hold_write_lock_then_commit_after(
    holder: sqlite3.Connection, seconds: float
) -> threading.Thread:
    holder.execute("BEGIN IMMEDIATE")

    def unlock() -> None:
        time.sleep(seconds)
        holder.commit()

    thread = threading.Thread(target=unlock)
    thread.start()
    return thread


def test_engine_connect_converts_locked_database_to_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "busy.db"
    holder = _seed_delete_mode_db(db_path)
    thread = _hold_write_lock_then_commit_after(holder, 0.6)
    try:
        engine = make_engine(db_path)
        with engine.connect() as connection:
            mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
    finally:
        thread.join()
        holder.close()
    assert str(mode).lower() == "wal"


def test_engine_connect_sets_wal_and_busy_timeout(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "fresh.db")
    with engine.connect() as connection:
        mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert str(mode).lower() == "wal"
    assert int(str(busy_timeout)) == 30000
    assert int(str(foreign_keys)) == 1


def test_engine_connect_gives_up_after_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "stuck.db"
    holder = _seed_delete_mode_db(db_path)
    holder.execute("BEGIN IMMEDIATE")
    monkeypatch.setattr("app.storage.db._WAL_ATTEMPTS", 2)
    monkeypatch.setattr("app.storage.db._WAL_RETRY_SEC", 0.05)
    try:
        engine = make_engine(db_path)
        with pytest.raises(SAOperationalError, match="database is locked"):
            engine.connect().close()
    finally:
        holder.commit()
        holder.close()
