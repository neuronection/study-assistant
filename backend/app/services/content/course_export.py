import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import __version__
from ...domain.models import (
    Activity,
    Answer,
    Attempt,
    Concept,
    ConceptLink,
    Course,
    ErrorPattern,
    Exercise,
    ExerciseSession,
    ExerciseStep,
    ExternalSource,
    Extraction,
    FsrsState,
    Material,
    MaterialFolder,
    MaterialFolderLink,
    MaterialIndexCard,
    MaterialLink,
    NodeConcept,
    Note,
    NoteVersion,
    Question,
    QuizHelpEvent,
    ReviewLog,
    Skill,
    SkillVersion,
    StepAttempt,
    TreeNode,
)
from ...domain.payloads import (
    BundleConceptsMap,
    BundleCourseMap,
    BundleFolderLinkRow,
    BundleFoldersMap,
    BundleHistoryMap,
    BundleManifestMap,
    BundleMaterialDrawingRow,
    BundleMaterialExtraction,
    BundleMaterialIndexCard,
    BundleMaterialRow,
    BundleTreeRow,
)
from ...storage.blobs import blob_path
from ..study.exercise_kinds import is_card_kind
from .course_validate import (
    BLOBS_PREFIX,
    BUNDLE_FORMAT_V2,
    CARDS_NAME,
    CONCEPTS_NAME,
    COURSE_NAME,
    EXERCISES_NAME,
    EXTERNAL_SOURCES_NAME,
    FOLDERS_NAME,
    HISTORY_NAME,
    MANIFEST_NAME,
    MATERIALS_NAME,
    NOTE_VERSIONS_NAME,
    NOTES_NAME,
    PATTERNS_NAME,
    QUIZZES_NAME,
    SKILLS_NAME,
    TREE_NAME,
)
from .drawings import drawing_view


def _export_course(session: Session, course: Course) -> BundleCourseMap:
    return {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "subject": course.subject,
        "level": course.level,
        "goals": course.goals,
        "tags": course.tags,
        "color": course.color,
        "exam_date": course.exam_date.isoformat() if course.exam_date else None,
    }


def _export_cards(session: Session, course_id: str, include_history: bool) -> list[dict[str, Any]]:
    exercises = list(session.scalars(select(Exercise).where(Exercise.course_id == course_id)))
    card_ids = [exercise.id for exercise in exercises if is_card_kind(exercise.kind)]
    if not card_ids:
        return []
    states = {
        state.card_id: state
        for state in session.scalars(select(FsrsState).where(FsrsState.card_id.in_(card_ids)))
    }
    reviews: dict[str, list[ReviewLog]] = {}
    if include_history:
        for log in session.scalars(
            select(ReviewLog)
            .where(ReviewLog.card_id.in_(card_ids))
            .order_by(ReviewLog.reviewed_at, ReviewLog.id)
        ):
            reviews.setdefault(log.card_id, []).append(log)
    out: list[dict[str, Any]] = []
    for card_id in sorted(card_ids):
        state = states.get(card_id)
        out.append(
            {
                "exercise_id": card_id,
                "state": state.state if state else "new",
                "stability": state.stability if state else None,
                "difficulty": state.difficulty if state else None,
                "reps": state.reps if state else 0,
                "lapses": state.lapses if state else 0,
                "due_at": state.due_at.isoformat() if state else None,
                "last_review_at": (
                    state.last_review_at.isoformat() if state and state.last_review_at else None
                ),
                "reviews": [
                    {
                        "rating": log.rating,
                        "interval_days": log.interval_days,
                        "elapsed_days": log.elapsed_days,
                        "reviewed_at": log.reviewed_at.isoformat(),
                    }
                    for log in reviews.get(card_id, [])
                ],
            }
        )
    return out


def _export_patterns(session: Session, course: Course) -> list[dict[str, Any]]:
    course_type_id = course.course_type_id
    if course_type_id is None:
        rows = session.scalars(
            select(ErrorPattern).where(
                ErrorPattern.is_system.is_(False),
                ErrorPattern.course_type_id.is_(None),
            )
        )
    else:
        rows = session.scalars(
            select(ErrorPattern).where(
                ErrorPattern.is_system.is_(False),
                ErrorPattern.course_type_id.in_([course_type_id, None]),
            )
        )
    return [
        {
            "key": pattern.key,
            "name": pattern.name,
            "description": pattern.description,
            "example": pattern.example,
            "detection": pattern.detection,
            "is_active": pattern.is_active,
            "order_idx": pattern.order_idx,
        }
        for pattern in rows
    ]


def _export_note_versions(session: Session, course_id: str) -> list[dict[str, Any]]:
    note_ids = list(session.scalars(select(Note.id).where(Note.course_id == course_id)))
    if not note_ids:
        return []
    versions = list(
        session.scalars(
            select(NoteVersion)
            .where(NoteVersion.note_id.in_(note_ids))
            .order_by(NoteVersion.created_at, NoteVersion.id)
        )
    )
    return [
        {
            "note_id": version.note_id,
            "title": version.title,
            "tags": version.tags,
            "body": version.body,
            "cause": version.cause,
            "created_at": version.created_at.isoformat(),
        }
        for version in versions
    ]


def _export_history(session: Session, course_id: str) -> BundleHistoryMap:
    activities = list(session.scalars(select(Activity.id).where(Activity.course_id == course_id)))
    exercise_ids = list(session.scalars(select(Exercise.id).where(Exercise.course_id == course_id)))
    attempts = (
        list(
            session.scalars(
                select(Attempt)
                .where(Attempt.activity_id.in_(activities))
                .order_by(Attempt.started_at, Attempt.id)
            )
        )
        if activities
        else []
    )
    attempt_ids = [attempt.id for attempt in attempts]
    answers = (
        list(
            session.scalars(
                select(Answer)
                .where(Answer.attempt_id.in_(attempt_ids))
                .order_by(Answer.created_at, Answer.id)
            )
        )
        if attempt_ids
        else []
    )
    sessions = (
        list(
            session.scalars(
                select(ExerciseSession)
                .where(ExerciseSession.exercise_id.in_(exercise_ids))
                .order_by(ExerciseSession.started_at, ExerciseSession.id)
            )
        )
        if exercise_ids
        else []
    )
    session_ids = [row.id for row in sessions]
    step_attempts = (
        list(
            session.scalars(
                select(StepAttempt)
                .where(StepAttempt.session_id.in_(session_ids))
                .order_by(StepAttempt.created_at, StepAttempt.id)
            )
        )
        if session_ids
        else []
    )
    help_events = (
        list(
            session.scalars(
                select(QuizHelpEvent)
                .where(QuizHelpEvent.attempt_id.in_(attempt_ids))
                .order_by(QuizHelpEvent.created_at, QuizHelpEvent.id)
            )
        )
        if attempt_ids
        else []
    )
    return {
        "attempts": [
            {
                "id": attempt.id,
                "activity_id": attempt.activity_id,
                "mode": attempt.mode,
                "started_at": attempt.started_at.isoformat(),
                "finished_at": (attempt.finished_at.isoformat() if attempt.finished_at else None),
                "score": attempt.score,
                "meta": attempt.meta,
            }
            for attempt in attempts
        ],
        "answers": [
            {
                "attempt_id": answer.attempt_id,
                "question_id": answer.question_id,
                "response": answer.response,
                "input_mode": answer.input_mode,
                "correct": answer.correct,
                "partial_credit": answer.partial_credit,
                "feedback": answer.feedback,
                "graded_by": answer.graded_by,
                "time_ms": answer.time_ms,
                "retries": answer.retries,
                "error_tags": answer.error_tags,
                "help_events": answer.help_events,
                "created_at": answer.created_at.isoformat(),
            }
            for answer in answers
        ],
        "exercise_sessions": [
            {
                "id": row.id,
                "exercise_id": row.exercise_id,
                "current_step_idx": row.current_step_idx,
                "status": row.status,
                "socratic": row.socratic,
                "independence_score": row.independence_score,
                "started_at": row.started_at.isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
            for row in sessions
        ],
        "step_attempts": [
            {
                "session_id": row.session_id,
                "step_idx": row.step_idx,
                "response": row.response,
                "correct": row.correct,
                "hint_level_used": row.hint_level_used,
                "error_class": row.error_class,
                "feedback": row.feedback,
                "state": row.state,
                "created_at": row.created_at.isoformat(),
            }
            for row in step_attempts
        ],
        "quiz_help_events": [
            {
                "attempt_id": row.attempt_id,
                "question_id": row.question_id,
                "level": row.level,
                "markdown": row.markdown,
                "violations": row.violations,
                "created_at": row.created_at.isoformat(),
            }
            for row in help_events
        ],
    }


def _export_tree(session: Session, course_id: str) -> list[BundleTreeRow]:
    nodes = list(
        session.scalars(
            select(TreeNode).where(TreeNode.course_id == course_id).order_by(TreeNode.sort_path)
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


def _export_concepts(session: Session, course_id: str) -> BundleConceptsMap:
    concepts = list(session.scalars(select(Concept).where(Concept.course_id == course_id)))
    by_id = {concept.id: concept for concept in concepts}
    links = list(session.scalars(select(ConceptLink).where(ConceptLink.course_id == course_id)))
    coverage = list(
        session.execute(select(NodeConcept.node_id, NodeConcept.concept_id, NodeConcept.weight))
    )
    node_ids = set(session.scalars(select(TreeNode.id).where(TreeNode.course_id == course_id)))
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


def _export_materials(session: Session, course_id: str) -> tuple[list[BundleMaterialRow], set[str]]:
    materials = list(
        session.scalars(
            select(Material)
            .where(Material.course_id == course_id)
            .order_by(Material.created_at, Material.id)
        )
    )
    links = list(session.scalars(select(MaterialLink).where(MaterialLink.course_id == course_id)))
    links_by_material: dict[str, list[MaterialLink]] = {}
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
    out: list[BundleMaterialRow] = []
    for material in materials:
        extraction = session.scalars(
            select(Extraction)
            .where(Extraction.material_id == material.id)
            .order_by(Extraction.version.desc())
            .limit(1)
        ).first()
        card = session.get(MaterialIndexCard, material.id)
        if material.blob_sha is not None:
            shas.add(material.blob_sha)
        drawings: list[BundleMaterialDrawingRow] = []
        for drawing in material.drawings:
            if drawing.png_sha is not None:
                shas.add(drawing.png_sha)
            drawings.append(
                {
                    "id": drawing.id,
                    "strokes": drawing.strokes,
                    "png_sha": drawing.png_sha,
                    "view": drawing_view(drawing),
                    "ocr_markdown": drawing.ocr_markdown,
                    "ocr_blocks": drawing.ocr_blocks,
                    "ocr_version": drawing.ocr_version,
                }
            )
        extraction_payload: BundleMaterialExtraction | None = None
        if extraction is not None:
            extraction_payload = BundleMaterialExtraction(
                version=extraction.version,
                extractor=extraction.extractor,
                model=extraction.model,
                blocks=extraction.blocks,
                markdown=extraction.markdown,
                language=extraction.language,
                reviewed=extraction.reviewed,
            )
        index_card_payload: BundleMaterialIndexCard | None = None
        if card is not None:
            index_card_payload = BundleMaterialIndexCard(
                summary=card.summary,
                topics=card.topics,
                key_terms=card.key_terms,
                reading_minutes=card.reading_minutes,
                difficulty=card.difficulty,
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
                "source_url": material.source_url,
                "source_url_norm": material.source_url_norm,
                "tags": material.tags,
                "starred": material.starred,
                "drawings": drawings,
                "extraction": extraction_payload,
                "index_card": index_card_payload,
                "folder_path": (
                    folder_paths[material.folder_id]
                    if material.folder_id is not None and material.folder_id in folder_paths
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


def _export_folders(session: Session, course_id: str) -> tuple[BundleFoldersMap, list[str]]:
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
        session.scalars(select(MaterialFolderLink).where(MaterialFolderLink.course_id == course_id))
    )
    warnings: list[str] = []
    out_links: list[BundleFolderLinkRow] = []
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


def _export_notes(session: Session, course_id: str) -> tuple[list[dict[str, Any]], set[str]]:
    notes = list(
        session.scalars(
            select(Note).where(Note.course_id == course_id).order_by(Note.created_at, Note.id)
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
                    "view": drawing_view(drawing),
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


def _export_quizzes(session: Session, course_id: str) -> list[dict[str, Any]]:
    activities = list(
        session.scalars(
            select(Activity)
            .where(Activity.course_id == course_id)
            .order_by(Activity.created_at, Activity.id)
        )
    )
    out: list[dict[str, Any]] = []
    for activity in activities:
        questions = list(
            session.scalars(
                select(Question)
                .where(Question.activity_id == activity.id)
                .order_by(Question.created_at, Question.id)
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
                        "id": question.id,
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


def _export_exercises(session: Session, course_id: str) -> list[dict[str, Any]]:
    exercises = list(
        session.scalars(
            select(Exercise)
            .where(Exercise.course_id == course_id)
            .order_by(Exercise.created_at, Exercise.id)
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


def _export_skills(session: Session, course_id: str) -> list[dict[str, Any]]:
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


def _export_external_sources(session: Session, course_id: str) -> list[dict[str, Any]]:
    from ...core.vocab import ExternalSourceKind

    sources = list(
        session.scalars(select(ExternalSource).where(ExternalSource.course_id == course_id))
    )
    out: list[dict[str, Any]] = []
    for source in sources:
        if source.kind not in {item.value for item in ExternalSourceKind}:
            continue
        out.append(
            {
                "kind": source.kind,
                "url": source.url,
                "label": source.label,
                "options": source.options,
                "enabled": source.enabled,
                "scan_interval_sec": source.scan_interval_sec,
            }
        )
    return out


def build_course_bundle(
    session: Session,
    course: Course,
    blobs_root: Path,
    *,
    include_history: bool = False,
    include_note_versions: bool = False,
) -> bytes:
    tree = _export_tree(session, course.id)
    concepts = _export_concepts(session, course.id)
    materials, material_shas = _export_materials(session, course.id)
    folders, folder_warnings = _export_folders(session, course.id)
    notes, note_shas = _export_notes(session, course.id)
    quizzes = _export_quizzes(session, course.id)
    exercises = _export_exercises(session, course.id)
    skills = _export_skills(session, course.id)
    cards = _export_cards(session, course.id, include_history)
    patterns = _export_patterns(session, course)
    external_sources = _export_external_sources(session, course.id)
    note_versions = _export_note_versions(session, course.id) if include_note_versions else []
    history = _export_history(session, course.id) if include_history else {}
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

    manifest: BundleManifestMap = {
        "format": BUNDLE_FORMAT_V2,
        "app_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "course_title": course.title,
        "options": {
            "include_history": include_history,
            "include_note_versions": include_note_versions,
        },
        "counts": {
            "nodes": len(tree),
            "concepts": len(concepts["concepts"]),
            "materials": len(materials),
            "folders": len(folders["folders"]),
            "notes": len(notes),
            "note_versions": len(note_versions),
            "quizzes": len(quizzes),
            "exercises": len(exercises),
            "card_schedules": len(cards),
            "error_patterns": len(patterns),
            "attempts": len(history.get("attempts", [])),
            "skill_overrides": len(skills),
            "external_sources": len(external_sources),
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
        archive.writestr(CARDS_NAME, json.dumps(cards))
        archive.writestr(PATTERNS_NAME, json.dumps(patterns))
        archive.writestr(HISTORY_NAME, json.dumps(history))
        archive.writestr(NOTE_VERSIONS_NAME, json.dumps(note_versions))
        archive.writestr(EXTERNAL_SOURCES_NAME, json.dumps(external_sources))
        for sha in sorted(exportable):
            data = blob_path(blobs_root, sha).read_bytes()
            archive.writestr(f"{BLOBS_PREFIX}{sha}", data)
    return buffer.getvalue()
