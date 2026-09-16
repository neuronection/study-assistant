import contextlib
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ...core.vocab import WsTopic
from ...domain.models import ExternalSource, utcnow
from ..content.external_sources import effective_interval, run_scan

_SCHEDULER_TICK_SEC = 300


def _utc_naive() -> datetime:
    """SQLite stores naive datetimes — compare naive on both sides."""
    return datetime.now(UTC).replace(tzinfo=None)


class ExternalSourceScheduler:
    """Due-time loop over enabled external sources (plan 73-E).

    Same shape as ScanScheduler (startup pass + periodic tick, per-source
    error isolation) plus an overlap guard: a source already mid-scan is
    skipped on the next due tick — a slow feed or hung yt-dlp invocation
    must never stack concurrent scans of the same source.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        publish: Callable[[str, dict[str, Any]], None],
        interval_sec: int = _SCHEDULER_TICK_SEC,
        startup_delay_sec: float = 5.0,
    ) -> None:
        self._session_factory = session_factory
        self._publish = publish
        self._interval = interval_sec
        self._startup_delay = startup_delay_sec
        self._stop = threading.Event()
        self._cycle = threading.Event()
        self._thread: threading.Thread | None = None
        self._in_flight: set[int] = set()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="external-source-scanner", daemon=True
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
            with contextlib.suppress(Exception):
                self.scan_all()
            self._cycle.wait(self._interval)

    def scan_all(self, *, now: datetime | None = None) -> dict[int, dict[str, int]]:
        current = now or _utc_naive()
        with self._session_factory() as session:
            sources = list(
                session.scalars(
                    select(ExternalSource).where(
                        ExternalSource.enabled.is_(True)
                    )
                )
            )
            due = [
                source.id
                for source in sources
                if source.last_scanned_at is None
                or source.last_scanned_at
                + timedelta(seconds=effective_interval(source))
                <= current
            ]
        results: dict[int, dict[str, int]] = {}
        for source_id in due:
            stats = self._scan_one(source_id)
            if stats is not None:
                results[source_id] = stats
        return results

    def _scan_one(self, source_id: int) -> dict[str, int] | None:
        if source_id in self._in_flight:
            return None
        self._in_flight.add(source_id)
        try:
            with self._session_factory() as session:
                source = session.get(ExternalSource, source_id)
                if source is None or not source.enabled:
                    return None
                try:
                    stats = run_scan(session, source)
                    session.commit()
                except Exception as error:
                    session.rollback()
                    with contextlib.suppress(Exception):
                        dead = session.get(ExternalSource, source_id)
                        if dead is not None:
                            dead.last_scan_error = str(error)[:500]
                            dead.last_scanned_at = utcnow()
                            session.commit()
                    self._publish(
                        WsTopic.externalsource(source_id),
                        {"event": "scan_failed", "error": str(error)[:300]},
                    )
                    return None
        finally:
            self._in_flight.discard(source_id)
        self._publish(WsTopic.externalsource(source_id), {"event": "scanned", **stats})
        return stats
