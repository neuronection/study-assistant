import threading
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core.vocab import JobStatus
from ..domain.models import Job, utcnow

CANCELLED_ERROR = "source deleted before this job finished"

_active_statuses = (JobStatus.QUEUED, JobStatus.RUNNING)

_cancel_flags: dict[int, threading.Event] = {}
_flags_lock = threading.Lock()


def _flag_for(job_id: int) -> threading.Event:
    with _flags_lock:
        flag = _cancel_flags.get(job_id)
        if flag is None:
            flag = threading.Event()
            _cancel_flags[job_id] = flag
        return flag


def request_cancel(job_id: int) -> None:
    _flag_for(job_id).set()


def is_cancel_requested(job_id: int) -> bool:
    with _flags_lock:
        flag = _cancel_flags.get(job_id)
    return flag is not None and flag.is_set()


def clear_cancel(job_id: int) -> None:
    with _flags_lock:
        _cancel_flags.pop(job_id, None)


class JobCancelled(Exception):
    pass


def _payload_id(payload: dict[str, Any] | None, key: str) -> int | None:
    if not payload:
        return None
    value = payload.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _job_matches(
    job: Job,
    material_ids: set[int],
    chat_session_ids: set[int],
    note_ids: set[int],
) -> bool:
    if material_ids and _payload_id(job.payload, "material_id") in material_ids:
        return True
    if chat_session_ids and _payload_id(job.payload, "chat_session_id") in chat_session_ids:
        return True
    return bool(note_ids and _payload_id(job.payload, "note_id") in note_ids)


def cancel_jobs_for(
    session: Session,
    *,
    material_ids: list[int] | tuple[int, ...] = (),
    chat_session_ids: list[int] | tuple[int, ...] = (),
    note_ids: list[int] | tuple[int, ...] = (),
) -> int:
    wanted_materials = {int(entry) for entry in material_ids}
    wanted_chats = {int(entry) for entry in chat_session_ids}
    wanted_notes = {int(entry) for entry in note_ids}
    if not material_ids and not chat_session_ids and not note_ids:
        return 0
    active = list(
        session.scalars(select(Job).where(Job.status.in_(_active_statuses)))
    )
    cancelled = 0
    for job in active:
        if not _job_matches(job, wanted_materials, wanted_chats, wanted_notes):
            continue
        claimed = session.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "queued")
            .values(status=JobStatus.CANCELLED, error=CANCELLED_ERROR, finished_at=utcnow())
        )
        session.commit()
        if int(cast(Any, claimed).rowcount or 0):
            cancelled += 1
        else:
            request_cancel(job.id)
    return cancelled


def cancel_jobs_for_material(session: Session, material_id: int) -> int:
    return cancel_jobs_for(session, material_ids=[material_id])


def ensure_target_exists(
    session: Session, model: type, entity_id: int, label: str
) -> None:
    session.expire_all()
    if session.get(model, entity_id) is None:
        raise JobCancelled(f"{label} was deleted while this job was running")
