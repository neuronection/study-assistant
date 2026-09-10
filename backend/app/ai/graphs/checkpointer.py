"""Dialect-picked LangGraph checkpointer (dual-mode, plan 10 §5.1).

Desktop mode runs SQLite (`AsyncSqliteSaver` on `data_dir/checkpoints.db`);
server mode picks Postgres (`AsyncPostgresSaver`) when the engine dialect is
postgresql and a URI is provided. The saver is opened once in the app lifespan
and held for the whole process; `setup()` runs at boot so the checkpoint
tables exist before the first graph turn.

`prune_checkpoints` is the day-one retention beat: checkpoint rows grow
unboundedly, so boot pruning removes threads whose checkpoints are older than
the TTL (same precedent as `prune_done_jobs`). Checkpoint ids are UUIDv6 —
the first 12 hex chars are the top 48 bits of the 100 ns Gregorian timestamp,
so a zero-padded hex prefix compares lexicographically by time.
"""

import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

_GREGORIAN_100NS = 122192928000000000
_MS_PER_100NS = 10_000


@asynccontextmanager
async def open_checkpointer(
    dialect: str,
    sqlite_path: Path,
    postgres_uri: str | None = None,
) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    if dialect == "postgresql":
        if postgres_uri is None:
            raise ValueError(
                "postgres checkpointing needs a database uri (got none)"
            )
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(postgres_uri) as saver:
            await saver.setup()
            yield saver
    else:
        async with AsyncSqliteSaver.from_conn_string(str(sqlite_path)) as saver:
            await saver.setup()
            yield saver


def _stale_prefix(now_ms: int, ttl_days: int) -> str:
    cutoff_100ns = (now_ms - ttl_days * 86_400_000) * _MS_PER_100NS + _GREGORIAN_100NS
    return f"{cutoff_100ns >> 12:012x}"


def prune_checkpoints(db_path: Path, ttl_days: int, now_ms: int | None = None) -> int:
    """Delete checkpoint threads whose latest write is older than the TTL.

    Returns the number of checkpoint rows removed. Orphaned `writes` rows are
    dropped with it. No-op when the checkpoint database does not exist yet.
    """
    if not db_path.exists():
        return 0
    prefix = _stale_prefix(now_ms if now_ms is not None else int(time.time() * 1000), ttl_days)
    connection = sqlite3.connect(db_path)
    try:
        stale = (
            "select thread_id || checkpoint_ns from checkpoints "
            "group by thread_id, checkpoint_ns "
            "having max(replace(checkpoint_id, '-', '')) < ?"
        )
        cursor = connection.execute(
            f"delete from checkpoints where thread_id || checkpoint_ns in ({stale})",
            (prefix,),
        )
        deleted = cursor.rowcount
        connection.execute(
            "delete from writes where not exists ("
            "select 1 from checkpoints c where c.thread_id = writes.thread_id "
            "and c.checkpoint_ns = writes.checkpoint_ns "
            "and c.checkpoint_id = writes.checkpoint_id)"
        )
        connection.commit()
        return deleted
    finally:
        connection.close()
