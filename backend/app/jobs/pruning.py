from collections.abc import Callable
from datetime import datetime, timedelta

import structlog
from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from ..domain.models import Job, utcnow

logger = structlog.get_logger(__name__)


def prune_done_jobs(
    session_factory: Callable[[], Session],
    ttl_days: int,
    now: datetime | None = None,
) -> int:
    current = now if now is not None else utcnow()
    cutoff = current - timedelta(days=ttl_days)
    with session_factory() as session:
        result = session.execute(
            delete(Job).where(
                Job.status == "done",
                func.coalesce(Job.finished_at, Job.created_at) < cutoff,
            )
        )
        session.commit()
        pruned = int(result.rowcount if hasattr(result, "rowcount") else 0)
    if pruned:
        logger.info("jobs_done_pruned", count=pruned, ttl_days=ttl_days)
    return pruned
