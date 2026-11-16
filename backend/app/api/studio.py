from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.vocab import StudioArtifactKind
from ..domain.models import Material, StudioArtifact
from ..services.platform.profiles import ensure_default_profile
from ..services.studio.artifacts import (
    StudioError,
    create_artifact,
    render_markdown,
    validate_spec,
)
from .deps import get_session

router = APIRouter(prefix="/studio", tags=["studio"])


class StudioCreateIn(BaseModel):
    material_id: str
    kind: str = Field(default=StudioArtifactKind.SLIDE_DECK.value, max_length=20)
    title: str | None = Field(default=None, max_length=200)


class StudioUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    spec: dict[str, Any] | None = None


class StudioOut(BaseModel):
    id: str
    course_id: str
    kind: str
    title: str
    spec: dict[str, Any]
    source_material_id: str | None
    material_id: str | None
    created_at: datetime


class StudioMarkdownOut(BaseModel):
    markdown: str


def _out(artifact: StudioArtifact) -> StudioOut:
    return StudioOut(
        id=artifact.id,
        course_id=artifact.course_id,
        kind=artifact.kind,
        title=artifact.title,
        spec=dict(artifact.spec or {}),
        source_material_id=artifact.source_material_id,
        material_id=artifact.material_id,
        created_at=artifact.created_at,
    )


def _load(session: Session, artifact_id: str, profile_id: str) -> StudioArtifact:
    artifact = session.get(StudioArtifact, artifact_id)
    if artifact is None or artifact.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="studio artifact not found")
    return artifact


@router.post("/artifacts", response_model=StudioOut, status_code=201)
def create_studio_artifact(
    body: StudioCreateIn,
    request: Request,
    session: Session = Depends(get_session),
) -> StudioOut:
    profile = ensure_default_profile(session)
    if body.kind not in {member.value for member in StudioArtifactKind}:
        raise HTTPException(status_code=422, detail="unknown studio artifact kind")
    source = session.get(Material, body.material_id)
    if source is None or source.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="source material not found")
    try:
        artifact = create_artifact(
            session,
            blobs=request.app.state.blobs,
            jobs=request.app.state.jobs,
            profile_id=profile.id,
            course_id=source.course_id,
            material_id=source.id,
            kind=body.kind,
            title=body.title,
        )
    except (StudioError, ValueError) as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(artifact)


@router.get("/artifacts", response_model=list[StudioOut])
def list_studio_artifacts(
    course_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[StudioOut]:
    profile = ensure_default_profile(session)
    statement = select(StudioArtifact).where(StudioArtifact.profile_id == profile.id)
    if course_id is not None:
        statement = statement.where(StudioArtifact.course_id == course_id)
    rows = session.scalars(
        statement.order_by(StudioArtifact.created_at.desc(), StudioArtifact.id.desc())
    )
    return [_out(row) for row in rows]


@router.get("/artifacts/{artifact_id}", response_model=StudioOut)
def get_studio_artifact(artifact_id: str, session: Session = Depends(get_session)) -> StudioOut:
    profile = ensure_default_profile(session)
    return _out(_load(session, artifact_id, profile.id))


@router.patch("/artifacts/{artifact_id}", response_model=StudioOut)
def update_studio_artifact(
    artifact_id: str,
    body: StudioUpdateIn,
    session: Session = Depends(get_session),
) -> StudioOut:
    profile = ensure_default_profile(session)
    artifact = _load(session, artifact_id, profile.id)
    if body.title is not None:
        artifact.title = body.title.strip()
    if body.spec is not None:
        try:
            artifact.spec = validate_spec(body.spec)
        except StudioError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(artifact)


@router.get("/artifacts/{artifact_id}/markdown", response_model=StudioMarkdownOut)
def studio_markdown(artifact_id: str, session: Session = Depends(get_session)) -> StudioMarkdownOut:
    profile = ensure_default_profile(session)
    artifact = _load(session, artifact_id, profile.id)
    return StudioMarkdownOut(markdown=render_markdown(artifact.spec or {}))


@router.delete("/artifacts/{artifact_id}", status_code=204)
def delete_studio_artifact(artifact_id: str, session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    artifact = _load(session, artifact_id, profile.id)
    session.delete(artifact)
    session.commit()
