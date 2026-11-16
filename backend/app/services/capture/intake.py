import hashlib
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...core.limits import MAX_UPLOAD_BYTES
from ...core.vocab import CaptureKind, CaptureStatus
from ...domain.models import CaptureStaging, utcnow
from ...jobs.runner import JobRunner
from ...services.content.materials import MaterialsService
from ...services.knowledge.courses import StructureService
from ...storage.blobs import BlobStore
from .sources import source_for

CAPTURE_TTL_DAYS = 7


class CaptureNotFound(LookupError):
    pass


class CaptureConflict(RuntimeError):
    pass


class CaptureBlobMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class CaptureItem:
    filename: str
    mime: str | None
    data: bytes


@dataclass(frozen=True)
class CaptureCommit:
    capture_id: str
    material_id: str
    job_id: str | None
    deduped: bool


def stage(
    session: Session,
    blobs: BlobStore,
    *,
    profile_id: str,
    source_kind: str,
    items: list[CaptureItem],
    group_id: str | None = None,
    client_op_ids: list[str | None] | None = None,
) -> list[CaptureStaging]:
    source = source_for(source_kind)
    rows: list[CaptureStaging] = []
    for index, item in enumerate(items):
        if not item.data:
            raise ValueError("empty file")
        if len(item.data) > MAX_UPLOAD_BYTES:
            raise ValueError("file exceeds upload size limit")
        if not source.accepts(item.filename, item.mime):
            raise ValueError(f"capture source does not accept '{item.filename}'")
        op_id = None
        if client_op_ids and index < len(client_op_ids):
            op_id = client_op_ids[index]
        if op_id is not None:
            existing = session.scalar(
                select(CaptureStaging).where(
                    CaptureStaging.profile_id == profile_id,
                    CaptureStaging.client_op_id == op_id,
                )
            )
            if existing is not None:
                if existing.blob_sha != hashlib.sha256(item.data).hexdigest():
                    raise ValueError("client_op_id was reused with different bytes")
                rows.append(existing)
                continue
        stored = blobs.put(item.data, mime=item.mime, session=session)
        session.flush()
        row = CaptureStaging(
            profile_id=profile_id,
            source_kind=CaptureKind.parse(source_kind).value,
            filename=item.filename,
            mime=item.mime,
            blob_sha=stored.sha256,
            byte_size=stored.size,
            group_id=group_id,
            client_op_id=op_id or None,
            expires_at=utcnow() + timedelta(days=CAPTURE_TTL_DAYS),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def list_staged(
    session: Session,
    *,
    profile_id: str,
    status: CaptureStatus = CaptureStatus.STAGED,
    limit: int = 50,
) -> list[CaptureStaging]:
    return list(
        session.scalars(
            select(CaptureStaging)
            .where(
                CaptureStaging.profile_id == profile_id,
                CaptureStaging.status == status.value,
            )
            .order_by(CaptureStaging.created_at.desc(), CaptureStaging.id)
            .limit(limit)
        )
    )


def get_staged(
    session: Session,
    *,
    capture_id: str,
    profile_id: str,
) -> CaptureStaging:
    row = session.get(CaptureStaging, capture_id)
    if row is None or row.profile_id != profile_id:
        raise CaptureNotFound("capture not found")
    return row


def commit(
    session: Session,
    blobs: BlobStore,
    jobs: JobRunner,
    *,
    capture_id: str,
    profile_id: str,
    course_id: str,
    folder_id: str | None = None,
    node_id: str | None = None,
    title: str | None = None,
) -> CaptureCommit:
    row = get_staged(session, capture_id=capture_id, profile_id=profile_id)
    if row.status != CaptureStatus.STAGED.value:
        raise CaptureConflict(f"capture is {row.status}")
    data = blobs.get(row.blob_sha)
    if data is None:
        raise CaptureBlobMissing("capture bytes are not available")
    service = MaterialsService(session, blobs)
    material, deduped = service.upload(
        profile_id=profile_id,
        filename=row.filename,
        data=data,
        mime=row.mime,
        course_id=course_id,
        folder_id=folder_id,
    )
    if title is not None and title.strip():
        material.title = title.strip()
    if node_id is not None:
        StructureService(session).assign(node_id, material.id, rationale="captured here")
    job_id = None if deduped else service.queue_ingest(material, jobs)
    row.status = CaptureStatus.COMMITTED.value
    row.material_id = material.id
    row.updated_at = utcnow()
    session.flush()
    return CaptureCommit(
        capture_id=row.id,
        material_id=material.id,
        job_id=job_id,
        deduped=deduped,
    )


def discard(session: Session, *, capture_id: str, profile_id: str) -> CaptureStaging:
    row = get_staged(session, capture_id=capture_id, profile_id=profile_id)
    if row.status == CaptureStatus.STAGED.value:
        row.status = CaptureStatus.DISCARDED.value
        row.updated_at = utcnow()
        session.flush()
    return row


def sweep_expired(session: Session) -> int:
    result = session.execute(
        update(CaptureStaging)
        .where(
            CaptureStaging.status == CaptureStatus.STAGED.value,
            CaptureStaging.expires_at < utcnow(),
        )
        .values(status=CaptureStatus.EXPIRED.value, updated_at=utcnow())
    )
    return int(getattr(result, "rowcount", 0) or 0)


def assemble(
    session: Session,
    blobs: BlobStore,
    *,
    profile_id: str,
    items: list[tuple[str, int]],
    title: str | None = None,
) -> CaptureStaging:
    if len(items) < 2:
        raise ValueError("combine at least two pages")
    pairs: list[tuple[CaptureStaging, int]] = []
    for capture_id, rotation in items:
        if rotation not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180 or 270")
        row = get_staged(session, capture_id=capture_id, profile_id=profile_id)
        if row.status != CaptureStatus.STAGED.value:
            raise CaptureConflict(f"capture is {row.status}")
        if row.mime is None or not row.mime.startswith("image/"):
            raise ValueError("only image captures can be combined")
        pairs.append((row, rotation))

    import fitz

    document = fitz.open()
    try:
        for row, rotation in pairs:
            data = blobs.get(row.blob_sha)
            if data is None:
                raise CaptureBlobMissing("capture bytes are not available")
            source = fitz.open(stream=data, filetype=None)
            try:
                rect = source[0].rect
            finally:
                source.close()
            width, height = rect.width, rect.height
            if rotation in (90, 270):
                width, height = height, width
            page = document.new_page(width=width, height=height)
            page.insert_image(page.rect, stream=data, rotate=rotation)
        pdf = bytes(document.tobytes())
    finally:
        document.close()
    if len(pdf) > MAX_UPLOAD_BYTES:
        raise ValueError("combined PDF exceeds upload size limit")

    stored = blobs.put(pdf, mime="application/pdf", session=session)
    session.flush()
    base = (title or "scan").strip() or "scan"
    if base.lower().endswith(".pdf"):
        base = base[:-4]
    combined = CaptureStaging(
        profile_id=profile_id,
        source_kind=pairs[0][0].source_kind,
        filename=f"{base}.pdf",
        mime="application/pdf",
        blob_sha=stored.sha256,
        byte_size=stored.size,
        group_id=pairs[0][0].group_id,
        expires_at=utcnow() + timedelta(days=CAPTURE_TTL_DAYS),
    )
    session.add(combined)
    for row, _rotation in pairs:
        row.status = CaptureStatus.DISCARDED.value
        row.updated_at = utcnow()
    session.flush()
    return combined
