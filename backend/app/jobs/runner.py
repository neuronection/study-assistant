import threading
from collections.abc import Callable
from typing import Any, cast

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from ..core.events import EventBus
from ..core.vocab import JobStatus, JobType, WsTopic
from ..domain.models import Job, utcnow
from .cancellation import (
    CANCELLED_ERROR,
    JobCancelled,
    clear_cancel,
    is_cancel_requested,
)
from .payloads import (
    ChatTurnPayload,
    DrawingOcrPayload,
    IngestPayload,
    PostprocessPayload,
)

logger = structlog.get_logger(__name__)

ProgressReporter = Callable[[int, str], None]
JobHandler = Callable[[Session, Job, ProgressReporter], None]
GroupKey = Callable[[Job], str | None]

INTERRUPTED_ERROR = (
    "interrupted: the backend restarted before this job finished — please retry"
)


class JobError(Exception):
    pass


class JobRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        bus: EventBus,
        handlers: dict[str, JobHandler],
        poll_interval: float = 0.2,
        workers: int = 4,
        job_timeout_sec: float | None = None,
        group_key: GroupKey | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._bus = bus
        self._handlers = handlers
        self._poll_interval = poll_interval
        self._workers = max(1, workers)
        self._job_timeout_sec = job_timeout_sec
        self._group_key = group_key
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._threads:
            return
        reclaimed = self._reclaim_interrupted()
        if reclaimed:
            logger.warning(
                "reclaimed_interrupted_jobs",
                count=reclaimed,
            )
        for index in range(self._workers):
            thread = threading.Thread(
                target=self._run, name=f"job-worker-{index}", daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads = []

    def wake(self) -> None:
        self._wake.set()

    def has_handler(self, job_type: str) -> bool:
        return job_type in self._handlers

    def retriable_handlers(self) -> frozenset[str]:
        return frozenset(self._handlers) - {JobType.CHAT_TURN}

    def publish_progress(self, job_id: int, progress: int, stage: str, status: str) -> None:
        self._bus.publish_threadsafe(
            WsTopic.jobs(job_id), {"progress": progress, "stage": stage, "status": status}
        )

    def _reclaim_interrupted(self) -> int:
        with self._session_factory() as session:
            result = session.execute(
                update(Job)
                .where(Job.status == "running")
                .values(status=JobStatus.FAILED, error=INTERRUPTED_ERROR, finished_at=utcnow())
            )
            session.commit()
            return int(cast(Any, result).rowcount or 0)

    def _group_of(self, job: Job) -> str | None:
        if self._group_key is None:
            return None
        try:
            return self._group_key(job)
        except Exception:
            return None

    def _blocked_by_group(self, session: Session, job: Job) -> bool:
        group = self._group_of(job)
        if group is None:
            return False
        earlier = session.scalars(
            select(Job)
            .where(
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                Job.id < job.id,
                Job.type == job.type,
            )
            .order_by(Job.id)
            .limit(100)
        ).all()
        return any(self._group_of(other) == group for other in earlier)

    def _claim_next(self) -> Job | None:
        with self._session_factory() as session:
            candidates = session.scalars(
                select(Job)
                .where(Job.status == JobStatus.QUEUED)
                .order_by(Job.id)
                .limit(25)
            ).all()
            for job in candidates:
                if self._blocked_by_group(session, job):
                    continue
                claimed = session.execute(
                    update(Job)
                    .where(Job.id == job.id, Job.status == JobStatus.QUEUED)
                    .values(status="running", started_at=utcnow())
                )
                session.commit()
                if not bool(cast(Any, claimed).rowcount):
                    continue
                session.refresh(job)
                session.expunge(job)
                return job
            return None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._claim_next()
            except Exception as error:
                logger.exception("job_claim_failed", error=str(error))
                self._wake.wait(self._poll_interval)
                self._wake.clear()
                continue
            if job is None:
                self._wake.wait(self._poll_interval)
                self._wake.clear()
                continue
            self._execute(job)

    def _execute(self, job: Job) -> None:
        self.publish_progress(job.id, job.progress or 0, job.stage or "", "running")
        handler_thread = threading.Thread(
            target=self._run_handler,
            args=(job.id, job.type),
            name=f"job-{job.id}",
            daemon=True,
        )
        handler_thread.start()
        if self._job_timeout_sec is None:
            handler_thread.join()
            return
        handler_thread.join(timeout=self._job_timeout_sec)
        if handler_thread.is_alive():
            logger.error(
                "job_timed_out",
                job_id=job.id,
                job_type=job.type,
                timeout_sec=self._job_timeout_sec,
            )
            self._mark_failed(
                job.id, f"timed out after {int(self._job_timeout_sec)}s"
            )

    def _run_handler(self, job_id: int, job_type: str) -> None:
        handler = self._handlers.get(job_type)
        try:
            if is_cancel_requested(job_id):
                self._mark_cancelled(job_id, CANCELLED_ERROR)
                return
            with self._session_factory() as session:
                job_row = session.get(Job, job_id)
                if job_row is None:
                    return
                if job_row.status != JobStatus.RUNNING:
                    return

                def report(progress: int, stage: str) -> None:
                    if is_cancel_requested(job_id):
                        raise JobCancelled(CANCELLED_ERROR)
                    job_row.progress = max(0, min(100, progress))
                    job_row.stage = stage
                    session.commit()
                    self.publish_progress(job_id, progress, stage, "running")

                try:
                    if handler is None:
                        raise JobError(f"no handler registered for job type '{job_type}'")
                    handler(session, job_row, report)
                    session.expire(job_row, ["status", "progress", "stage", "finished_at"])
                    if job_row.status == JobStatus.RUNNING:
                        job_row.status = JobStatus.DONE
                        job_row.progress = 100
                        job_row.finished_at = utcnow()
                        session.commit()
                        self.publish_progress(job_id, 100, job_row.stage or "", "done")
                        logger.info("job_done", job_id=job_id, job_type=job_type)
                except JobCancelled:
                    session.rollback()
                    self._mark_cancelled(job_id, CANCELLED_ERROR)
                except Exception as error:
                    session.rollback()
                    logger.exception(
                        "job_failed", job_id=job_id, job_type=job_type, error=str(error)
                    )
                    self._mark_failed(job_id, str(error))
        except Exception as error:
            logger.exception(
                "job_handler_setup_failed", job_id=job_id, error=str(error)
            )
            self._mark_failed(job_id, str(error))
        finally:
            clear_cancel(job_id)

    def _mark_cancelled(self, job_id: int, error: str) -> None:
        with self._session_factory() as session:
            cancelled = session.get(Job, job_id)
            if cancelled is None:
                return
            if cancelled.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
                return
            cancelled.status = JobStatus.CANCELLED
            cancelled.error = str(error)[:4000]
            cancelled.finished_at = utcnow()
            session.commit()
            self._bus.publish_threadsafe(
                WsTopic.jobs(job_id),
                {
                    "progress": cancelled.progress or 0,
                    "stage": "cancelled",
                    "status": JobStatus.CANCELLED,
                },
            )
            logger.info("job_cancelled", job_id=job_id)

    def _mark_failed(self, job_id: int, error: str) -> None:
        with self._session_factory() as session:
            failed = session.get(Job, job_id)
            if failed is None:
                return
            failed.status = JobStatus.FAILED
            failed.error = str(error)[:4000]
            failed.finished_at = utcnow()
            session.commit()
            self._bus.publish_threadsafe(
                WsTopic.jobs(job_id),
                {
                    "progress": failed.progress or 0,
                    "stage": "failed",
                    "status": JobStatus.FAILED,
                    "error": str(error)[:500],
                },
            )

    @staticmethod
    def enqueue(
        session: Session,
        job_type: str,
        payload: IngestPayload | PostprocessPayload | ChatTurnPayload | DrawingOcrPayload,
    ) -> Job:
        job = Job(type=job_type, payload=dict(payload), status=JobStatus.QUEUED, progress=0)
        session.add(job)
        session.flush()
        return job
