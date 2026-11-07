import json
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from ...domain.payloads import (
    BundleConceptsMap,
    BundleCourseMap,
    BundleFoldersMap,
    BundleManifestMap,
    BundleMaterialRow,
    BundleTreeRow,
)

BUNDLE_FORMAT = "sa-course/v1"
BUNDLE_FORMAT_V2 = "sa-course/v2"
SUPPORTED_FORMATS = (BUNDLE_FORMAT, BUNDLE_FORMAT_V2)
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
CARDS_NAME = "cards.json"
PATTERNS_NAME = "patterns.json"
HISTORY_NAME = "history.json"
NOTE_VERSIONS_NAME = "note-versions.json"
EXTERNAL_SOURCES_NAME = "external-sources.json"
TASK_ASSIGNMENTS_NAME = "task-assignments.json"
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

OPTIONAL_JSON_NAMES = (
    CARDS_NAME,
    PATTERNS_NAME,
    HISTORY_NAME,
    NOTE_VERSIONS_NAME,
    EXTERNAL_SOURCES_NAME,
    TASK_ASSIGNMENTS_NAME,
)


class BundleError(ValueError):
    pass


@dataclass
class BundleData:
    manifest: BundleManifestMap
    course: BundleCourseMap
    tree: list[BundleTreeRow]
    concepts: BundleConceptsMap
    materials: list[BundleMaterialRow]
    folders: BundleFoldersMap
    notes: list[dict[str, Any]]
    quizzes: list[dict[str, Any]]
    exercises: list[dict[str, Any]]
    skills: list[dict[str, Any]]
    blobs: dict[str, bytes]
    cards: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    history: dict[str, Any] = field(default_factory=dict)
    note_versions: list[dict[str, Any]] = field(default_factory=list)
    external_sources: list[dict[str, Any]] = field(default_factory=list)
    task_assignments: list[dict[str, Any]] = field(default_factory=list)


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
    if manifest.get("format") not in SUPPORTED_FORMATS:
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
            folders_payload: BundleFoldersMap = json.loads(archive.read(FOLDERS_NAME))
        except ValueError as error:
            raise BundleError(f"unreadable {FOLDERS_NAME}") from error
    else:
        folders_payload = {"folders": [], "links": []}

    optional: dict[str, Any] = {}
    for name in OPTIONAL_JSON_NAMES:
        if name in names:
            try:
                optional[name] = json.loads(archive.read(name))
            except ValueError as error:
                raise BundleError(f"unreadable {name}") from error
        else:
            optional[name] = [] if name != HISTORY_NAME else {}

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
        cards=optional[CARDS_NAME],
        patterns=optional[PATTERNS_NAME],
        history=optional[HISTORY_NAME],
        note_versions=optional[NOTE_VERSIONS_NAME],
        external_sources=optional[EXTERNAL_SOURCES_NAME],
        task_assignments=optional[TASK_ASSIGNMENTS_NAME],
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
        for material_link in material.get("links", []):
            if material_link.get("node_id") not in node_ids:
                raise BundleError("material link references an unknown node")
    folder_paths = {entry.get("path") for entry in bundle.folders.get("folders", [])}
    for folder_link in bundle.folders.get("links", []):
        if folder_link.get("node_id") not in node_ids:
            raise BundleError("folder link references an unknown node")
        if folder_link.get("folder_path") not in folder_paths:
            raise BundleError("folder link references an unknown folder")
    for note in bundle.notes:
        if note.get("node_id") is not None and note["node_id"] not in node_ids:
            raise BundleError(f"note {note['id']} references an unknown node")
        for drawing in note.get("drawings", []):
            sha = drawing.get("png_sha")
            if sha is not None and sha not in bundle.blobs:
                raise BundleError(f"note {note['id']} has a drawing with a missing blob")
    concept_ids = {entry["id"] for entry in bundle.concepts.get("concepts", [])}
    for concept_link in bundle.concepts.get("links", []):
        if (
            concept_link.get("from_concept_id") not in concept_ids
            or concept_link.get("to_concept_id") not in concept_ids
        ):
            raise BundleError("concept link references an unknown concept")
    for quiz in bundle.quizzes:
        if quiz.get("node_id") is not None and quiz["node_id"] not in node_ids:
            raise BundleError(f"quiz {quiz['id']} references an unknown node")
    for exercise in bundle.exercises:
        if exercise.get("node_id") is not None and exercise["node_id"] not in node_ids:
            raise BundleError(f"exercise {exercise['id']} references an unknown node")
    exercise_ids = {entry["id"] for entry in bundle.exercises}
    for card in bundle.cards:
        if card.get("exercise_id") not in exercise_ids:
            raise BundleError(
                f"card schedule {card.get('exercise_id')} references an unknown exercise"
            )
    for pattern in bundle.patterns:
        if not str(pattern.get("key") or "").strip():
            raise BundleError("error pattern is missing its key")
        if not str(pattern.get("name") or "").strip():
            raise BundleError(f"error pattern '{pattern.get('key')}' is missing its name")
    activity_ids = {entry["id"] for entry in bundle.quizzes}
    question_ids = {
        question["id"]
        for quiz in bundle.quizzes
        for question in quiz.get("questions", [])
        if question.get("id") is not None
    }
    attempt_ids = {entry["id"] for entry in bundle.history.get("attempts", [])}
    session_ids = {entry["id"] for entry in bundle.history.get("exercise_sessions", [])}
    for answer in bundle.history.get("answers", []):
        if answer.get("attempt_id") not in attempt_ids:
            raise BundleError("history answer references an unknown attempt")
        if answer.get("question_id") not in question_ids:
            raise BundleError("history answer references an unknown question")
    for attempt in bundle.history.get("attempts", []):
        if attempt.get("activity_id") not in activity_ids:
            raise BundleError("history attempt references an unknown quiz")
    for row in bundle.history.get("exercise_sessions", []):
        if row.get("exercise_id") not in exercise_ids:
            raise BundleError("history session references an unknown exercise")
    for row in bundle.history.get("step_attempts", []):
        if row.get("session_id") not in session_ids:
            raise BundleError("history step attempt references an unknown session")
    for row in bundle.history.get("quiz_help_events", []):
        if row.get("attempt_id") not in attempt_ids:
            raise BundleError("history help event references an unknown attempt")
        if row.get("question_id") not in question_ids:
            raise BundleError("history help event references an unknown question")
    note_ids = {entry["id"] for entry in bundle.notes}
    for version in bundle.note_versions:
        if version.get("note_id") not in note_ids:
            raise BundleError("note version references an unknown note")
