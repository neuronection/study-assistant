from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...domain.models import Extraction, Material, MediaSegment


def _stamp(ms: int) -> str:
    total = max(0, ms // 1000)
    return f"{total // 60}:{total % 60:02d}"


def rebuild_transcript_extraction(
    session: Session, material: Material
) -> Extraction | None:
    segments = list(
        session.scalars(
            select(MediaSegment)
            .where(MediaSegment.material_id == material.id)
            .order_by(MediaSegment.order_idx, MediaSegment.start_ms, MediaSegment.id)
        )
    )
    if not segments:
        return None
    markdown = "\n\n".join(
        f"[{_stamp(segment.start_ms)}] {segment.text.strip()}"
        for segment in segments
        if segment.text.strip()
    )
    if not markdown:
        return None
    latest = session.scalar(
        select(func.max(Extraction.version)).where(Extraction.material_id == material.id)
    )
    extraction = Extraction(
        material_id=material.id,
        version=int(latest or 0) + 1,
        extractor="media_transcript",
        blocks=[{"type": "text", "md": markdown}],
        markdown=markdown,
    )
    session.add(extraction)
    session.flush()
    return extraction
