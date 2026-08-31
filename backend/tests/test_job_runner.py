import time
from pathlib import Path
from typing import Any, cast

from alembic.config import Config
from sqlalchemy.orm import Session

from alembic import command
from app.core.events import EventBus
from app.domain.models import Job
from app.jobs.payloads import IngestPayload
from app.jobs.runner import GroupKey, JobError, JobHandler, JobRunner
from app.storage.db import make_engine, make_session_factory


def make_runner(
    tmp_path: Path,
    handler: JobHandler,
    workers: int = 1,
    job_timeout_sec: float | None = None,
    group_key: GroupKey | None = None,
) -> tuple[JobRunner, EventBus]:
    db_path = tmp_path / "runner.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, "head")
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    bus = EventBus()
    return (
        JobRunner(
            factory,
            bus,
            handlers={"noop": handler},
            poll_interval=0.02,
            workers=workers,
            job_timeout_sec=job_timeout_sec,
            group_key=group_key,
        ),
        bus,
    )


def wait_until(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met before timeout")


def job_status(runner: JobRunner, job_id: int) -> str:
    with runner._session_factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job.status


def job_error(runner: JobRunner, job_id: int) -> str | None:
    with runner._session_factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job.error


def enqueue(runner: JobRunner, job_type: str, payload: dict[str, Any]) -> int:
    with runner._session_factory() as session:
        job = JobRunner.enqueue(session, job_type, cast("IngestPayload", payload))
        session.commit()
        return job.id


def test_runner_executes_handler_and_marks_done(tmp_path: Path) -> None:
    seen: list[int] = []

    def handler(session: Session, job: Job, report: Any) -> None:
        seen.append(job.id)
        report(50, "halfway")

    runner, _bus = make_runner(tmp_path, handler)
    job_id = enqueue(runner, "noop", {"x": 1})
    runner.start()
    try:
        wait_until(lambda: job_status(runner, job_id) == "done")
    finally:
        runner.stop()
    assert seen == [job_id]


def test_runner_marks_failure_with_error(tmp_path: Path) -> None:
    def handler(session: Session, job: Job, report: Any) -> None:
        raise JobError("boom")

    runner, _bus = make_runner(tmp_path, handler)
    job_id = enqueue(runner, "noop", {})
    runner.start()
    try:
        wait_until(lambda: job_status(runner, job_id) == "failed")
        assert job_error(runner, job_id) == "boom"
    finally:
        runner.stop()


def test_runner_unknown_type_fails(tmp_path: Path) -> None:
    def handler(session: Session, job: Job, report: Any) -> None:
        raise AssertionError("should not run")

    runner, _bus = make_runner(tmp_path, handler)
    job_id = enqueue(runner, "mystery", {})
    runner.start()
    try:
        wait_until(lambda: job_status(runner, job_id) == "failed")
        assert "no handler" in (job_error(runner, job_id) or "")
    finally:
        runner.stop()


def test_runner_survives_handler_crash_and_runs_next(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(session: Session, job: Job, report: Any) -> None:
        calls.append(job.id)
        if len(calls) == 1:
            raise RuntimeError("worker crash")

    runner, _bus = make_runner(tmp_path, handler)
    first = enqueue(runner, "noop", {})
    second = enqueue(runner, "noop", {})
    runner.start()
    try:
        wait_until(lambda: job_status(runner, second) == "done")
        assert job_status(runner, first) == "failed"
    finally:
        runner.stop()
    assert calls == [first, second]


def test_runner_reclaims_interrupted_running_jobs_on_start(tmp_path: Path) -> None:
    seen: list[int] = []

    def handler(session: Session, job: Job, report: Any) -> None:
        seen.append(job.id)

    runner, _bus = make_runner(tmp_path, handler)
    stale_id = enqueue(runner, "noop", {})
    fresh_id = enqueue(runner, "noop", {})
    with runner._session_factory() as session:
        stale = session.get(Job, stale_id)
        assert stale is not None
        stale.status = "running"
        stale.started_at = None
        session.commit()
    runner.start()
    try:
        wait_until(lambda: job_status(runner, fresh_id) == "done")
        assert job_status(runner, stale_id) == "failed"
        assert "interrupted" in (job_error(runner, stale_id) or "")
    finally:
        runner.stop()
    assert seen == [fresh_id]


def test_runner_worker_pool_processes_jobs_concurrently(tmp_path: Path) -> None:
    def handler(session: Session, job: Job, report: Any) -> None:
        time.sleep(0.3)

    runner, _bus = make_runner(tmp_path, handler, workers=3)
    ids = [enqueue(runner, "noop", {}) for _ in range(3)]
    started = time.monotonic()
    runner.start()
    try:
        wait_until(lambda: all(job_status(runner, job_id) == "done" for job_id in ids))
        elapsed = time.monotonic() - started
    finally:
        runner.stop()
    assert elapsed < 0.85  # 3 x 0.3s serial would be ~0.9s; pool runs them in parallel


def test_runner_grouped_jobs_run_in_enqueue_order(tmp_path: Path) -> None:
    events: list[str] = []

    def handler(session: Session, job: Job, report: Any) -> None:
        events.append(f"start:{job.id}")
        time.sleep(0.25)
        events.append(f"end:{job.id}")

    def group(job: Job) -> str | None:
        key = (job.payload or {}).get("k")
        return str(key) if key is not None else None

    runner, _bus = make_runner(tmp_path, handler, workers=3, group_key=group)
    first = enqueue(runner, "noop", {"k": "s1"})
    second = enqueue(runner, "noop", {"k": "s1"})
    other = enqueue(runner, "noop", {"k": "s2"})
    runner.start()
    try:
        wait_until(
            lambda: all(
                job_status(runner, job_id) == "done"
                for job_id in (first, second, other)
            )
        )
    finally:
        runner.stop()
    assert events.index(f"end:{first}") < events.index(f"start:{second}")
    assert events.index(f"start:{other}") < events.index(f"end:{first}")


def test_runner_timeout_marks_failed(tmp_path: Path) -> None:
    def handler(session: Session, job: Job, report: Any) -> None:
        time.sleep(2.0)

    runner, _bus = make_runner(tmp_path, handler, job_timeout_sec=0.3)
    job_id = enqueue(runner, "noop", {})
    runner.start()
    try:
        wait_until(lambda: job_status(runner, job_id) == "failed")
        assert "timed out" in (job_error(runner, job_id) or "")
    finally:
        runner.stop()


def test_runner_logs_failures(tmp_path: Path, capsys: Any) -> None:
    def handler(session: Session, job: Job, report: Any) -> None:
        raise JobError("boom")

    runner, _bus = make_runner(tmp_path, handler)
    job_id = enqueue(runner, "noop", {})
    runner.start()
    try:
        wait_until(lambda: job_status(runner, job_id) == "failed")
    finally:
        runner.stop()
    output = capsys.readouterr().out + capsys.readouterr().err
    assert "job_failed" in output
