from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.models import ChatSession, Job, Material, Note
from .deps import get_session

router = APIRouter(prefix="/jobs", tags=["jobs"])

NON_RETRYABLE_TYPES = frozenset({"chat_turn"})
JOB_STATUSES = frozenset({"queued", "running", "done", "failed", "cancelled"})


class JobOut(BaseModel):
    id: int
    type: str
    status: str
    progress: int
    stage: str | None
    error: str | None
    label: str
    material_id: int | None
    retriable: bool
    stale: bool = False
    created_at: str | None
    started_at: str | None
    finished_at: str | None


class JobsSummary(BaseModel):
    queued: int
    running: int
    failed: int
    done: int
    cancelled: int = 0
    failed_retryable: int
    failed_stale: int


class RetryFailedBody(BaseModel):
    types: list[str] | None = None


class DeleteFailedBody(BaseModel):
    types: list[str] | None = None
    stale_only: bool = False


class JobTypeOut(BaseModel):
    type: str
    label: str


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _material_label(session: Session, payload: dict[str, Any] | None) -> str | None:
    material_id = _material_id(payload)
    if material_id is None:
        return None
    material = session.get(Material, material_id)
    if material is None:
        return None
    return material.filename or f"Material #{material.id}"


def _material_id(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    material_id = payload.get("material_id")
    if material_id is None:
        return None
    try:
        return int(material_id)
    except (TypeError, ValueError):
        return None


def _chat_session_id(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    value = payload.get("chat_session_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _note_label(session: Session, payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    value = payload.get("note_id")
    if value is None:
        return None
    try:
        note_id = int(value)
    except (TypeError, ValueError):
        return None
    note = session.get(Note, note_id)
    if note is None:
        return None
    return note.title


def _note_id(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    value = payload.get("note_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stale_job_ids(session: Session, jobs: list[Job] | tuple[Job, ...]) -> set[int]:
    material_ids: set[int] = set()
    chat_ids: set[int] = set()
    note_ids: set[int] = set()
    for job in jobs:
        material_id = _material_id(job.payload)
        if material_id is not None:
            material_ids.add(material_id)
        chat_id = _chat_session_id(job.payload)
        if chat_id is not None:
            chat_ids.add(chat_id)
        note_id = _note_id(job.payload)
        if note_id is not None:
            note_ids.add(note_id)
    stale: set[int] = set()
    if material_ids:
        found = set(
            session.scalars(select(Material.id).where(Material.id.in_(material_ids)))
        )
        stale.update(
            job.id
            for job in jobs
            if (material_id := _material_id(job.payload)) is not None
            and material_id not in found
        )
    if chat_ids:
        found = set(
            session.scalars(select(ChatSession.id).where(ChatSession.id.in_(chat_ids)))
        )
        stale.update(
            job.id
            for job in jobs
            if (chat_id := _chat_session_id(job.payload)) is not None
            and chat_id not in found
        )
    if note_ids:
        found = set(session.scalars(select(Note.id).where(Note.id.in_(note_ids))))
        stale.update(
            job.id
            for job in jobs
            if (note_id := _note_id(job.payload)) is not None
            and note_id not in found
        )
    return stale


def _to_out(
    session: Session,
    job: Job,
    retriable_types: frozenset[str] | set[str],
    stale_ids: set[int] | None = None,
) -> JobOut:
    retriable = (
        job.status == "failed"
        and job.type not in NON_RETRYABLE_TYPES
        and job.type in retriable_types
    )
    label = _material_label(session, job.payload) or _note_label(session, job.payload)
    stale = job.id in stale_ids if stale_ids else False
    return JobOut(
        id=job.id,
        type=job.type,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        error=job.error,
        label=label or job.type.replace("_", " "),
        material_id=_material_id(job.payload),
        retriable=retriable,
        stale=stale,
        created_at=_iso(job.created_at),
        started_at=_iso(job.started_at),
        finished_at=_iso(job.finished_at),
    )


def _reset(job: Job) -> None:
    job.status = "queued"
    job.progress = 0
    job.stage = None
    job.error = None
    job.started_at = None
    job.finished_at = None


@router.get("")
def list_jobs(
    request: Request,
    status: str | None = None,
    type: str | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> list[JobOut]:
    if status is not None and status not in JOB_STATUSES:
        raise HTTPException(status_code=422, detail="unknown job status")
    query = select(Job).order_by(Job.id.desc()).limit(max(1, min(limit, 500)))
    if status is not None:
        query = query.where(Job.status == status)
    if type is not None:
        query = query.where(Job.type == type)
    retriable_types = request.app.state.jobs.retriable_handlers()
    jobs = list(session.scalars(query))
    stale_ids = _stale_job_ids(session, jobs)
    return [_to_out(session, job, retriable_types, stale_ids) for job in jobs]


@router.get("/summary")
def jobs_summary(
    request: Request, session: Session = Depends(get_session)
) -> JobsSummary:
    rows = session.execute(
        select(Job.status, func.count(Job.id)).group_by(Job.status)
    ).all()
    counts: dict[str, int] = {str(status): int(count) for status, count in rows}
    retriable_types = request.app.state.jobs.retriable_handlers()
    failed_jobs = list(session.scalars(select(Job).where(Job.status == "failed")))
    failed_retryable = sum(
        1
        for job in failed_jobs
        if job.type in retriable_types and job.type not in NON_RETRYABLE_TYPES
    )
    failed_stale = len(_stale_job_ids(session, failed_jobs))
    return JobsSummary(
        queued=counts.get("queued", 0),
        running=counts.get("running", 0),
        failed=counts.get("failed", 0),
        done=counts.get("done", 0),
        cancelled=counts.get("cancelled", 0),
        failed_retryable=failed_retryable,
        failed_stale=failed_stale,
    )


@router.get("/types")
def job_types(request: Request) -> list[JobTypeOut]:
    retriable_types = request.app.state.jobs.retriable_handlers()
    return [
        JobTypeOut(type=entry, label=entry.replace("_", " "))
        for entry in sorted(retriable_types)
    ]


@router.post("/{job_id}/retry")
def retry_job(
    job_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    retriable_types = request.app.state.jobs.retriable_handlers()
    if job.status != "failed":
        raise HTTPException(
            status_code=422, detail="only failed jobs can be retried"
        )
    if job.type in NON_RETRYABLE_TYPES or job.type not in retriable_types:
        raise HTTPException(
            status_code=422, detail=f"job type '{job.type}' cannot be retried"
        )
    _reset(job)
    session.commit()
    request.app.state.jobs.publish_progress(job_id, 0, "queued", "queued")
    request.app.state.jobs.wake()
    return _to_out(session, job, retriable_types, _stale_job_ids(session, [job]))


@router.post("/retry-failed")
def retry_failed_jobs(
    body: RetryFailedBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    retriable_types = request.app.state.jobs.retriable_handlers()
    query = select(Job).where(Job.status == "failed")
    if body.types:
        wanted = [entry for entry in body.types if entry not in NON_RETRYABLE_TYPES]
        if not wanted:
            return {"retried": 0}
        query = query.where(Job.type.in_(wanted))
    retried = 0
    for job in session.scalars(query):
        if job.type in NON_RETRYABLE_TYPES or job.type not in retriable_types:
            continue
        _reset(job)
        retried += 1
    if retried:
        session.commit()
        request.app.state.jobs.wake()
    return {"retried": retried}


@router.delete("/failed")
def delete_failed_jobs(
    body: DeleteFailedBody,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    query = select(Job).where(Job.status == "failed")
    if body.types:
        query = query.where(Job.type.in_(body.types))
    candidates = list(session.scalars(query))
    if body.stale_only:
        stale_ids = _stale_job_ids(session, candidates)
        candidates = [job for job in candidates if job.id in stale_ids]
    deleted = 0
    for job in candidates:
        session.delete(job)
        deleted += 1
    if deleted:
        session.commit()
    return {"deleted": deleted}


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: int,
    session: Session = Depends(get_session),
) -> None:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in {"queued", "running"}:
        raise HTTPException(
            status_code=422,
            detail=f"job '{job.type}' cannot be deleted while {job.status}",
        )
    session.delete(job)
    session.commit()
