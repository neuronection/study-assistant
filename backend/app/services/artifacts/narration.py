from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import ArtifactKind, ArtifactStatus
from ...domain.models import (
    Artifact,
    Course,
    Extraction,
    Material,
    MaterialIndexCard,
    MaterialLink,
)
from ...domain.payloads import ArtifactSpec, NarrationSection
from ...jobs.payloads import ArtifactRenderPayload
from ...jobs.runner import JobRunner
from ..knowledge.tree import TreeError, TreeService
from ..platform.metrics import answer_rows, due_cards_count, weakness_matrix
from .spec import ArtifactError, validate_artifact_spec


def _node_title(session: Session, course_id: str, node_id: str | None) -> tuple[str, str | None]:
    try:
        tree = TreeService(session)
        node = tree.get(node_id) if node_id else tree.ensure_root(course_id)
    except TreeError as error:
        raise ArtifactError(str(error)) from error
    if node.course_id != course_id:
        raise ArtifactError("node belongs to a different course")
    return node.title, node.id


def _source_materials(session: Session, course_id: str, node_id: str | None) -> list[Material]:
    if node_id is None:
        return []
    node_ids = TreeService(session).scoped_node_ids(node_id, include_children=True)
    rows = session.execute(
        select(Material, MaterialLink)
        .join(MaterialLink, MaterialLink.material_id == Material.id)
        .where(MaterialLink.node_id.in_(node_ids), Material.course_id == course_id)
        .order_by(Material.created_at.desc())
        .limit(4)
    ).all()
    return [material for material, _link in rows]


def build_narration(
    session: Session,
    *,
    course_id: str,
    node_id: str | None,
    title: str | None,
    length_minutes: int,
    voice: str | None,
) -> ArtifactSpec:
    course = session.get(Course, course_id)
    if course is None:
        raise ArtifactError("course not found")
    node_title, resolved_node = _node_title(session, course_id, node_id)
    sources = _source_materials(session, course_id, resolved_node)
    due = due_cards_count(session, course.profile_id, course_id)
    weak = [
        cell
        for cell in weakness_matrix(answer_rows(session, course.profile_id, course_id))
        if cell.get("enough_data")
    ]
    weak.sort(key=lambda cell: -float(cell.get("weakness_score", 0)))
    sections: list[NarrationSection] = [
        NarrationSection(
            kind="today",
            title="Today",
            script=(
                f"Today, {date.today().isoformat()}. This is a short study brief for "
                f"{node_title}. {due} cards are due now. Listen for the ideas you want "
                "to review next."
            ),
        )
    ]
    if weak:
        sections.append(
            NarrationSection(
                kind="weak",
                title="Weak spots",
                script="Two weak spots from recent answers: "
                + "; ".join(
                    f"{cell['concept']} with {cell['skill']} at "
                    f"{round(float(cell['accuracy']) * 100)} percent"
                    for cell in weak[:2]
                )
                + ".",
            )
        )
    citations: list[str] = []
    for material in sources:
        card = session.get(MaterialIndexCard, material.id)
        summary = (card.summary if card is not None else None) or ""
        if not summary:
            extraction = session.scalars(
                select(Extraction)
                .where(Extraction.material_id == material.id)
                .order_by(Extraction.version.desc())
                .limit(1)
            ).first()
            summary = extraction.markdown[:700] if extraction is not None else ""
        if not summary.strip():
            continue
        citations.append(material.id)
        sections.append(
            NarrationSection(
                kind="material",
                title=material.title,
                script=summary.strip(),
                citations=[material.id],
                source_refs=[material.id],
            )
        )
        if len(sections) >= 6:
            break
    if len(sections) == 1:
        sections.append(
            NarrationSection(
                kind="material",
                title="No source summary yet",
                script=(
                    "There is no indexed material summary for this topic yet. "
                    "Add a material or generate a study guide, then narrate again."
                ),
            )
        )
    sections.append(
        NarrationSection(
            kind="next",
            title="Next",
            script=(
                f"Next, open {node_title} and review the weakest topic or the next item "
                "on your plan. Keep the session short and active."
            ),
            citations=citations,
            source_refs=citations,
        )
    )
    script = "\n\n".join(
        f"{section['title']}. {section['script']}" for section in sections
    )
    spec = ArtifactSpec(
        kind=ArtifactKind.AUDIO_BRIEF.value,
        title=(title or f"Narrate: {node_title}")[:200],
        length_minutes=max(1, min(length_minutes, 20)),
        voice=voice,
        script=script,
        renderer="pending",
        sections=sections,
        chapters=[
            {"title": section["title"], "script": section["script"], "kind": section["kind"]}
            for section in sections
        ],
        model=None,
    )
    return validate_artifact_spec(spec)


def create_audio_brief(
    session: Session,
    *,
    profile_id: str,
    course_id: str,
    node_id: str | None,
    title: str | None,
    length_minutes: int,
    voice: str | None,
    regenerate: bool,
) -> Artifact:
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile_id:
        raise ArtifactError("course not found")
    spec = build_narration(
        session,
        course_id=course_id,
        node_id=node_id,
        title=title,
        length_minutes=length_minutes,
        voice=voice,
    )
    existing = session.scalars(
        select(Artifact).where(
            Artifact.profile_id == profile_id,
            Artifact.course_id == course_id,
            Artifact.node_id == node_id,
            Artifact.kind == ArtifactKind.AUDIO_BRIEF.value,
            Artifact.status != ArtifactStatus.FAILED.value,
        )
    ).first()
    if existing is not None and not regenerate:
        raise ArtifactError(
            "an audio brief already exists at this node — pass regenerate=true to replace it"
        )
    artifact = existing or Artifact(
        profile_id=profile_id,
        course_id=course_id,
        node_id=node_id,
        kind=ArtifactKind.AUDIO_BRIEF.value,
        title=spec["title"],
    )
    artifact.title = spec["title"]
    artifact.spec = spec
    artifact.status = ArtifactStatus.PENDING.value
    artifact.spec_schema_version = 1
    artifact.model = None
    artifact.voice = voice
    session.add(artifact)
    session.flush()
    job = JobRunner.enqueue(
        session,
        "artifact_render",
        ArtifactRenderPayload(artifact_id=artifact.id),
    )
    artifact.job_id = job.id
    session.flush()
    return artifact
