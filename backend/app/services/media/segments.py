from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import MediaSegmentSource
from ...domain.models import Extraction, Material, MediaSegment


class MediaError(ValueError):
    pass


def _seed_from_extraction(session: Session, material: Material, profile_id: str) -> None:
    extraction = session.scalars(
        select(Extraction)
        .where(Extraction.material_id == material.id)
        .order_by(Extraction.version.desc())
        .limit(1)
    ).first()
    if extraction is None or not extraction.markdown.strip():
        return
    duration_ms = int((material.duration_sec or 0) * 1000)
    session.add(
        MediaSegment(
            profile_id=profile_id,
            material_id=material.id,
            start_ms=0,
            end_ms=duration_ms,
            text=extraction.markdown,
            order_idx=0,
            source=MediaSegmentSource.IMPORT.value,
        )
    )
    session.flush()


def list_segments(session: Session, material: Material, profile_id: str) -> list[MediaSegment]:
    rows = list(
        session.scalars(
            select(MediaSegment)
            .where(MediaSegment.material_id == material.id)
            .order_by(MediaSegment.order_idx, MediaSegment.start_ms, MediaSegment.id)
        )
    )
    if not rows:
        _seed_from_extraction(session, material, profile_id)
        rows = list(
            session.scalars(
                select(MediaSegment)
                .where(MediaSegment.material_id == material.id)
                .order_by(MediaSegment.order_idx, MediaSegment.start_ms, MediaSegment.id)
            )
        )
    return rows


def update_segment(
    session: Session,
    segment: MediaSegment,
    *,
    text: str | None = None,
    speaker: str | None = None,
) -> MediaSegment:
    if text is not None:
        segment.text = text.strip()
    if speaker is not None:
        segment.speaker = speaker.strip() or None
    session.flush()
    return segment


def add_segment(
    session: Session,
    *,
    profile_id: str,
    material_id: str,
    start_ms: int,
    end_ms: int,
    text: str,
    speaker: str | None,
    order_idx: int,
) -> MediaSegment:
    if end_ms < start_ms:
        raise MediaError("segment end must not be before start")
    if not text.strip():
        raise MediaError("segment text is required")
    row = MediaSegment(
        profile_id=profile_id,
        material_id=material_id,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text.strip(),
        speaker=speaker.strip() if speaker else None,
        order_idx=order_idx,
        source=MediaSegmentSource.MANUAL.value,
    )
    session.add(row)
    session.flush()
    return row


def _reindex(session: Session, material_id: str) -> None:
    rows = list(
        session.scalars(
            select(MediaSegment)
            .where(MediaSegment.material_id == material_id)
            .order_by(MediaSegment.start_ms, MediaSegment.order_idx, MediaSegment.id)
        )
    )
    for index, row in enumerate(rows):
        row.order_idx = index
    session.flush()


def split_segment(
    session: Session, segment: MediaSegment, at_ms: int
) -> MediaSegment:
    if segment.material_id is None:
        raise MediaError("segment has no material")
    if not segment.start_ms < at_ms < segment.end_ms:
        raise MediaError("split point must be inside the segment")
    words = segment.text.split()
    if len(words) < 2:
        raise MediaError("segment needs at least two words to split")
    ratio = (at_ms - segment.start_ms) / max(1, segment.end_ms - segment.start_ms)
    boundary = max(1, min(len(words) - 1, round(len(words) * ratio)))
    first_text = " ".join(words[:boundary])
    second_text = " ".join(words[boundary:])
    if not first_text or not second_text:
        raise MediaError("split point would create an empty segment")
    second = MediaSegment(
        profile_id=segment.profile_id,
        material_id=segment.material_id,
        start_ms=at_ms,
        end_ms=segment.end_ms,
        text=second_text,
        speaker=segment.speaker,
        confidence=segment.confidence,
        order_idx=segment.order_idx + 1,
        source=segment.source,
    )
    segment.end_ms = at_ms
    segment.text = first_text
    session.add(second)
    session.flush()
    _reindex(session, segment.material_id)
    return second


def merge_segments(
    session: Session, first: MediaSegment, second: MediaSegment
) -> MediaSegment:
    if first.material_id is None or first.material_id != second.material_id:
        raise MediaError("segments must belong to the same material")
    first.end_ms = max(first.end_ms, second.end_ms)
    first.text = f"{first.text.strip()} {second.text.strip()}".strip()
    if first.speaker != second.speaker:
        first.speaker = None
    session.delete(second)
    session.flush()
    _reindex(session, first.material_id)
    return first
