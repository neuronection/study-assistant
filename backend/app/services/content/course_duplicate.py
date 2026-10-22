from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.models import Course
from .course_export import build_course_bundle
from .course_import import import_course_bundle
from .course_validate import BundleData, read_course_bundle


def _unique_title(session: Session, profile_id: str, base: str) -> str:
    existing = set(session.scalars(select(Course.title).where(Course.profile_id == profile_id)))
    trimmed = base.strip()[:300] or "Course"
    if trimmed not in existing:
        return trimmed
    counter = 2
    while True:
        suffix = f" ({counter})"
        candidate = f"{trimmed[: 300 - len(suffix)]}{suffix}"
        if candidate not in existing:
            return candidate
        counter += 1


def duplicate_course(
    session: Session,
    course: Course,
    profile_id: str,
    blobs_root: Path,
    blob_store: Any,
    *,
    title: str | None = None,
    copy_materials: bool = True,
) -> dict[str, Any]:
    package = build_course_bundle(session, course, blobs_root)
    bundle: BundleData = read_course_bundle(package)
    materials_copied = len(bundle.materials) if copy_materials else 0
    if not copy_materials:
        bundle.materials = []
    bundle.course["title"] = _unique_title(session, profile_id, title or f"{course.title} (copy)")
    result = import_course_bundle(
        session,
        bundle,
        profile_id,
        blobs_root,
        blob_store,
        set(session.scalars(select(Course.title).where(Course.profile_id == profile_id))),
    )
    return {
        "course_id": result["course_id"],
        "title": result["title"],
        "copy_materials": copy_materials,
        "materials_copied": materials_copied,
        "nodes_copied": len(bundle.tree),
        "notes_copied": len(bundle.notes),
        "quizzes_copied": len(bundle.quizzes),
        "exercises_copied": len(bundle.exercises),
        "task_assignments_copied": len(bundle.task_assignments),
    }
