from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..domain.models import Material, MediaSegment
from ..jobs.payloads import PostprocessPayload
from ..jobs.runner import JobRunner
from ..services.media.refs import MediaRef
from ..services.media.segments import (
    MediaError,
    add_segment,
    list_segments,
    merge_segments,
    split_segment,
    update_segment,
)
from ..services.media.transcript import rebuild_transcript_extraction
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(tags=["media"])


class MediaSegmentOut(BaseModel):
    id: str
    material_id: str | None
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None
    confidence: float | None
    order_idx: int
    source: str


class MediaOut(BaseModel):
    material_id: str
    course_id: str
    title: str
    blob_sha: str | None
    mime: str | None
    duration_ms: int
    segments: list[MediaSegmentOut]


class SegmentIn(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=20_000)
    speaker: str | None = Field(default=None, max_length=120)
    order_idx: int = Field(default=0, ge=0)


class SegmentPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=20_000)
    speaker: str | None = Field(default=None, max_length=120)


class SegmentSplit(BaseModel):
    at_ms: int = Field(ge=0)


class SegmentMerge(BaseModel):
    first_id: str
    second_id: str


class MediaRebuildOut(BaseModel):
    extraction_id: str
    version: int


def _material(session: Session, material_id: str, profile_id: str) -> Material:
    material = session.get(Material, material_id)
    if material is None or material.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="material not found")
    if material.kind not in ("audio", "video"):
        raise HTTPException(status_code=422, detail="material is not audio or video")
    return material


def _rebuild(session: Session, material: Material) -> None:
    extraction = rebuild_transcript_extraction(session, material)
    if extraction is not None:
        JobRunner.enqueue(
            session,
            "postprocess",
            PostprocessPayload(material_id=material.id, extraction_id=extraction.id),
        )


def _segment_out(row: MediaSegment) -> MediaSegmentOut:
    return MediaSegmentOut(
        id=row.id,
        material_id=row.material_id,
        start_ms=row.start_ms,
        end_ms=row.end_ms,
        text=row.text,
        speaker=row.speaker,
        confidence=row.confidence,
        order_idx=row.order_idx,
        source=row.source,
    )


@router.get("/materials/{material_id}/media", response_model=MediaOut)
def material_media(material_id: str, session: Session = Depends(get_session)) -> MediaOut:
    profile = ensure_default_profile(session)
    material = _material(session, material_id, profile.id)
    rows = list_segments(session, material, profile.id)
    session.commit()
    ref = MediaRef.from_material(material)
    return MediaOut(
        material_id=ref.material_id,
        course_id=material.course_id,
        title=material.title,
        blob_sha=ref.blob_sha,
        mime=ref.mime,
        duration_ms=ref.duration_ms,
        segments=[_segment_out(row) for row in rows],
    )


@router.post(
    "/materials/{material_id}/media/segments",
    response_model=MediaSegmentOut,
    status_code=201,
)
def create_segment(
    material_id: str,
    body: SegmentIn,
    session: Session = Depends(get_session),
) -> MediaSegmentOut:
    profile = ensure_default_profile(session)
    material = _material(session, material_id, profile.id)
    try:
        row = add_segment(
            session,
            profile_id=profile.id,
            material_id=material.id,
            start_ms=body.start_ms,
            end_ms=body.end_ms,
            text=body.text,
            speaker=body.speaker,
            order_idx=body.order_idx,
        )
    except MediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    _rebuild(session, material)
    session.commit()
    return _segment_out(row)


@router.post("/materials/{material_id}/media/rebuild", response_model=MediaRebuildOut)
def rebuild_media_transcript(
    material_id: str, session: Session = Depends(get_session)
) -> MediaRebuildOut:
    profile = ensure_default_profile(session)
    material = _material(session, material_id, profile.id)
    extraction = rebuild_transcript_extraction(session, material)
    if extraction is None:
        raise HTTPException(status_code=422, detail="there are no transcript segments to rebuild")
    JobRunner.enqueue(
        session,
        "postprocess",
        PostprocessPayload(material_id=material.id, extraction_id=extraction.id),
    )
    session.commit()
    return MediaRebuildOut(extraction_id=extraction.id, version=extraction.version)


def _load_segment(session: Session, segment_id: str, profile_id: str) -> MediaSegment:
    row = session.get(MediaSegment, segment_id)
    if row is None or row.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="media segment not found")
    return row


@router.patch("/media/segments/{segment_id}", response_model=MediaSegmentOut)
def patch_segment(
    segment_id: str,
    body: SegmentPatch,
    session: Session = Depends(get_session),
) -> MediaSegmentOut:
    profile = ensure_default_profile(session)
    row = _load_segment(session, segment_id, profile.id)
    update_segment(session, row, text=body.text, speaker=body.speaker)
    if row.material_id is not None:
        material = session.get(Material, row.material_id)
        if material is not None:
            _rebuild(session, material)
    session.commit()
    return _segment_out(row)


@router.post("/media/segments/{segment_id}/split", response_model=MediaSegmentOut, status_code=201)
def split_media_segment(
    segment_id: str,
    body: SegmentSplit,
    session: Session = Depends(get_session),
) -> MediaSegmentOut:
    profile = ensure_default_profile(session)
    row = _load_segment(session, segment_id, profile.id)
    try:
        second = split_segment(session, row, body.at_ms)
    except MediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if row.material_id:
        material = session.get(Material, row.material_id)
        if material is not None:
            _rebuild(session, material)
    session.commit()
    return _segment_out(second)


@router.post("/media/segments/merge", response_model=MediaSegmentOut)
def merge_media_segments(
    body: SegmentMerge,
    session: Session = Depends(get_session),
) -> MediaSegmentOut:
    profile = ensure_default_profile(session)
    first = _load_segment(session, body.first_id, profile.id)
    second = _load_segment(session, body.second_id, profile.id)
    try:
        merged = merge_segments(session, first, second)
    except MediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if merged.material_id:
        material = session.get(Material, merged.material_id)
        if material is not None:
            _rebuild(session, material)
    session.commit()
    return _segment_out(merged)


@router.delete("/media/segments/{segment_id}", status_code=204)
def delete_segment(segment_id: str, session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    row = _load_segment(session, segment_id, profile.id)
    material = session.get(Material, row.material_id) if row.material_id else None
    session.delete(row)
    if material is not None:
        _rebuild(session, material)
    session.commit()
