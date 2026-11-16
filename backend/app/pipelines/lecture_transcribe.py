import re
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..ai.gateway import BudgetExceeded, ProviderError, TaskUnassigned
from ..ai.transcribe import TranscriptionSegment
from ..core.vocab import LectureStatus, MediaSegmentSource
from ..domain.models import (
    Extraction,
    LectureSession,
    Material,
    MediaSegment,
)
from ..jobs.payloads import LectureTranscribePayload, PostprocessPayload
from ..jobs.runner import JobError, JobHandler, JobRunner, ProgressReporter


def _stamp(ms: int) -> str:
    total = max(0, ms // 1000)
    return f"{total // 60}:{total % 60:02d}"


def _fallback_segments(text: str, duration_ms: int) -> list[TranscriptionSegment]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if not sentences:
        return []
    total = sum(len(sentence) for sentence in sentences) or 1
    total_ms = max(duration_ms, len(sentences) * 1500)
    cursor = 0
    segments: list[TranscriptionSegment] = []
    for index, sentence in enumerate(sentences):
        share = round(total_ms * len(sentence) / total)
        end = total_ms if index == len(sentences) - 1 else cursor + max(1200, share)
        end = min(total_ms, max(cursor + 500, end))
        segments.append(TranscriptionSegment(start_ms=cursor, end_ms=end, text=sentence))
        cursor = end
    return segments


def _markdown(segments: list[TranscriptionSegment]) -> str:
    return "\n\n".join(
        f"[{_stamp(segment.start_ms)}] {segment.text.strip()}"
        for segment in segments
        if segment.text.strip()
    )


def _persist(
    session: Session,
    lecture: LectureSession,
    material: Material,
    segments: list[TranscriptionSegment],
    *,
    jobs: Any,
) -> None:
    session.execute(
        delete(MediaSegment).where(
            MediaSegment.material_id == material.id,
            MediaSegment.source == MediaSegmentSource.STT.value,
        )
    )
    for index, segment in enumerate(segments):
        session.add(
            MediaSegment(
                profile_id=lecture.profile_id,
                material_id=material.id,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text.strip(),
                order_idx=index,
                source=MediaSegmentSource.STT.value,
            )
        )
    markdown = _markdown(segments)
    latest = session.scalar(
        select(func.max(Extraction.version)).where(Extraction.material_id == material.id)
    )
    extraction = Extraction(
        material_id=material.id,
        version=int(latest or 0) + 1,
        extractor="lecture_stt",
        blocks=[{"type": "text", "md": markdown}],
        markdown=markdown,
    )
    session.add(extraction)
    material.status = "ready"
    session.flush()
    if jobs is not None:
        JobRunner.enqueue(
            session,
            "postprocess",
            PostprocessPayload(material_id=material.id, extraction_id=extraction.id),
        )


def make_lecture_transcribe_handler(
    gateway: Any, blobs: Any, jobs_provider: Any = None
) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        payload = cast(LectureTranscribePayload, job.payload or {})
        session_id = payload.get("session_id")
        material_id = payload.get("material_id")
        if not session_id or not material_id:
            raise JobError("lecture transcribe payload missing ids")
        lecture = session.get(LectureSession, str(session_id))
        material = session.get(Material, str(material_id))
        if lecture is None or material is None:
            raise JobError("lecture or material not found")
        report(10, "transcribe")
        data = blobs.get(material.blob_sha) if material.blob_sha else None
        if data is None:
            lecture.status = LectureStatus.FAILED.value
            lecture.error = "recording audio is missing"
            session.commit()
            raise JobError("recording audio is missing")
        try:
            result = gateway.transcribe(
                data,
                material.mime or "audio/webm",
                course_id=lecture.course_id,
            )
        except (TaskUnassigned, ProviderError, BudgetExceeded) as error:
            lecture.status = LectureStatus.READY.value
            lecture.error = f"recorded — transcription unavailable: {error}"
            material.status = "ready"
            session.commit()
            report(100, "deferred")
            return
        report(60, "persist")
        segments = list(result.segments)
        if not segments and result.text.strip():
            duration = int((material.duration_sec or 0) * 1000)
            segments = _fallback_segments(result.text, duration)
        if not segments:
            lecture.status = LectureStatus.READY.value
            lecture.error = "no speech detected"
            material.status = "ready"
            session.commit()
            report(100, "empty")
            return
        _persist(
            session,
            lecture,
            material,
            segments,
            jobs=jobs_provider() if callable(jobs_provider) else jobs_provider,
        )
        lecture.status = LectureStatus.READY.value
        lecture.error = None
        session.commit()
        report(100, "done")

    return handler
