from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.vocab import ArtifactStatus
from ..domain.models import Artifact
from ..jobs.payloads import ArtifactRenderPayload
from ..jobs.runner import JobRunner
from ..services.artifacts.narration import create_audio_brief
from ..services.artifacts.spec import ArtifactError
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


class NarrationIn(BaseModel):
    course_id: str
    node_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    length_minutes: int = Field(default=5, ge=1, le=20)
    voice: str | None = Field(default=None, max_length=100)
    regenerate: bool = False


class ArtifactOut(BaseModel):
    id: str
    course_id: str
    node_id: str | None
    kind: str
    title: str
    status: str
    spec: dict[str, Any]
    output_material_id: str | None
    job_id: str | None
    model: str | None
    voice: str | None
    created_at: datetime


def _out(artifact: Artifact) -> ArtifactOut:
    return ArtifactOut(
        id=artifact.id,
        course_id=artifact.course_id,
        node_id=artifact.node_id,
        kind=artifact.kind,
        title=artifact.title,
        status=artifact.status,
        spec=dict(artifact.spec or {}),
        output_material_id=artifact.output_material_id,
        job_id=artifact.job_id,
        model=artifact.model,
        voice=artifact.voice,
        created_at=artifact.created_at,
    )


def _load(session: Session, artifact_id: str, profile_id: str) -> Artifact:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None or artifact.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="artifact not found")
    return artifact


@router.post("/narrate", response_model=ArtifactOut, status_code=201)
def narrate_topic(body: NarrationIn, session: Session = Depends(get_session)) -> ArtifactOut:
    profile = ensure_default_profile(session)
    try:
        artifact = create_audio_brief(
            session,
            profile_id=profile.id,
            course_id=body.course_id,
            node_id=body.node_id,
            title=body.title,
            length_minutes=body.length_minutes,
            voice=body.voice,
            regenerate=body.regenerate,
        )
    except ArtifactError as error:
        session.rollback()
        status = 409 if "already exists" in str(error) else 422
        raise HTTPException(status_code=status, detail=str(error)) from error
    session.commit()
    return _out(artifact)


@router.get("", response_model=list[ArtifactOut])
def list_artifacts(
    course_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[ArtifactOut]:
    profile = ensure_default_profile(session)
    statement = select(Artifact).where(Artifact.profile_id == profile.id)
    if course_id is not None:
        statement = statement.where(Artifact.course_id == course_id)
    rows = session.scalars(
        statement.order_by(Artifact.created_at.desc(), Artifact.id.desc()).limit(100)
    )
    return [_out(row) for row in rows]


@router.get("/{artifact_id}", response_model=ArtifactOut)
def get_artifact(artifact_id: str, session: Session = Depends(get_session)) -> ArtifactOut:
    profile = ensure_default_profile(session)
    return _out(_load(session, artifact_id, profile.id))


@router.post("/{artifact_id}/retry", response_model=ArtifactOut, status_code=201)
def retry_artifact(artifact_id: str, session: Session = Depends(get_session)) -> ArtifactOut:
    profile = ensure_default_profile(session)
    artifact = _load(session, artifact_id, profile.id)
    if artifact.status not in (ArtifactStatus.FAILED.value, ArtifactStatus.STALE.value):
        raise HTTPException(
            status_code=422, detail="only a failed or stale artifact can be retried"
        )
    artifact.status = ArtifactStatus.PENDING.value
    job = JobRunner.enqueue(
        session, "artifact_render", ArtifactRenderPayload(artifact_id=artifact.id)
    )
    artifact.job_id = job.id
    session.commit()
    return _out(artifact)


@router.delete("/{artifact_id}", status_code=204)
def delete_artifact(artifact_id: str, session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    artifact = _load(session, artifact_id, profile.id)
    session.delete(artifact)
    session.commit()
