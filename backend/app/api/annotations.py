from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import AnchorSource
from ..domain.anchors import AnchorPayloadError
from ..domain.models import DocumentAnchor
from ..services.content.annotations import (
    AnchorConflict,
    AnchorNotFound,
    create_anchor,
    delete_anchor,
    get_anchor,
    list_anchors,
    update_anchor,
)
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(tags=["annotations"])


class AnchorCreateIn(BaseModel):
    anchor_kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    quote: str | None = None
    page: int | None = None
    color: str = "yellow"
    note_md: str | None = None
    source: str = AnchorSource.USER.value


class AnchorPatchIn(BaseModel):
    payload: dict[str, Any] | None = None
    color: str | None = None
    note_md: str | None = None


class AnchorOut(BaseModel):
    id: str
    material_id: str | None
    anchor_kind: str
    page: int | None
    quote: str | None
    payload: dict[str, Any]
    color: str
    note_md: str | None
    source: str
    created_at: datetime
    updated_at: datetime
    orphaned: bool


def _out(anchor: DocumentAnchor) -> AnchorOut:
    return AnchorOut(
        id=anchor.id,
        material_id=anchor.material_id,
        anchor_kind=anchor.anchor_kind,
        page=anchor.page,
        quote=anchor.quote,
        payload=dict(anchor.payload or {}),
        color=anchor.color,
        note_md=anchor.note_md,
        source=anchor.source,
        created_at=anchor.created_at,
        updated_at=anchor.updated_at,
        orphaned=anchor.orphaned_at is not None,
    )


@router.get("/materials/{material_id}/anchors", response_model=list[AnchorOut])
def list_material_anchors(
    material_id: str,
    include_orphaned: bool = True,
    session: Session = Depends(get_session),
) -> list[AnchorOut]:
    profile = ensure_default_profile(session)
    try:
        anchors = list_anchors(
            session,
            profile_id=profile.id,
            material_id=material_id,
            include_orphaned=include_orphaned,
        )
    except AnchorNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return [_out(anchor) for anchor in anchors]


@router.post("/materials/{material_id}/anchors", response_model=AnchorOut, status_code=201)
def create_material_anchor(
    material_id: str,
    body: AnchorCreateIn,
    session: Session = Depends(get_session),
) -> AnchorOut:
    profile = ensure_default_profile(session)
    try:
        anchor = create_anchor(
            session,
            profile_id=profile.id,
            material_id=material_id,
            anchor_kind=body.anchor_kind,
            quote=body.quote,
            payload=body.payload,
            page=body.page,
            color=body.color,
            note_md=body.note_md,
            source=body.source,
        )
    except AnchorNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except AnchorConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except AnchorPayloadError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(anchor)


@router.get("/anchors/{anchor_id}", response_model=AnchorOut)
def get_anchor_endpoint(
    anchor_id: str,
    session: Session = Depends(get_session),
) -> AnchorOut:
    profile = ensure_default_profile(session)
    try:
        anchor = get_anchor(session, profile_id=profile.id, anchor_id=anchor_id)
    except AnchorNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _out(anchor)


@router.patch("/anchors/{anchor_id}", response_model=AnchorOut)
def patch_anchor(
    anchor_id: str,
    body: AnchorPatchIn,
    session: Session = Depends(get_session),
) -> AnchorOut:
    profile = ensure_default_profile(session)
    try:
        anchor = update_anchor(
            session,
            profile_id=profile.id,
            anchor_id=anchor_id,
            color=body.color,
            note_md=(body.note_md or "") if "note_md" in body.model_fields_set else None,
            payload=body.payload,
        )
    except AnchorNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except AnchorPayloadError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(anchor)


@router.delete("/anchors/{anchor_id}", status_code=204)
def remove_anchor(
    anchor_id: str,
    session: Session = Depends(get_session),
) -> None:
    profile = ensure_default_profile(session)
    try:
        delete_anchor(session, profile_id=profile.id, anchor_id=anchor_id)
    except AnchorNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    session.commit()
