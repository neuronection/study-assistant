import contextlib
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..domain.models import Material, MaterialSource
from ..jobs.runner import JobRunner
from .sources import SourcesError, SourcesService


class ScanScheduler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        blobs_dir: Path,
        jobs: JobRunner,
        publish: Callable[[str, dict[str, Any]], None],
        interval_sec: int = 300,
        startup_delay_sec: float = 5.0,
    ) -> None:
        self._session_factory = session_factory
        self._blobs_dir = Path(blobs_dir)
        self._jobs = jobs
        self._publish = publish
        self._interval = interval_sec
        self._startup_delay = startup_delay_sec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cycle = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="source-scanner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._cycle.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        self._stop.wait(self._startup_delay)
        while not self._stop.is_set():
            with contextlib.suppress(Exception):
                self.scan_all()
            self._cycle.wait(self._interval)

    def wake(self) -> None:
        self._cycle.set()

    def scan_all(self, *, force: bool = False) -> dict[int, dict[str, int]]:
        results: dict[int, dict[str, int]] = {}
        now = datetime.now(UTC)
        with self._session_factory() as session:
            sources = list(
                session.scalars(
                    select(MaterialSource).where(MaterialSource.enabled.is_(True))
                )
            )
            due: list[tuple[int, int]] = []
            for source in sources:
                if force or source.last_scanned_at is None:
                    due.append((source.profile_id, source.id))
                    continue
                interval = source.scan_interval_sec or self._interval
                if source.last_scanned_at + timedelta(seconds=interval) <= now:
                    due.append((source.profile_id, source.id))
        for profile_id, source_id in due:
            stats = self._scan_one(profile_id, source_id)
            if stats is not None:
                results[source_id] = stats
        return results

    def _scan_one(self, profile_id: int, source_id: int) -> dict[str, int] | None:
        try:
            with self._session_factory() as session:
                service = SourcesService(session, self._blobs_dir)
                stats = service.scan(profile_id, source_id)
                pending = list(
                    session.scalars(
                        select(Material.id).where(
                            Material.source_id == source_id,
                            Material.status == "pending",
                        )
                    )
                )
                for material_id in pending:
                    JobRunner.enqueue(session, "ingest", {"material_id": material_id})
                session.commit()
        except (SourcesError, OSError, ValueError):
            with (
                contextlib.suppress(Exception),
                self._session_factory() as session,
            ):
                session.rollback()
                source = session.get(MaterialSource, source_id)
                if source is not None and source.last_scan_error is None:
                    source.last_scan_error = "scan failed"
                    session.commit()
            return None
        self._jobs.wake()
        self._publish(f"source:{source_id}", {"event": "scanned", **stats})
        return stats
