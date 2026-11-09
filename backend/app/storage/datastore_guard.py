"""One-time datastore break gate (family contract: datastore-breaks.md).

Deliberate schema breaks (0.13) do not migrate and never delete user data.
The first boot of the new line moves the old datastore aside, creates a
fresh one, and leaves a marker the UI renders as a one-time notice.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core.config import Settings

CONTRACT_FORMAT = "nx-datastore-quarantine/v1"
PRODUCT = "study-assistant"
FOLDER_PREFIX = "previous-datastore-"
MANIFEST_NAME = "manifest.json"
MARKER_NAME = "datastore-quarantine.json"

FRESH = "fresh"
CURRENT = "current"
PREVIOUS = "previous"
UNREADABLE = "unreadable"

_REASON_SCHEMA = "incompatible-schema"
_REASON_UNREADABLE = "unreadable"


class DatastoreQuarantineError(RuntimeError):
    """The old datastore could not be moved aside; refuse rather than risk it."""


@dataclass(frozen=True)
class QuarantineNotice:
    path: str
    reason: str
    quarantined_at: str
    schema_revision: str | None = None
    from_version: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": CONTRACT_FORMAT,
            "product": PRODUCT,
            "path": self.path,
            "reason": self.reason,
            "quarantined_at": self.quarantined_at,
            "schema_revision": self.schema_revision,
            "from_version": self.from_version,
        }


def _probe(db_path: Path, known: frozenset[str]) -> tuple[str, str | None]:
    try:
        if not db_path.exists() or db_path.stat().st_size == 0:
            return FRESH, None
    except OSError:
        return UNREADABLE, None
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.DatabaseError:
        return UNREADABLE, None
    try:
        try:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.DatabaseError:
            row = None
        revision = str(row[0]) if row else None
        if revision is not None:
            return (CURRENT if revision in known else PREVIOUS), revision
        tables = [
            str(entry[0])
            for entry in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return (PREVIOUS if tables else FRESH), None
    except sqlite3.DatabaseError:
        return UNREADABLE, None
    finally:
        connection.close()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def quarantine(
    settings: Settings,
    *,
    reason: str,
    schema_revision: str | None,
) -> QuarantineNotice:
    """Move the old datastore aside (atomic rename) and mark the new boot."""
    data_dir = settings.data_dir
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    folder = data_dir / f"{FOLDER_PREFIX}{stamp}"
    suffix = 1
    while folder.exists():
        folder = data_dir / f"{FOLDER_PREFIX}{stamp}-{suffix}"
        suffix += 1
    databases = (settings.db_path, settings.checkpoints_path)
    sources = [
        item
        for database in databases
        for item in (
            database,
            database.with_name(database.name + "-wal"),
            database.with_name(database.name + "-shm"),
        )
    ]
    sources += [settings.blobs_dir, settings.backups_dir]
    sources = [source for source in sources if source.exists()]
    folder.mkdir(parents=True)
    moved: list[Path] = []
    try:
        for source in sources:
            os.replace(source, folder / source.name)
            moved.append(source)
    except OSError as error:
        for source in reversed(moved):
            with contextlib.suppress(OSError):
                os.replace(folder / source.name, source)
        with contextlib.suppress(OSError):
            folder.rmdir()
        raise DatastoreQuarantineError(
            "The previous datastore could not be moved aside. Close any other "
            f"Study Assistant instance, check permissions for {data_dir}, then "
            f"relaunch. ({error})"
        ) from error
    quarantined_at = datetime.now(UTC).isoformat()
    manifest = {
        "format": CONTRACT_FORMAT,
        "product": PRODUCT,
        "reason": reason,
        "schema_revision": schema_revision,
        "from_version": None,
        "quarantined_at": quarantined_at,
        "items": sorted(path.name for path in moved),
    }
    _write_json(folder / MANIFEST_NAME, manifest)
    notice = QuarantineNotice(
        path=str(folder),
        reason=reason,
        quarantined_at=quarantined_at,
        schema_revision=schema_revision,
    )
    _write_json(data_dir / MARKER_NAME, notice.as_dict())
    return notice


def guard_datastore(settings: Settings) -> QuarantineNotice | None:
    """Quarantine a pre-0.13 SQLite datastore; SQLite only (PG is ops-owned)."""
    if not settings.db_url.startswith("sqlite"):
        return None
    from ..local import known_revisions

    state, revision = _probe(settings.db_path, known_revisions())
    if state in (FRESH, CURRENT):
        return None
    return quarantine(
        settings,
        reason=_REASON_UNREADABLE if state == UNREADABLE else _REASON_SCHEMA,
        schema_revision=revision,
    )


def read_marker(data_dir: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((data_dir / MARKER_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("format") != CONTRACT_FORMAT:
        return None
    return payload
