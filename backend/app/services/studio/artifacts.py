import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import StudioArtifactKind
from ...domain.models import Extraction, Material, StudioArtifact
from ...domain.payloads import StudioArtifactSpec, StudioSlide
from ..content.materials import MaterialsService

_HEADING = re.compile(r"^(#{1,3})\s+(.+)$")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_ALLOWED_LAYOUTS = {
    "title",
    "section",
    "bullets",
    "two_column",
    "image",
    "math",
    "chart",
    "quote",
    "summary",
}


class StudioError(ValueError):
    pass


def _clean(text: str) -> str:
    value = text.strip()
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", " ", value).strip()


def _bullets(paragraph: str, limit: int = 5) -> list[str]:
    text = _clean(paragraph)
    if not text:
        return []
    parts = [part.strip(" -") for part in _SENTENCE.split(text) if part.strip(" -")]
    if len(parts) == 1:
        parts = [part.strip(" -") for part in text.splitlines() if part.strip(" -")]
    return [part[:240] for part in parts[:limit]]


def _sections(markdown: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current: list[str] = []
    for raw in markdown.splitlines():
        match = _HEADING.match(raw.strip())
        if match:
            if current_title or current:
                sections.append((current_title, current))
            current_title = _clean(match.group(2))
            current = []
            continue
        if raw.strip() and not raw.strip().startswith(("|", "```", "$$")):
            current.append(raw.strip())
    if current_title or current:
        sections.append((current_title, current))
    return [(title, "\n\n".join(lines)) for title, lines in sections if title or lines]


def build_spec(markdown: str, title: str, kind: str) -> StudioArtifactSpec:
    if kind not in {member.value for member in StudioArtifactKind}:
        raise StudioError("unknown studio artifact kind")
    sections = _sections(markdown)
    slides: list[StudioSlide] = [
        StudioSlide(layout="title", title=title.strip()[:200], bullets=[], body_md=None)
    ]
    for section_title, body in sections[:19]:
        points = _bullets(body)
        if not points and not section_title:
            continue
        slides.append(
            StudioSlide(
                layout="bullets" if points else "section",
                title=(section_title or title)[:200],
                bullets=points,
                body_md=None,
            )
        )
    if len(slides) == 1 and sections:
        section_title, body = sections[0]
        slides.append(
            StudioSlide(
                layout="bullets",
                title=(section_title or title)[:200],
                bullets=_bullets(body),
                body_md=None,
            )
        )
    return StudioArtifactSpec(
        kind=kind,
        title=title.strip()[:200],
        subtitle=None,
        theme="tokens",
        slides=slides[:20],
        source_title=None,
    )


def validate_spec(spec: Any) -> StudioArtifactSpec:
    if not isinstance(spec, dict):
        raise StudioError("spec must be an object")
    title = str(spec.get("title", "")).strip()
    if not title:
        raise StudioError("spec title is required")
    kind = str(spec.get("kind", ""))
    if kind not in {member.value for member in StudioArtifactKind}:
        raise StudioError("unknown studio artifact kind")
    slides = spec.get("slides")
    if not isinstance(slides, list) or not 1 <= len(slides) <= 20:
        raise StudioError("a studio artifact needs 1-20 slides")
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            raise StudioError(f"slide {index + 1} must be an object")
        layout = str(slide.get("layout", "bullets"))
        if layout not in _ALLOWED_LAYOUTS:
            raise StudioError(f"slide {index + 1} has an unknown layout")
        if not str(slide.get("title", "")).strip():
            raise StudioError(f"slide {index + 1} needs a title")
        bullets = slide.get("bullets") or []
        if not isinstance(bullets, list) or len(bullets) > 8:
            raise StudioError(f"slide {index + 1} allows at most 8 bullets")
        if any(not isinstance(bullet, str) or not bullet.strip() for bullet in bullets):
            raise StudioError(f"slide {index + 1} has an empty bullet")
    return StudioArtifactSpec(
        kind=kind,
        title=title[:200],
        subtitle=(str(spec.get("subtitle")).strip() if spec.get("subtitle") else None),
        theme=str(spec.get("theme") or "tokens"),
        slides=[
            StudioSlide(
                layout=str(slide.get("layout", "bullets")),
                title=str(slide["title"])[:200],
                bullets=[str(bullet)[:240] for bullet in (slide.get("bullets") or [])],
                body_md=(str(slide["body_md"]) if slide.get("body_md") else None),
                notes=(str(slide["notes"]) if slide.get("notes") else None),
            )
            for slide in slides
        ],
        source_title=(str(spec["source_title"]) if spec.get("source_title") else None),
    )


def render_markdown(spec: StudioArtifactSpec) -> str:
    lines = [f"# {spec.get('title', 'Studio artifact')}", ""]
    for slide in spec.get("slides", []):
        if slide.get("layout") == "title":
            continue
        lines += [f"## {slide.get('title', '')}", ""]
        for bullet in slide.get("bullets", []):
            lines.append(f"- {bullet}")
        if slide.get("body_md"):
            lines += ["", str(slide["body_md"])]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def create_artifact(
    session: Session,
    *,
    blobs: Any,
    jobs: Any,
    profile_id: str,
    course_id: str,
    material_id: str,
    kind: str,
    title: str | None = None,
) -> StudioArtifact:
    source = session.get(Material, material_id)
    if source is None or source.profile_id != profile_id or source.course_id != course_id:
        raise StudioError("source material not found in this course")
    extraction = session.scalars(
        select(Extraction)
        .where(Extraction.material_id == source.id)
        .order_by(Extraction.version.desc())
        .limit(1)
    ).first()
    markdown = extraction.markdown if extraction is not None else source.title
    resolved_title = (title or source.title).strip() or "Studio artifact"
    spec = build_spec(markdown, resolved_title, kind)
    spec["source_title"] = source.title
    validated = validate_spec(spec)
    artifact = StudioArtifact(
        profile_id=profile_id,
        course_id=course_id,
        kind=kind,
        title=validated["title"],
        spec=validated,
        source_material_id=source.id,
    )
    session.add(artifact)
    session.flush()
    generated, _deduped = MaterialsService(session, blobs).create_text(
        profile_id=profile_id,
        course_id=course_id,
        filename=f"{validated['title']}.md",
        content=render_markdown(validated),
        description=f"Studio {kind.replace('_', ' ')} generated from {source.title}",
    )
    artifact.material_id = generated.id
    session.flush()
    if jobs is not None:
        MaterialsService(session, blobs).queue_ingest(generated, jobs)
    return artifact
