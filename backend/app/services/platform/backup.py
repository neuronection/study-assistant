import json
import re
import sqlite3
import threading
import zipfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from ... import __version__

MANIFEST_NAME = "manifest.json"
DB_NAME = "database.sqlite"
BLOBS_PREFIX = "blobs/"
BACKUP_FORMAT = "ca-backup/v1"
STAMP_PATTERN = re.compile(r"^(auto|manual)-(\d{8}-\d{6})\.zip$")


class BackupError(Exception):
    pass


@dataclass
class EffectiveBackupSettings:
    auto: bool
    interval_hours: int
    keep_daily: int
    keep_weekly: int
    sync_dir: str | None


@dataclass
class BackupSettingsOverride:
    auto: bool | None = None
    interval_hours: int | None = None
    keep_daily: int | None = None
    keep_weekly: int | None = None
    sync_dir: str | None = None


def _settings_path(settings_dir: Path) -> Path:
    return settings_dir / "backup-settings.json"


def load_effective_settings(
    defaults: EffectiveBackupSettings, settings_dir: Path
) -> EffectiveBackupSettings:
    path = _settings_path(settings_dir)
    if not path.is_file():
        return defaults
    try:
        raw = json.loads(path.read_text())
    except ValueError:
        return defaults
    fields = asdict(defaults)
    for key in fields:
        if key in raw and raw[key] is not None:
            fields[key] = raw[key]
    fields["sync_dir"] = fields["sync_dir"] or None
    return EffectiveBackupSettings(**fields)


def store_settings_override(
    override: BackupSettingsOverride, settings_dir: Path
) -> EffectiveBackupSettings:
    path = _settings_path(settings_dir)
    current: dict[str, Any] = {}
    if path.is_file():
        with suppress(ValueError):
            current = json.loads(path.read_text())
    for key, value in asdict(override).items():
        if value is not None:
            current[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2))
    return load_effective_settings(
        EffectiveBackupSettings(
            auto=True, interval_hours=24, keep_daily=14, keep_weekly=8, sync_dir=None
        ),
        settings_dir,
    )


def _snapshot_database(db_path: Path) -> bytes:
    target = db_path.with_suffix(".snapshot.db")
    source = sqlite3.connect(str(db_path))
    try:
        backup = sqlite3.connect(str(target))
        try:
            source.backup(backup)
            backup.execute("PRAGMA journal_mode=DELETE")
            backup.commit()
        finally:
            backup.close()
    finally:
        source.close()
    data = target.read_bytes()
    target.unlink(missing_ok=True)
    return data


def build_backup(db_path: Path, blobs_dir: Path) -> bytes:
    manifest = {
        "format": BACKUP_FORMAT,
        "app_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
    }
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest))
        archive.writestr(DB_NAME, _snapshot_database(db_path))
        blobs = Path(blobs_dir)
        if blobs.is_dir():
            for path in sorted(blobs.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(blobs).as_posix()
                    archive.writestr(f"{BLOBS_PREFIX}{rel}", path.read_bytes())
    return buffer.getvalue()


def read_archive(data: bytes) -> tuple[bytes, dict[str, bytes]]:
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as error:
        raise BackupError("not a backup archive") from error
    names = archive.namelist()
    if MANIFEST_NAME not in names or DB_NAME not in names:
        raise BackupError("backup archive is incomplete")
    try:
        manifest = json.loads(archive.read(MANIFEST_NAME))
    except ValueError as error:
        raise BackupError("unreadable manifest") from error
    if manifest.get("format") != BACKUP_FORMAT:
        raise BackupError("unsupported backup format")
    database = archive.read(DB_NAME)
    blobs: dict[str, bytes] = {}
    for name in names:
        if name.startswith(BLOBS_PREFIX) and not name.endswith("/"):
            blobs[name[len(BLOBS_PREFIX) :]] = archive.read(name)
    return database, blobs


def database_is_healthy(database: bytes) -> bool:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as handle:
        handle.write(database)
        handle.flush()
        try:
            connection = sqlite3.connect(handle.name)
        except sqlite3.DatabaseError:
            return False
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                return False
            version = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            return version is not None
        except sqlite3.DatabaseError:
            return False
        finally:
            connection.close()


def validate_backup_file(path: Path) -> bool:
    try:
        database, _blobs = read_archive(path.read_bytes())
    except (BackupError, OSError):
        return False
    return database_is_healthy(database)


def create_backup(
    db_path: Path,
    blobs_dir: Path,
    target_dir: Path,
    prefix: str = "auto",
    now: datetime | None = None,
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    path = target_dir / f"{prefix}-{stamp}.zip"
    data = build_backup(db_path, blobs_dir)
    path.write_bytes(data)
    if not validate_backup_file(path):
        path.unlink(missing_ok=True)
        raise BackupError("backup failed validation after write")
    return path


def _parse_stamp(path: Path) -> datetime | None:
    match = STAMP_PATTERN.match(path.name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(2), "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def apply_retention(
    target_dir: Path, keep_daily: int, keep_weekly: int
) -> list[Path]:
    if not target_dir.is_dir():
        return []
    stamped = sorted(
        ((path, stamp) for path in target_dir.iterdir() if (stamp := _parse_stamp(path))),
        key=lambda entry: entry[1],
        reverse=True,
    )
    keep: set[Path] = {path for path, _ in stamped[: max(0, keep_daily)]}
    weekly: dict[tuple[int, int], Path] = {}
    for path, stamp in stamped[max(0, keep_daily) :]:
        week = (stamp.isocalendar()[0], stamp.isocalendar()[1])
        weekly.setdefault(week, path)
    for week in list(weekly)[: max(0, keep_weekly)]:
        keep.add(weekly[week])
    removed: list[Path] = []
    for path, _stamp in stamped:
        if path not in keep:
            with suppress(OSError):
                path.unlink()
            removed.append(path)
    return removed


def list_backups(target_dir: Path) -> list[dict[str, Any]]:
    if not target_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in target_dir.iterdir():
        stamp = _parse_stamp(path)
        if stamp is None:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        entries.append(
            {"name": path.name, "size": size, "created_at": stamp.isoformat()}
        )
    entries.sort(key=lambda entry: entry["created_at"], reverse=True)
    return entries


def last_backup_time(target_dir: Path) -> datetime | None:
    stamps = [
        stamp for path in target_dir.iterdir() if (stamp := _parse_stamp(path))
    ] if target_dir.is_dir() else []
    return max(stamps) if stamps else None


def sync_to_dir(path: Path, sync_dir: Path) -> Path:
    sync_dir.mkdir(parents=True, exist_ok=True)
    target = sync_dir / path.name
    temp = sync_dir / f".{path.name}.part"
    temp.write_bytes(path.read_bytes())
    temp.replace(target)
    return target


def _corrupt_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def boot_integrity_check(
    db_path: Path, backups_dir: Path, blobs_dir: Path
) -> dict[str, Any] | None:
    def database_ok(path: Path) -> bool:
        try:
            connection = sqlite3.connect(str(path))
        except sqlite3.DatabaseError:
            return False
        try:
            row = connection.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        except sqlite3.DatabaseError:
            return False
        finally:
            connection.close()

    if db_path.exists() and database_ok(db_path):
        return None

    recovery: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(),
        "from_backup": None,
    }
    if db_path.exists():
        quarantine = db_path.with_name(f"corrupt-{_corrupt_stamp()}.db")
        with suppress(OSError):
            db_path.replace(quarantine)
        for sidecar in ("-wal", "-shm"):
            with suppress(OSError):
                db_path.with_name(db_path.name + sidecar).unlink()
        recovery["quarantined"] = quarantine.name

    candidates = []
    if backups_dir.is_dir():
        for path in backups_dir.iterdir():
            if _parse_stamp(path) is not None:
                candidates.append(path)
    candidates.sort(key=lambda path: path.name, reverse=True)
    for candidate in candidates:
        try:
            database, blobs = read_archive(candidate.read_bytes())
        except (BackupError, OSError):
            continue
        if not database_is_healthy(database):
            continue
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(database)
        for rel, data in blobs.items():
            target = blobs_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        recovery["from_backup"] = candidate.name
        break

    recovery_path = backups_dir.parent / "last-recovery.json"
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.write_text(json.dumps(recovery, indent=2))
    return recovery


class BackupScheduler:
    def __init__(
        self,
        settings_provider: Callable[[], EffectiveBackupSettings],
        db_path: Path,
        blobs_dir: Path,
        backups_dir: Path,
        publish: Callable[[str, dict[str, Any]], None] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        startup_delay_sec: float = 60.0,
    ) -> None:
        self._settings_provider = settings_provider
        self._db_path = Path(db_path)
        self._blobs_dir = Path(blobs_dir)
        self._backups_dir = Path(backups_dir)
        self._publish = publish
        self._clock = clock
        self._startup_delay = startup_delay_sec
        self._stop = threading.Event()
        self._cycle = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="backup-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._cycle.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def wake(self) -> None:
        self._cycle.set()

    def _run(self) -> None:
        self._stop.wait(self._startup_delay)
        while not self._stop.is_set():
            effective = self._settings_provider()
            if effective.auto:
                with suppress(Exception):
                    self.run_once(prefix="auto")
                self._stop.wait(self._check_interval_sec(effective))
            else:
                self._cycle.wait(30)
                self._cycle.clear()

    @staticmethod
    def _check_interval_sec(effective: EffectiveBackupSettings) -> float:
        return max(300.0, effective.interval_hours * 3600 / 2)

    def run_once(self, prefix: str = "auto") -> Path | None:
        effective = self._settings_provider()
        if prefix == "auto" and not effective.auto:
            return None
        if prefix == "auto":
            latest = last_backup_time(self._backups_dir)
            if latest is not None:
                due_after = latest + timedelta(hours=effective.interval_hours)
                if self._clock() < due_after:
                    return None
        with self._lock:
            path = create_backup(
                self._db_path,
                self._blobs_dir,
                self._backups_dir,
                prefix=prefix,
                now=self._clock(),
            )
            apply_retention(
                self._backups_dir, effective.keep_daily, effective.keep_weekly
            )
            if effective.sync_dir:
                sync_dir = Path(effective.sync_dir).expanduser()
                sync_to_dir(path, sync_dir)
                apply_retention(sync_dir, effective.keep_daily, effective.keep_weekly)
        if self._publish is not None:
            self._publish(
                "backups",
                {"event": "created", "name": path.name, "prefix": prefix},
            )
        return path
