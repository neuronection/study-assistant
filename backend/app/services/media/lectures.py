import hashlib
from datetime import UTC, timedelta
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ...core.vocab import LectureRetention, LectureStatus
from ...domain.models import (
    Blob,
    CaptureStaging,
    Course,
    Extraction,
    LectureChunk,
    LectureSession,
    Material,
    MaterialDrawing,
    MaterialImage,
    NoteDrawing,
    utcnow,
)
from ...jobs.payloads import LectureTranscribePayload
from ...jobs.runner import JobRunner
from ..content.materials import MaterialsService
from ..knowledge.tree import TreeError, TreeService
from .container import LectureContainerError, concat_and_validate

MAX_CHUNK_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_PARTS = 2000
TEXT_ONLY_TTL_DAYS = 7


class LectureError(ValueError):
    pass


class LectureConflict(LectureError):
    pass


def create_session(
    session: Session,
    *,
    profile_id: str,
    course_id: str,
    node_id: str | None,
    title: str,
    consent_confirmed: bool,
    retention: str,
    mime: str,
) -> LectureSession:
    if not consent_confirmed:
        raise LectureError("recording consent must be confirmed")
    if retention not in {member.value for member in LectureRetention}:
        raise LectureError("unknown retention mode")
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile_id:
        raise LectureError("course not found")
    try:
        placement = TreeService(session).placement_node(course_id, node_id)
    except TreeError as error:
        raise LectureError(str(error)) from error
    row = LectureSession(
        profile_id=profile_id,
        course_id=course_id,
        node_id=placement,
        title=title.strip()[:300] or "Lecture recording",
        retention=retention,
        mime=mime or "audio/webm",
        consent_confirmed=True,
        status=LectureStatus.RECORDING.value,
    )
    session.add(row)
    session.flush()
    return row


def _load(session: Session, session_id: str, profile_id: str) -> LectureSession:
    row = session.get(LectureSession, session_id)
    if row is None or row.profile_id != profile_id:
        raise LectureError("lecture session not found")
    return row


def get_session(session: Session, session_id: str, profile_id: str) -> LectureSession:
    return _load(session, session_id, profile_id)


def list_sessions(
    session: Session, profile_id: str, course_id: str | None = None
) -> list[LectureSession]:
    statement = select(LectureSession).where(LectureSession.profile_id == profile_id)
    if course_id is not None:
        statement = statement.where(LectureSession.course_id == course_id)
    return list(
        session.scalars(
            statement.order_by(LectureSession.created_at.desc(), LectureSession.id.desc())
        )
    )


def update_session(
    session: Session,
    row: LectureSession,
    *,
    title: str | None = None,
    status: str | None = None,
    retention: str | None = None,
) -> LectureSession:
    if title is not None:
        row.title = title.strip()[:300] or row.title
    if retention is not None:
        if retention not in {member.value for member in LectureRetention}:
            raise LectureError("unknown retention mode")
        row.retention = retention
    if status is not None:
        allowed = {
            LectureStatus.RECORDING.value,
            LectureStatus.PAUSED.value,
            LectureStatus.UPLOADING.value,
            LectureStatus.CANCELLED.value,
        }
        if status not in allowed:
            raise LectureError("unsupported status transition")
        row.status = status
        if status == LectureStatus.CANCELLED.value:
            row.ended_at = utcnow()
    session.flush()
    return row


def put_chunk(
    session: Session,
    *,
    blobs: Any,
    row: LectureSession,
    seq: int,
    data: bytes,
    sha256: str,
) -> LectureChunk:
    if row.status not in (
        LectureStatus.RECORDING.value,
        LectureStatus.PAUSED.value,
        LectureStatus.UPLOADING.value,
    ):
        raise LectureConflict("lecture is not accepting chunks")
    if seq < 0 or seq >= MAX_PARTS:
        raise LectureError("chunk sequence is out of range")
    if not data or len(data) > MAX_CHUNK_BYTES:
        raise LectureError("chunk must be between 1 byte and 32 MB")
    digest = hashlib.sha256(data).hexdigest()
    if sha256 and digest != sha256.lower():
        raise LectureError("chunk sha256 does not match the body")
    existing = session.scalar(
        select(LectureChunk).where(LectureChunk.session_id == row.id, LectureChunk.seq == seq)
    )
    if existing is not None:
        if existing.sha256 == digest:
            return existing
        raise LectureConflict(f"chunk {seq} already exists with different content")
    count = session.scalar(
        select(func.count()).select_from(LectureChunk).where(LectureChunk.session_id == row.id)
    ) or 0
    total = session.scalar(
        select(func.coalesce(func.sum(LectureChunk.size), 0)).where(
            LectureChunk.session_id == row.id
        )
    ) or 0
    if count >= MAX_PARTS or int(total) + len(data) > MAX_TOTAL_BYTES:
        raise LectureError("lecture recording exceeds the session quota")
    blobs.put(data, mime=row.mime, session=session)
    chunk = LectureChunk(session_id=row.id, seq=seq, sha256=digest, size=len(data))
    session.add(chunk)
    session.flush()
    return chunk


def chunks(session: Session, row: LectureSession) -> list[LectureChunk]:
    return list(
        session.scalars(
            select(LectureChunk)
            .where(LectureChunk.session_id == row.id)
            .order_by(LectureChunk.seq)
        )
    )


def missing_sequences(session: Session, row: LectureSession) -> list[int]:
    present = {chunk.seq for chunk in chunks(session, row)}
    if not present:
        return list(range(0, 1))
    return [seq for seq in range(0, max(present) + 1) if seq not in present]


def finalize(
    session: Session,
    *,
    row: LectureSession,
    blobs: Any,
    jobs: Any,
) -> Material:
    if row.material_id is not None:
        material = session.get(Material, row.material_id)
        if material is not None:
            return material
    rows = chunks(session, row)
    if not rows:
        raise LectureError("no chunks uploaded")
    missing = missing_sequences(session, row)
    if missing:
        raise LectureConflict(f"missing chunk sequences: {missing[:10]}")
    row.status = LectureStatus.UPLOADING.value
    parts = [blobs.get(chunk.sha256) for chunk in rows]
    if any(part is None for part in parts):
        raise LectureError("chunk content is missing from the blob store")
    try:
        data, mime = concat_and_validate(
            [part for part in parts if part is not None], row.mime
        )
    except LectureContainerError as error:
        row.status = LectureStatus.FAILED.value
        row.error = str(error)
        raise LectureError(str(error)) from error
    if "webm" in mime:
        extension = "webm"
    elif "ogg" in mime:
        extension = "ogg"
    elif "mp4" in mime:
        extension = "mp4"
    else:
        extension = "bin"
    material, _deduped = MaterialsService(session, blobs).upload(
        profile_id=row.profile_id,
        filename=f"{row.title}.{extension}",
        data=data,
        mime=mime,
        course_id=row.course_id,
    )
    ended = utcnow()
    row.ended_at = ended
    provenance: dict[str, Any] = {
        "source": "lecture",
        "session_id": row.id,
        "retention": row.retention,
    }
    if row.retention == LectureRetention.TEXT_ONLY.value:
        provenance["text_only"] = True
        provenance["audio_expires_at"] = (ended + timedelta(days=7)).isoformat()
    material.provenance = cast(Any, provenance)
    session.flush()
    row.material_id = material.id
    if jobs is not None:
        JobRunner.enqueue(
            session,
            "lecture_transcribe",
            LectureTranscribePayload(session_id=row.id, material_id=material.id),
        )
        row.status = LectureStatus.TRANSCRIBING.value
    else:
        row.status = LectureStatus.READY.value
    session.flush()
    return material


def purge_text_only_audio(session: Session, row: LectureSession, blobs: Any) -> LectureSession:
    if row.retention != LectureRetention.TEXT_ONLY.value:
        raise LectureError("this session does not use text-only retention")
    if row.audio_purged_at is not None:
        return row
    if row.ended_at is None:
        raise LectureConflict("the recording has not finished yet")
    ended = row.ended_at if row.ended_at.tzinfo is not None else row.ended_at.replace(tzinfo=UTC)
    expires = ended + timedelta(days=TEXT_ONLY_TTL_DAYS)
    if utcnow() < expires:
        raise LectureConflict(f"audio is kept until {expires.isoformat()}")
    material = session.get(Material, row.material_id) if row.material_id else None
    if material is None:
        raise LectureError("recording material not found")
    extraction = session.scalar(
        select(Extraction.id)
        .where(Extraction.material_id == material.id)
        .limit(1)
    )
    if extraction is None:
        raise LectureConflict("transcript is not ready yet; audio is kept")
    sha = material.blob_sha
    material.blob_sha = None
    provenance = dict(material.provenance or {})
    provenance["audio_expired"] = True
    provenance["audio_purged_at"] = utcnow().isoformat()
    material.provenance = cast(Any, provenance)
    session.flush()
    if sha:
        references = session.scalar(
            select(func.count())
            .select_from(Material)
            .where(Material.blob_sha == sha, Material.id != material.id)
        ) or 0
        references += session.scalar(
            select(func.count()).select_from(MaterialImage).where(MaterialImage.blob_sha == sha)
        ) or 0
        references += session.scalar(
            select(func.count()).select_from(MaterialDrawing).where(MaterialDrawing.png_sha == sha)
        ) or 0
        references += session.scalar(
            select(func.count()).select_from(NoteDrawing).where(NoteDrawing.png_sha == sha)
        ) or 0
        references += session.scalar(
            select(func.count()).select_from(CaptureStaging).where(CaptureStaging.blob_sha == sha)
        ) or 0
        if references == 0:
            session.execute(delete(Blob).where(Blob.sha256 == sha))
            blobs.delete(sha)
    row.audio_purged_at = utcnow()
    session.flush()
    return row


def purge_due_text_only(session: Session, profile_id: str, blobs: Any) -> None:
    rows = session.scalars(
        select(LectureSession).where(
            LectureSession.profile_id == profile_id,
            LectureSession.retention == LectureRetention.TEXT_ONLY.value,
            LectureSession.audio_purged_at.is_(None),
        )
    )
    for row in rows:
        try:
            purge_text_only_audio(session, row, blobs)
        except (LectureError, LectureConflict):
            continue
    session.flush()
