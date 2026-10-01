"""Per-boot idempotent seeding & retention (plan 20 Phase 4 split).

Not migrations (D6): these are data/maintenance operations every boot
may run — starter rows for task assignments, skills, course types and
error patterns, plus trash and job retention. `run_startup_seeds` is
called from `create_app`; the desktop bootstrap (`app/local.py`) does
not duplicate it.
"""

from __future__ import annotations

from typing import Any

from .ai.tasks import TASK_DEFS


def run_startup_seeds(session_factory: Any, *, jobs_done_ttl_days: int) -> None:
    """Seed starter data (idempotent) and run boot-time retention."""
    from .ai.providers import seed_default_task_assignments
    from .domain.models import TaskAssignment
    from .jobs.pruning import prune_done_jobs
    from .services.platform.skills import (
        seed_course_types,
        seed_error_patterns,
        seed_skills,
    )
    from .services.platform.trash import purge_expired

    with session_factory() as session:
        for task_def in TASK_DEFS:
            if session.get(TaskAssignment, task_def.task) is None:
                session.add(
                    TaskAssignment(task=task_def.task, model_id=None, fallback_model_id=None)
                )
        seed_default_task_assignments(session)
        seed_course_types(session)
        seed_error_patterns(session)
        seed_skills(session)
        session.commit()
        purge_expired(session)

    prune_done_jobs(session_factory, jobs_done_ttl_days)
