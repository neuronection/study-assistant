from datetime import timedelta
from pathlib import Path

from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.domain.models import Job, utcnow
from app.jobs.pruning import prune_done_jobs
from app.storage.db import make_engine, make_session_factory


def make_factory(tmp_path: Path) -> sessionmaker[Session]:
    db_path = tmp_path / "prune.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, "head")
    engine = make_engine(db_path)
    return make_session_factory(engine)


def insert(
    factory: sessionmaker[Session], *, status: str, age_days: float, finished: bool
) -> int:
    now = utcnow()
    with factory() as session:
        job = Job(type="postprocess", status=status, payload=None)
        if finished:
            job.finished_at = now - timedelta(days=age_days)
        else:
            job.created_at = now - timedelta(days=age_days)
        session.add(job)
        session.commit()
        job_id = int(job.id)
    return job_id


def survivors(factory: sessionmaker[Session]) -> set[int]:
    with factory() as session:
        return {int(job.id) for job in session.scalars(select(Job))}


def test_prune_removes_only_old_done_jobs(tmp_path: Path) -> None:
    factory = make_factory(tmp_path / "one")

    insert(factory, status="done", age_days=20, finished=True)
    young_done = insert(factory, status="done", age_days=2, finished=True)
    old_failed = insert(factory, status="failed", age_days=30, finished=True)
    old_queued = insert(factory, status="queued", age_days=30, finished=False)

    pruned = prune_done_jobs(factory, ttl_days=14)

    assert pruned == 1
    assert survivors(factory) == {young_done, old_failed, old_queued}


def test_prune_uses_created_at_when_finished_missing(tmp_path: Path) -> None:
    factory = make_factory(tmp_path / "two")

    insert(factory, status="done", age_days=40, finished=False)

    pruned = prune_done_jobs(factory, ttl_days=14)

    assert pruned == 1
    assert survivors(factory) == set()


def test_prune_respects_ttl_override(tmp_path: Path) -> None:
    factory = make_factory(tmp_path / "three")

    insert(factory, status="done", age_days=3, finished=True)

    assert prune_done_jobs(factory, ttl_days=7) == 0
    assert prune_done_jobs(factory, ttl_days=1) == 1
    assert survivors(factory) == set()
