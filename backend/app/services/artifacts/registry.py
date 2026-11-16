from collections.abc import Callable
from typing import Any, cast

from sqlalchemy.orm import Session

from ...ai.gateway import BudgetExceeded, ProviderError, TaskUnassigned
from ...domain.models import Artifact
from ...domain.payloads import ArtifactSpec
from ...jobs.runner import ProgressReporter
from ..content.materials import MaterialsService

Renderer = Callable[..., Any]


def _audio(
    session: Session,
    artifact: Artifact,
    spec: ArtifactSpec,
    *,
    gateway: Any,
    blobs: Any,
    jobs: Any,
    report: ProgressReporter,
) -> Any:
    script = spec.get("script", "").strip()
    if not script:
        raise ValueError("audio brief has no script")
    try:
        speech = gateway.speak(
            script,
            voice=artifact.voice,
            course_id=artifact.course_id,
        )
    except (TaskUnassigned, ProviderError, BudgetExceeded):
        from .render import make_script_material

        spec["renderer"] = "browser"
        spec["model"] = None
        artifact.model = None
        artifact.spec = cast(Any, dict(spec))
        return make_script_material(
            session, artifact, spec, blobs=blobs, jobs=jobs, renderer="browser"
        )
    extension = "wav" if speech.mime.startswith("audio/wav") else "mp3"
    material, _deduped = MaterialsService(session, blobs).upload(
        profile_id=artifact.profile_id,
        filename=f"{artifact.title}.{extension}",
        data=speech.audio,
        mime=speech.mime,
        course_id=artifact.course_id,
    )
    material.provenance = cast(
        Any,
        {
            "source": "artifact",
            "kind": artifact.kind,
            "renderer": "provider",
            "model": speech.model,
        },
    )
    spec["renderer"] = "provider"
    spec["model"] = speech.model
    artifact.model = speech.model
    artifact.spec = spec
    session.flush()
    if jobs is not None:
        MaterialsService(session, blobs).queue_ingest(material, jobs)
    return material


_RENDERERS: dict[str, Renderer] = {"audio_brief": _audio}


def renderer_for(kind: str) -> Renderer:
    renderer = _RENDERERS.get(kind)
    if renderer is None:
        raise ValueError(f"no artifact renderer for kind {kind}")
    return renderer
