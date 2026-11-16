from typing import Any

from ...core.vocab import ArtifactKind
from ...domain.payloads import ArtifactChapter, ArtifactSpec, NarrationSection


class ArtifactError(ValueError):
    pass


def validate_artifact_spec(spec: Any) -> ArtifactSpec:
    if not isinstance(spec, dict):
        raise ArtifactError("artifact spec must be an object")
    kind = str(spec.get("kind", ""))
    if kind not in {member.value for member in ArtifactKind}:
        raise ArtifactError("unknown artifact kind")
    title = str(spec.get("title", "")).strip()
    if not title:
        raise ArtifactError("artifact title is required")
    if kind == ArtifactKind.AUDIO_BRIEF.value:
        script = str(spec.get("script", "")).strip()
        if not script:
            raise ArtifactError("audio brief needs a script")
        if len(script) > 40_000:
            raise ArtifactError("audio brief script is too long")
        sections = spec.get("sections") or []
        if not isinstance(sections, list):
            raise ArtifactError("artifact sections must be a list")
        clean_sections = []
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                raise ArtifactError(f"section {index + 1} must be an object")
            clean_sections.append(
                NarrationSection(
                    kind=str(section.get("kind") or "section"),
                    title=str(section.get("title") or ""),
                    script=str(section.get("script") or ""),
                    citations=[str(value) for value in (section.get("citations") or [])],
                    source_refs=[str(value) for value in (section.get("source_refs") or [])],
                )
            )
        return ArtifactSpec(
            kind=kind,
            title=title[:200],
            length_minutes=int(spec.get("length_minutes") or 5),
            voice=(str(spec["voice"]) if spec.get("voice") else None),
            script=script,
            renderer=str(spec.get("renderer") or "pending"),
            sections=clean_sections,
            chapters=[
                ArtifactChapter(
                    title=str(chapter.get("title") or ""),
                    script=str(chapter.get("script") or ""),
                    kind=str(chapter.get("kind") or "section"),
                )
                for chapter in (spec.get("chapters") or [])
                if isinstance(chapter, dict)
            ],
            model=(str(spec["model"]) if spec.get("model") else None),
        )
    if not spec.get("slides"):
        raise ArtifactError("this artifact kind needs a renderable spec")
    return ArtifactSpec(
        kind=kind,
        title=title[:200],
        length_minutes=int(spec.get("length_minutes") or 5),
        voice=(str(spec["voice"]) if spec.get("voice") else None),
        script=str(spec.get("script") or ""),
        renderer=str(spec.get("renderer") or "pending"),
        sections=[],
        chapters=[],
        model=(str(spec["model"]) if spec.get("model") else None),
    )
