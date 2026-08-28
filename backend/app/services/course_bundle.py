import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__
from ..domain.models import (
    Activity,
    Chunk,
    Concept,
    ConceptLink,
    Course,
    Exercise,
    ExerciseStep,
    Extraction,
    Material,
    MaterialDrawing,
    MaterialFolder,
    MaterialFolderLink,
    MaterialIndexCard,
    MaterialLink,
    NodeConcept,
    Note,
    NoteDrawing,
    Question,
    Skill,
    SkillVersion,
    TreeNode,
    utcnow,
)
from ..pipelines.chunking import chunk_markdown
from ..storage.blobs import blob_path
from ..storage.fts import sync_material_fts
from .drawings import remap_drawing_refs
from .folders import FoldersService
from .materials import extraction_to_blocks

BUNDLE_FORMAT = "ca-course/v1"
MANIFEST_NAME = "manifest.json"
COURSE_NAME = "course.json"
TREE_NAME = "tree.json"
CONCEPTS_NAME = "concepts.json"
MATERIALS_NAME = "materials.json"
FOLDERS_NAME = "folders.json"
NOTES_NAME = "notes.json"
QUIZZES_NAME = "quizzes.json"
EXERCISES_NAME = "exercises.json"
SKILLS_NAME = "skills-overrides.json"
BLOBS_PREFIX = "blobs/"

JSON_NAMES = (
    COURSE_NAME,
    TREE_NAME,
    CONCEPTS_NAME,
    MATERIALS_NAME,
    NOTES_NAME,
    QUIZZES_NAME,
    EXERCISES_NAME,
    SKILLS_NAME,
)


class BundleError(ValueError):
    pass


@dataclass
class BundleData:
    manifest: dict[str, Any]
    course: dict[str, Any]
    tree: list[dict[str, Any]]
    concepts: dict[str, Any]
    materials: list[dict[str, Any]]
    folders: dict[str, Any]
    notes: list[dict[str, Any]]
    quizzes: list[dict[str, Any]]
    exercises: list[dict[str, Any]]
    skills: list[dict[str, Any]]
    blobs: dict[str, bytes]


def _export_course(session: Session, course: Course) -> dict[str, Any]:
    return {
        "title": course.title,
        "description": course.description,
        "subject": course.subject,
        "level": course.level,
        "goals": course.goals,
        "tags": course.tags,
        "color": course.color,
    }


def _export_tree(session: Session, course_id: int) -> list[dict[str, Any]]:
    nodes = list(
        session.scalars(
            select(TreeNode)
            .where(TreeNode.course_id == course_id)
            .order_by(TreeNode.id)
        )
    )
    return [
        {
            "id": node.id,
            "parent_id": node.parent_id,
            "title": node.title,
            "summary": node.summary,
            "objectives": node.objectives,
            "ai_hint": node.ai_hint,
            "order_idx": node.order_idx,
            "is_root": node.is_root,
        }
        for node in nodes
    ]


def _export_concepts(session: Session, course_id: int) -> dict[str, Any]:
    concepts = list(
        session.scalars(select(Concept).where(Concept.course_id == course_id))
    )
    by_id = {concept.id: concept for concept in concepts}
    links = list(
        session.scalars(select(ConceptLink).where(ConceptLink.course_id == course_id))
    )
    coverage = list(
        session.execute(
            select(NodeConcept.node_id, NodeConcept.concept_id, NodeConcept.weight)
        )
    )
    node_ids = set(
        session.scalars(
            select(TreeNode.id).where(TreeNode.course_id == course_id)
        )
    )
    return {
        "concepts": [
            {
                "id": concept.id,
                "name": concept.name,
                "description": concept.description,
                "aliases": concept.aliases,
            }
            for concept in concepts
        ],
        "links": [
            {
                "from_concept_id": link.from_concept_id,
                "to_concept_id": link.to_concept_id,
                "relation": link.relation,
            }
            for link in links
            if link.from_concept_id in by_id and link.to_concept_id in by_id
        ],
        "coverage": [
            {"node_id": node_id, "concept_id": concept_id, "weight": weight}
            for node_id, concept_id, weight in coverage
            if node_id in node_ids and concept_id in by_id
        ],
    }


def _export_materials(session: Session, course_id: int) -> tuple[list[dict[str, Any]], set[str]]:
    materials = list(
        session.scalars(
            select(Material).where(Material.course_id == course_id).order_by(Material.id)
        )
    )
    links = list(
        session.scalars(select(MaterialLink).where(MaterialLink.course_id == course_id))
    )
    links_by_material: dict[int, list[MaterialLink]] = {}
    for link in links:
        links_by_material.setdefault(link.material_id, []).append(link)
    folder_paths = {
        folder.id: folder.path
        for folder in session.scalars(
            select(MaterialFolder).where(
                MaterialFolder.course_id == course_id,
                MaterialFolder.source_id.is_(None),
            )
        )
    }
    shas: set[str] = set()
    out: list[dict[str, Any]] = []
    for material in materials:
        extraction = (
            session.scalars(
                select(Extraction)
                .where(Extraction.material_id == material.id)
                .order_by(Extraction.version.desc())
                .limit(1)
            ).first()
        )
        card = session.get(MaterialIndexCard, material.id)
        if material.blob_sha is not None:
            shas.add(material.blob_sha)
        drawings: list[dict[str, Any]] = []
        for drawing in material.drawings:
            if drawing.png_sha is not None:
                shas.add(drawing.png_sha)
            drawings.append(
                {
                    "id": drawing.id,
                    "strokes": drawing.strokes,
                    "png_sha": drawing.png_sha,
                    "view": drawing.view,
                    "ocr_markdown": drawing.ocr_markdown,
                    "ocr_blocks": drawing.ocr_blocks,
                    "ocr_version": drawing.ocr_version,
                }
            )
        out.append(
            {
                "id": material.id,
                "kind": material.kind,
                "title": material.title,
                "filename": material.filename,
                "mime": material.mime,
                "pages": material.pages,
                "language": material.language,
                "blob_sha": material.blob_sha,
                "provenance": material.provenance,
                "drawings": drawings,
                "extraction": {
                    "version": extraction.version,
                    "extractor": extraction.extractor,
                    "model": extraction.model,
                    "blocks": extraction.blocks,
                    "markdown": extraction.markdown,
                    "language": extraction.language,
                    "reviewed": extraction.reviewed,
                }
                if extraction is not None
                else None,
                "index_card": {
                    "summary": card.summary,
                    "topics": card.topics,
                    "key_terms": card.key_terms,
                    "reading_minutes": card.reading_minutes,
                    "difficulty": card.difficulty,
                }
                if card is not None
                else None,
                "folder_path": (
                    folder_paths[material.folder_id]
                    if material.folder_id is not None
                    and material.folder_id in folder_paths
                    else None
                ),
                "links": [
                    {
                        "node_id": link.node_id,
                        "rationale": link.rationale,
                        "auto_assigned": link.auto_assigned,
                        "confidence": link.confidence,
                    }
                    for link in links_by_material.get(material.id, [])
                ],
            }
        )
    return out, shas


def _export_folders(
    session: Session, course_id: int
) -> tuple[dict[str, Any], list[str]]:
    folders = list(
        session.scalars(
            select(MaterialFolder).where(
                MaterialFolder.course_id == course_id,
                MaterialFolder.source_id.is_(None),
            )
        )
    )
    paths = {folder.id: folder.path for folder in folders}
    links = list(
        session.scalars(
            select(MaterialFolderLink).where(
                MaterialFolderLink.course_id == course_id
            )
        )
    )
    warnings: list[str] = []
    out_links: list[dict[str, Any]] = []
    for link in links:
        path = paths.get(link.folder_id)
        if path is None:
            warnings.append(
                "an assignment of a linked-source folder was not exported "
                "(linked sources are machine-local)"
            )
            continue
        out_links.append(
            {
                "node_id": link.node_id,
                "folder_path": path,
                "rationale": link.rationale,
                "auto_assigned": link.auto_assigned,
                "confidence": link.confidence,
            }
        )
    return (
        {
            "folders": [
                {"path": folder.path, "name": folder.name}
                for folder in sorted(folders, key=lambda entry: entry.path)
            ],
            "links": out_links,
        },
        warnings,
    )


def _export_notes(session: Session, course_id: int) -> tuple[list[dict[str, Any]], set[str]]:
    notes = list(
        session.scalars(
            select(Note).where(Note.course_id == course_id).order_by(Note.id)
        )
    )
    shas: set[str] = set()
    out: list[dict[str, Any]] = []
    for note in notes:
        drawings: list[dict[str, Any]] = []
        for drawing in note.drawings:
            if drawing.png_sha is not None:
                shas.add(drawing.png_sha)
            drawings.append(
                {
                    "strokes": drawing.strokes,
                    "png_sha": drawing.png_sha,
                    "view": drawing.view,
                    "ocr_markdown": drawing.ocr_markdown,
                    "ocr_blocks": drawing.ocr_blocks,
                    "ocr_version": drawing.ocr_version,
                }
            )
        out.append(
            {
                "id": note.id,
                "node_id": note.node_id,
                "title": note.title,
                "tags": note.tags,
                "pinned": note.pinned,
                "body": note.body,
                "drawings": drawings,
            }
        )
    return out, shas


def _export_quizzes(session: Session, course_id: int) -> list[dict[str, Any]]:
    activities = list(
        session.scalars(
            select(Activity).where(Activity.course_id == course_id).order_by(Activity.id)
        )
    )
    out: list[dict[str, Any]] = []
    for activity in activities:
        questions = list(
            session.scalars(
                select(Question)
                .where(Question.activity_id == activity.id)
                .order_by(Question.id)
            )
        )
        out.append(
            {
                "id": activity.id,
                "node_id": activity.node_id,
                "type": activity.type,
                "title": activity.title,
                "config": activity.config,
                "questions": [
                    {
                        "type": question.type,
                        "stem": question.stem,
                        "options": question.options,
                        "answer": question.answer,
                        "explanation": question.explanation,
                        "difficulty": question.difficulty,
                        "bloom": question.bloom,
                        "skill": question.skill,
                        "concept_ids": question.concept_ids,
                        "expected_time_sec": question.expected_time_sec,
                        "curriculum_code": question.curriculum_code,
                        "distractor_misconceptions": question.distractor_misconceptions,
                        "sympy_check": question.sympy_check,
                        "input_modes": question.input_modes,
                        "tags": question.tags,
                        "flag": question.flag,
                    }
                    for question in questions
                ],
            }
        )
    return out


def _export_exercises(session: Session, course_id: int) -> list[dict[str, Any]]:
    exercises = list(
        session.scalars(
            select(Exercise).where(Exercise.course_id == course_id).order_by(Exercise.id)
        )
    )
    out: list[dict[str, Any]] = []
    for exercise in exercises:
        steps = list(
            session.scalars(
                select(ExerciseStep)
                .where(ExerciseStep.exercise_id == exercise.id)
                .order_by(ExerciseStep.order_idx)
            )
        )
        out.append(
            {
                "id": exercise.id,
                "node_id": exercise.node_id,
                "title": exercise.title,
                "kind": exercise.kind,
                "deck_ref": exercise.deck_ref,
                "context": exercise.context,
                "difficulty": exercise.difficulty,
                "created_from": exercise.created_from,
                "steps": [
                    {
                        "order_idx": step.order_idx,
                        "prompt": step.prompt,
                        "expected": step.expected,
                        "hints_pregenerated": step.hints_pregenerated,
                        "rubric": step.rubric,
                    }
                    for step in steps
                ],
            }
        )
    return out


def _export_skills(session: Session, course_id: int) -> list[dict[str, Any]]:
    versions = list(
        session.scalars(
            select(SkillVersion).where(
                SkillVersion.scope_type == "course", SkillVersion.scope_ref == course_id
            )
        )
    )
    out: list[dict[str, Any]] = []
    for version in versions:
        skill = session.get(Skill, version.skill_id)
        if skill is None:
            continue
        out.append(
            {
                "skill": skill.name,
                "version": version.version,
                "system_template": version.system_template,
                "user_template": version.user_template,
                "params": version.params,
                "contract": version.contract,
                "is_active": version.is_active,
            }
        )
    return out


def build_course_bundle(
    session: Session, course: Course, blobs_root: Path
) -> bytes:
    tree = _export_tree(session, course.id)
    concepts = _export_concepts(session, course.id)
    materials, material_shas = _export_materials(session, course.id)
    folders, folder_warnings = _export_folders(session, course.id)
    notes, note_shas = _export_notes(session, course.id)
    quizzes = _export_quizzes(session, course.id)
    exercises = _export_exercises(session, course.id)
    skills = _export_skills(session, course.id)
    shas = {sha for sha in (material_shas | note_shas) if sha}
    warnings: list[str] = list(folder_warnings)
    readable = {sha for sha in shas if blob_path(blobs_root, sha).is_file()}
    for material in materials:
        sha = material["blob_sha"]
        if sha is not None and sha not in readable:
            material["blob_sha"] = None
            warnings.append(
                f"material '{material['title']}' original file is missing on this "
                "machine; exported its extraction only"
            )
    for note in notes:
        for drawing in note["drawings"]:
            sha = drawing["png_sha"]
            if sha is not None and sha not in readable:
                drawing["png_sha"] = None
                warnings.append(
                    f"note '{note['title']}' has a drawing image missing on this "
                    "machine; exported its strokes only"
                )
    for material in materials:
        for drawing in material["drawings"]:
            sha = drawing["png_sha"]
            if sha is not None and sha not in readable:
                drawing["png_sha"] = None
                warnings.append(
                    f"material '{material['title']}' has a drawing image missing on "
                    "this machine; exported its strokes only"
                )
    exportable = shas & readable

    manifest = {
        "format": BUNDLE_FORMAT,
        "app_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "course_title": course.title,
            "counts": {
                "nodes": len(tree),
                "concepts": len(concepts["concepts"]),
                "materials": len(materials),
                "folders": len(folders["folders"]),
                "notes": len(notes),
                "quizzes": len(quizzes),
                "exercises": len(exercises),
                "skill_overrides": len(skills),
                "blobs": len(exportable),
            },
        "warnings": warnings,
    }
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest))
        archive.writestr(COURSE_NAME, json.dumps(_export_course(session, course)))
        archive.writestr(TREE_NAME, json.dumps(tree))
        archive.writestr(CONCEPTS_NAME, json.dumps(concepts))
        archive.writestr(MATERIALS_NAME, json.dumps(materials))
        archive.writestr(FOLDERS_NAME, json.dumps(folders))
        archive.writestr(NOTES_NAME, json.dumps(notes))
        archive.writestr(QUIZZES_NAME, json.dumps(quizzes))
        archive.writestr(EXERCISES_NAME, json.dumps(exercises))
        archive.writestr(SKILLS_NAME, json.dumps(skills))
        for sha in sorted(exportable):
            data = blob_path(blobs_root, sha).read_bytes()
            archive.writestr(f"{BLOBS_PREFIX}{sha}", data)
    return buffer.getvalue()


def read_course_bundle(data: bytes) -> BundleData:
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as error:
        raise BundleError("not a course bundle") from error
    names = set(archive.namelist())
    if MANIFEST_NAME not in names:
        raise BundleError("bundle has no manifest")
    try:
        manifest = json.loads(archive.read(MANIFEST_NAME))
    except ValueError as error:
        raise BundleError("unreadable manifest") from error
    if manifest.get("format") != BUNDLE_FORMAT:
        raise BundleError(f"unsupported bundle format: {manifest.get('format')!r}")

    payload: dict[str, Any] = {}
    for name in JSON_NAMES:
        if name not in names:
            raise BundleError(f"bundle is missing {name}")
        try:
            payload[name] = json.loads(archive.read(name))
        except ValueError as error:
            raise BundleError(f"unreadable {name}") from error
    if FOLDERS_NAME in names:
        try:
            folders_payload: dict[str, Any] = json.loads(archive.read(FOLDERS_NAME))
        except ValueError as error:
            raise BundleError(f"unreadable {FOLDERS_NAME}") from error
    else:
        folders_payload = {"folders": [], "links": []}

    blobs: dict[str, bytes] = {}
    for name in names:
        if name.startswith(BLOBS_PREFIX) and not name.endswith("/"):
            blobs[name[len(BLOBS_PREFIX) :]] = archive.read(name)

    bundle = BundleData(
        manifest=manifest,
        course=payload[COURSE_NAME],
        tree=payload[TREE_NAME],
        concepts=payload[CONCEPTS_NAME],
        materials=payload[MATERIALS_NAME],
        folders=folders_payload,
        notes=payload[NOTES_NAME],
        quizzes=payload[QUIZZES_NAME],
        exercises=payload[EXERCISES_NAME],
        skills=payload[SKILLS_NAME],
        blobs=blobs,
    )
    _validate_bundle(bundle)
    return bundle


def _validate_bundle(bundle: BundleData) -> None:
    if not str(bundle.course.get("title") or "").strip():
        raise BundleError("course has no title")
    node_ids = {entry["id"] for entry in bundle.tree}
    roots = [entry for entry in bundle.tree if entry.get("is_root")]
    if len(roots) != 1:
        raise BundleError("tree must have exactly one root node")
    for entry in bundle.tree:
        if entry.get("is_root"):
            continue
        if entry.get("parent_id") not in node_ids:
            raise BundleError(f"node {entry['id']} has an unknown parent")
    for material in bundle.materials:
        sha = material.get("blob_sha")
        if sha is not None and sha not in bundle.blobs:
            raise BundleError(f"material {material['id']} references a missing blob")
        for link in material.get("links", []):
            if link.get("node_id") not in node_ids:
                raise BundleError("material link references an unknown node")
    folder_paths = {entry.get("path") for entry in bundle.folders.get("folders", [])}
    for link in bundle.folders.get("links", []):
        if link.get("node_id") not in node_ids:
            raise BundleError("folder link references an unknown node")
        if link.get("folder_path") not in folder_paths:
            raise BundleError("folder link references an unknown folder")
    for note in bundle.notes:
        if note.get("node_id") is not None and note["node_id"] not in node_ids:
            raise BundleError(f"note {note['id']} references an unknown node")
        for drawing in note.get("drawings", []):
            sha = drawing.get("png_sha")
            if sha is not None and sha not in bundle.blobs:
                raise BundleError(f"note {note['id']} has a drawing with a missing blob")
    concept_ids = {entry["id"] for entry in bundle.concepts.get("concepts", [])}
    for link in bundle.concepts.get("links", []):
        if (
            link.get("from_concept_id") not in concept_ids
            or link.get("to_concept_id") not in concept_ids
        ):
            raise BundleError("concept link references an unknown concept")
    for quiz in bundle.quizzes:
        if quiz.get("node_id") is not None and quiz["node_id"] not in node_ids:
            raise BundleError(f"quiz {quiz['id']} references an unknown node")
    for exercise in bundle.exercises:
        if exercise.get("node_id") is not None and exercise["node_id"] not in node_ids:
            raise BundleError(f"exercise {exercise['id']} references an unknown node")


def bundle_preview(bundle: BundleData) -> dict[str, Any]:
    counts = bundle.manifest.get("counts", {})
    warnings = [str(entry) for entry in bundle.manifest.get("warnings", [])]
    for material in bundle.materials:
        if material.get("extraction") is None:
            warnings.append(f"material '{material.get('title')}' has no extraction")
    return {
        "title": bundle.course.get("title"),
        "counts": counts,
        "warnings": warnings,
    }


def import_course_bundle(
    session: Session,
    bundle: BundleData,
    profile_id: int,
    blobs_root: Path,
    blob_store: Any,
    existing_titles: set[str],
) -> dict[str, Any]:
    from ..services.tree import TreeService

    title = str(bundle.course["title"]).strip()[:300]
    imported_title = title
    if imported_title in existing_titles:
        imported_title = f"{title[:280]} (imported)"

    course = Course(
        profile_id=profile_id,
        title=imported_title,
        description=bundle.course.get("description"),
        subject=bundle.course.get("subject"),
        level=bundle.course.get("level"),
        goals=bundle.course.get("goals"),
        tags=bundle.course.get("tags"),
        color=bundle.course.get("color"),
    )
    session.add(course)
    session.flush()

    tree = TreeService(session)
    root = tree.ensure_root(course.id)
    node_map: dict[int, int] = {}
    for entry in bundle.tree:
        if entry.get("is_root"):
            node_map[entry["id"]] = root.id
            if entry.get("ai_hint"):
                root.ai_hint = entry["ai_hint"]
            if entry.get("summary"):
                root.summary = entry["summary"]
            continue
    pending = [entry for entry in bundle.tree if not entry.get("is_root")]
    pending.sort(key=lambda entry: (entry.get("depth", 1), entry.get("order_idx", 0), entry["id"]))
    for entry in pending:
        created = tree.create_node(
            course.id,
            node_map[entry["parent_id"]],
            entry["title"],
            summary=entry.get("summary"),
            objectives=entry.get("objectives"),
            ai_hint=entry.get("ai_hint"),
        )
        node_map[entry["id"]] = created.id
    session.flush()

    concept_map: dict[int, int] = {}
    for entry in bundle.concepts.get("concepts", []):
        concept = Concept(
            course_id=course.id,
            name=str(entry["name"])[:200],
            description=entry.get("description"),
            aliases=entry.get("aliases"),
        )
        session.add(concept)
        session.flush()
        concept_map[entry["id"]] = concept.id
    for link in bundle.concepts.get("links", []):
        session.add(
            ConceptLink(
                course_id=course.id,
                from_concept_id=concept_map[link["from_concept_id"]],
                to_concept_id=concept_map[link["to_concept_id"]],
                relation=link["relation"],
            )
        )
    for coverage in bundle.concepts.get("coverage", []):
        session.add(
            NodeConcept(
                node_id=node_map[coverage["node_id"]],
                concept_id=concept_map[coverage["concept_id"]],
                weight=coverage.get("weight"),
            )
        )
    session.flush()

    folder_map: dict[str, int] = {}
    folders_service = FoldersService(session)
    for entry in sorted(
        bundle.folders.get("folders", []), key=lambda item: str(item.get("path"))
    ):
        path = str(entry.get("path") or "")
        name = str(entry.get("name") or path.rsplit("/", 1)[-1])
        parent_path = path.rsplit("/", 1)[0] if "/" in path else None
        parent_id = folder_map.get(parent_path) if parent_path is not None else None
        folder = folders_service.create(
            profile_id=profile_id,
            name=name,
            course_id=course.id,
            parent_id=parent_id,
        )
        folder_map[path] = folder.id
    for link in bundle.folders.get("links", []):
        session.add(
            MaterialFolderLink(
                course_id=course.id,
                node_id=node_map[link["node_id"]],
                folder_id=folder_map[link["folder_path"]],
                rationale=link.get("rationale"),
                auto_assigned=bool(link.get("auto_assigned")),
                confidence=link.get("confidence"),
            )
        )
    session.flush()

    material_map: dict[int, int] = {}
    for entry in bundle.materials:
        sha = entry.get("blob_sha")
        if sha is not None:
            mime = entry.get("mime") or "application/octet-stream"
            blob_store.put(bundle.blobs[sha], mime=mime, session=session)
        entry_folder_path = entry.get("folder_path")
        material = Material(
            profile_id=profile_id,
            course_id=course.id,
            folder_id=(
                folder_map[entry_folder_path]
                if isinstance(entry_folder_path, str) and entry_folder_path in folder_map
                else None
            ),
            kind=str(entry.get("kind") or "document"),
            title=str(entry.get("title") or "Material")[:300],
            blob_sha=sha,
            filename=str(entry.get("filename") or "material.md")[:500],
            mime=entry.get("mime"),
            pages=entry.get("pages"),
            language=entry.get("language"),
            status="ready",
            provenance=entry.get("provenance"),
        )
        session.add(material)
        session.flush()
        material_map[entry["id"]] = material.id

        drawing_map: dict[int, int] = {}
        for drawing in entry.get("drawings", []):
            drawing_sha = drawing.get("png_sha")
            if drawing_sha is not None:
                blob_store.put(bundle.blobs[drawing_sha], mime="image/png", session=session)
            old_id = int(drawing.get("id") or 0)
            material_drawing_row = MaterialDrawing(
                material_id=material.id,
                strokes=drawing.get("strokes") or [],
                png_sha=drawing_sha,
                view=drawing.get("view"),
                ocr_version=int(drawing.get("ocr_version") or 0),
                ocr_blocks=drawing.get("ocr_blocks"),
                ocr_markdown=drawing.get("ocr_markdown"),
            )
            session.add(material_drawing_row)
            session.flush()
            if old_id:
                drawing_map[old_id] = material_drawing_row.id
        drawing_ocr = "\n".join(
            d["ocr_markdown"] for d in entry.get("drawings", []) if d.get("ocr_markdown")
        )

        extraction = entry.get("extraction")
        if extraction is not None:
            markdown = remap_drawing_refs(str(extraction.get("markdown") or ""), drawing_map)
            row = Extraction(
                material_id=material.id,
                version=int(extraction.get("version") or 1),
                extractor=str(extraction.get("extractor") or "import"),
                model=extraction.get("model"),
                blocks=extraction_to_blocks(markdown),
                markdown=markdown,
                language=extraction.get("language"),
                reviewed=bool(extraction.get("reviewed")),
            )
            session.add(row)
            session.flush()
            chunk_source = f"{markdown}\n\n{drawing_ocr}" if drawing_ocr else markdown
            for ordinal, chunk_text in enumerate(chunk_markdown(chunk_source)):
                session.add(
                    Chunk(
                        extraction_id=row.id,
                        ordinal=ordinal,
                        text=chunk_text,
                        token_count=max(1, len(chunk_text) // 4),
                    )
                )
            sync_material_fts(session, material, markdown, drawing_ocr)
        card = entry.get("index_card")
        if card is not None:
            session.add(
                MaterialIndexCard(
                    material_id=material.id,
                    summary=card.get("summary"),
                    topics=card.get("topics"),
                    key_terms=card.get("key_terms"),
                    reading_minutes=card.get("reading_minutes"),
                    difficulty=card.get("difficulty"),
                )
            )
        for link in entry.get("links", []):
            session.add(
                MaterialLink(
                    course_id=course.id,
                    node_id=node_map[link["node_id"]],
                    material_id=material.id,
                    rationale=link.get("rationale"),
                    auto_assigned=bool(link.get("auto_assigned")),
                    confidence=link.get("confidence"),
                )
            )
        session.flush()

    for entry in bundle.notes:
        note = Note(
            profile_id=profile_id,
            course_id=course.id,
            node_id=node_map[entry["node_id"]] if entry.get("node_id") is not None else None,
            owner_type="standalone",
            owner_id=None,
            title=str(entry.get("title") or "Note")[:300],
            body=entry.get("body") or [],
            tags=entry.get("tags"),
            pinned=bool(entry.get("pinned")),
        )
        note.search_text = str(note.title)
        session.add(note)
        session.flush()
        for drawing in entry.get("drawings", []):
            sha = drawing.get("png_sha")
            if sha is not None:
                blob_store.put(bundle.blobs[sha], mime="image/png", session=session)
            drawing_row = NoteDrawing(
                note_id=note.id,
                strokes=drawing.get("strokes") or [],
                png_sha=sha,
                view=drawing.get("view"),
                ocr_version=int(drawing.get("ocr_version") or 0),
                ocr_blocks=drawing.get("ocr_blocks"),
                ocr_markdown=drawing.get("ocr_markdown"),
            )
            session.add(drawing_row)
            if drawing.get("ocr_markdown"):
                note.search_text = f"{note.search_text}\n{drawing['ocr_markdown']}"
        session.flush()

    for entry in bundle.quizzes:
        activity = Activity(
            profile_id=profile_id,
            course_id=course.id,
            node_id=node_map[entry["node_id"]] if entry.get("node_id") is not None else None,
            type=str(entry.get("type") or "quiz"),
            title=str(entry.get("title") or "Quiz")[:300],
            config=entry.get("config"),
        )
        session.add(activity)
        session.flush()
        for question in entry.get("questions", []):
            concept_ids = question.get("concept_ids") or []
            remapped = [
                concept_map[cid] for cid in concept_ids if cid in concept_map
            ]
            session.add(
                Question(
                    activity_id=activity.id,
                    type=str(question.get("type") or "single"),
                    stem=question.get("stem") or [{"type": "text", "md": ""}],
                    options=question.get("options"),
                    answer=question.get("answer") or {},
                    explanation=question.get("explanation"),
                    difficulty=question.get("difficulty"),
                    bloom=question.get("bloom"),
                    skill=question.get("skill"),
                    concept_ids=remapped or None,
                    expected_time_sec=question.get("expected_time_sec"),
                    curriculum_code=question.get("curriculum_code"),
                    distractor_misconceptions=question.get("distractor_misconceptions"),
                    sympy_check=question.get("sympy_check"),
                    input_modes=question.get("input_modes"),
                    tags=question.get("tags"),
                    flag=str(question.get("flag") or "ok"),
                )
            )
        session.flush()

    for entry in bundle.exercises:
        exercise = Exercise(
            profile_id=profile_id,
            course_id=course.id,
            node_id=node_map[entry["node_id"]] if entry.get("node_id") is not None else None,
            title=str(entry.get("title") or "Exercise")[:300],
            kind=str(entry.get("kind") or "multi_step"),
            deck_ref=entry.get("deck_ref"),
            context=entry.get("context"),
            difficulty=entry.get("difficulty"),
            created_from=entry.get("created_from"),
        )
        session.add(exercise)
        session.flush()
        for step in entry.get("steps", []):
            session.add(
                ExerciseStep(
                    exercise_id=exercise.id,
                    order_idx=int(step.get("order_idx") or 0),
                    prompt=step.get("prompt") or [{"type": "text", "md": ""}],
                    expected=step.get("expected"),
                    hints_pregenerated=step.get("hints_pregenerated"),
                    rubric=step.get("rubric"),
                )
            )
        session.flush()

    for entry in bundle.skills:
        skill = session.scalars(select(Skill).where(Skill.name == entry["skill"])).first()
        if skill is None:
            continue
        existing_version = session.scalars(
            select(SkillVersion.version)
            .where(
                SkillVersion.skill_id == skill.id,
                SkillVersion.scope_type == "course",
                SkillVersion.scope_ref == course.id,
            )
            .order_by(SkillVersion.version.desc())
            .limit(1)
        ).first()
        next_version = (existing_version + 1) if existing_version else 2
        session.add(
            SkillVersion(
                skill_id=skill.id,
                scope_type="course",
                scope_ref=course.id,
                version=next_version,
                system_template=entry.get("system_template") or "",
                user_template=entry.get("user_template") or "",
                params=entry.get("params"),
                contract=entry.get("contract"),
                is_active=bool(entry.get("is_active")),
            )
        )

    session.commit()
    return {
        "course_id": course.id,
        "title": course.title,
        "imported_at": utcnow().isoformat(),
    }
