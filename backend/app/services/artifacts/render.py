from typing import Any, cast

from sqlalchemy.orm import Session

from ...ai.gateway import BudgetExceeded, ProviderError, TaskUnassigned
from ...core.vocab import ArtifactStatus
from ...domain.models import Artifact
from ...domain.payloads import ArtifactSpec
from ...jobs.runner import JobError, JobHandler, ProgressReporter
from ..content.materials import MaterialsService
from .registry import renderer_for


def render_artifact(
    session: Session,
    artifact: Artifact,
    *,
    gateway: Any,
    blobs: Any,
    jobs: Any,
    report: ProgressReporter,
) -> None:
    spec = dict(artifact.spec or {})
    artifact.status = ArtifactStatus.RENDERING.value
    session.flush()
    report(10, "render")
    renderer = renderer_for(artifact.kind)
    material = renderer(
        session,
        artifact,
        spec,
        gateway=gateway,
        blobs=blobs,
        jobs=jobs,
        report=report,
    )
    artifact.output_material_id = material.id
    artifact.status = ArtifactStatus.READY.value
    artifact.spec = cast(Any, dict(spec))
    session.flush()
    report(100, "done")


def _mark_failed(session: Session, artifact: Artifact, error: Exception) -> None:
    artifact.status = ArtifactStatus.FAILED.value
    session.commit()
    raise JobError(f"artifact render failed: {error}") from error


def make_artifact_render_handler(
    gateway: Any, blobs: Any, jobs_provider: Any = None
) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        from ...jobs.payloads import ArtifactRenderPayload

        payload = cast(ArtifactRenderPayload, job.payload or {})
        artifact_id = payload.get("artifact_id")
        if not artifact_id:
            raise JobError("artifact render payload missing artifact_id")
        artifact = session.get(Artifact, str(artifact_id))
        if artifact is None:
            raise JobError("artifact not found")
        jobs = jobs_provider() if callable(jobs_provider) else jobs_provider
        try:
            render_artifact(
                session,
                artifact,
                gateway=gateway,
                blobs=blobs,
                jobs=jobs,
                report=report,
            )
        except (TaskUnassigned, ProviderError, BudgetExceeded) as error:
            _mark_failed(session, artifact, error)
        except Exception as error:
            _mark_failed(session, artifact, error)
        session.commit()

    return handler


def make_script_material(
    session: Session,
    artifact: Artifact,
    spec: ArtifactSpec,
    *,
    blobs: Any,
    jobs: Any,
    renderer: str,
) -> Any:
    material, _deduped = MaterialsService(session, blobs).create_text(
        profile_id=artifact.profile_id,
        course_id=artifact.course_id,
        filename=f"{artifact.title}.md",
        content=spec.get("script", ""),
        description=f"Artifact script ({renderer})",
    )
    material.provenance = cast(Any, {
        "source": "artifact",
        "kind": artifact.kind,
        "renderer": renderer,
        "model": artifact.model,
    })
    session.flush()
    if jobs is not None:
        MaterialsService(session, blobs).queue_ingest(material, jobs)
    return material
