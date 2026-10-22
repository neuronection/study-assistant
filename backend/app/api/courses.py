from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.vocab import CourseOrigin, StudyStatus
from ..domain.models import (
    Course,
    Material,
    TreeNode,
    utcnow,
)
from ..services.knowledge.courses import (
    CourseError,
    StructureService,
    ensure_scratch_course,
    purge_course,
    scratch_content_count,
)
from ..services.knowledge.tree import TreeError, TreeService
from ..services.platform.profiles import ensure_default_profile
from .courses_schemas import (
    CourseDeletedOut,
    CourseImportOut,
    ImportedCourseOut,
    StudyStateOut,
)
from .deps import content_disposition, get_session

router = APIRouter(tags=["courses"])


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subject: str | None = None
    level: str | None = None
    description: str | None = None
    color: str | None = None
    course_type_id: str | None = None


class CourseUpdate(BaseModel):
    title: str | None = None
    subject: str | None = None
    level: str | None = None
    description: str | None = None
    color: str | None = None
    course_type_id: str | None = None
    archived: bool | None = None
    exam_date: date | None = None


class CourseOut(BaseModel):
    id: str
    title: str
    subject: str | None
    level: str | None
    description: str | None
    color: str | None
    course_type_id: str | None = None
    archived_at: datetime | None
    exam_date: date | None = None
    material_count: int
    origin: CourseOrigin = CourseOrigin.MANUAL
    hidden: bool = False


class ScratchpadOut(BaseModel):
    course: CourseOut
    content_count: int


class PromoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subject: str | None = None
    level: str | None = None
    color: str | None = None


class StudyStateIn(BaseModel):
    status: StudyStatus
    progress: float | None = None


class DuplicateCourseIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    copy_materials: bool = True


class DuplicateCourseOut(BaseModel):
    course: CourseOut
    copy_materials: bool
    materials_copied: int
    nodes_copied: int
    notes_copied: int
    quizzes_copied: int
    exercises_copied: int
    task_assignments_copied: int


def _course_out(session: Session, course: Course) -> CourseOut:
    count = len(
        session.scalars(
            select(Material.id).where(Material.course_id == course.id, Material.status == "ready")
        ).all()
    )
    return CourseOut(
        id=course.id,
        title=course.title,
        subject=course.subject,
        level=course.level,
        description=course.description,
        color=course.color,
        course_type_id=course.course_type_id,
        archived_at=course.archived_at,
        exam_date=course.exam_date,
        material_count=count,
        origin=CourseOrigin(course.origin),
        hidden=course.hidden,
    )


def _structure(session: Session) -> StructureService:
    return StructureService(session)


def _tree(session: Session) -> TreeService:
    return TreeService(session)


def _load_course(session: Session, course_id: str) -> Course:
    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    return course


def _load_node(session: Session, node_id: str) -> TreeNode:
    try:
        node = _tree(session).get(node_id)
    except TreeError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    _load_course(session, node.course_id)
    return node


@router.get("/courses", response_model=list[CourseOut])
def list_courses(
    include_hidden: bool = False, session: Session = Depends(get_session)
) -> list[CourseOut]:
    profile = ensure_default_profile(session)
    statement = select(Course).where(
        Course.profile_id == profile.id,
        Course.archived_at.is_(None),
    )
    if not include_hidden:
        statement = statement.where(Course.hidden.is_(False))
    courses = session.scalars(statement.order_by(Course.title))
    return [_course_out(session, course) for course in courses]


@router.get("/courses/scratchpad", response_model=ScratchpadOut)
def get_scratchpad(session: Session = Depends(get_session)) -> ScratchpadOut:
    profile = ensure_default_profile(session)
    course = ensure_scratch_course(session, profile.id)
    session.commit()
    return ScratchpadOut(
        course=_course_out(session, course),
        content_count=scratch_content_count(session, course),
    )


@router.get("/courses/{course_id}", response_model=CourseOut)
def get_course(course_id: str, session: Session = Depends(get_session)) -> CourseOut:
    return _course_out(session, _load_course(session, course_id))


@router.post("/courses/{course_id}/nodes/{node_id}/promote", response_model=CourseOut)
def promote_node(
    course_id: str,
    node_id: str,
    body: PromoteIn,
    session: Session = Depends(get_session),
) -> CourseOut:
    node = _load_node(session, node_id)
    if node.course_id != course_id:
        raise HTTPException(status_code=404, detail="node not found")
    source_course = _load_course(session, course_id)
    if source_course.origin != CourseOrigin.SCRATCH.value:
        raise HTTPException(status_code=409, detail="only scratchpad nodes can be promoted")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title cannot be empty")
    course = Course(
        profile_id=source_course.profile_id,
        title=title[:300],
        subject=body.subject,
        level=body.level,
        color=body.color,
    )
    session.add(course)
    session.flush()
    TreeService(session).ensure_root(course.id)
    try:
        TreeService(session).move_subtree_to_course(node.id, course)
    except TreeError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _course_out(session, course)


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(body: CourseCreate, session: Session = Depends(get_session)) -> CourseOut:
    profile = ensure_default_profile(session)
    course = Course(
        profile_id=profile.id,
        title=body.title.strip(),
        subject=body.subject,
        level=body.level,
        description=body.description,
        color=body.color,
        course_type_id=body.course_type_id,
    )
    session.add(course)
    session.flush()
    TreeService(session).ensure_root(course.id)
    session.commit()
    return _course_out(session, course)


@router.patch("/courses/{course_id}", response_model=CourseOut)
def update_course(
    course_id: str, body: CourseUpdate, session: Session = Depends(get_session)
) -> CourseOut:
    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="title cannot be empty")
        course.title = title
    if body.subject is not None:
        course.subject = body.subject
    if body.level is not None:
        course.level = body.level
    if body.description is not None:
        course.description = body.description
    if body.color is not None:
        course.color = body.color
    if body.course_type_id is not None:
        course.course_type_id = body.course_type_id
    if body.archived is not None:
        course.archived_at = utcnow() if body.archived else None
    if "exam_date" in body.model_fields_set:
        course.exam_date = body.exam_date
    if body.title is not None or body.description is not None:
        root = _tree(session).ensure_root(course_id)
        if body.title is not None:
            root.title = course.title
        if body.description is not None:
            root.summary = course.description or None
    session.commit()
    return _course_out(session, course)


@router.post("/courses/{course_id}/duplicate", response_model=DuplicateCourseOut, status_code=201)
def duplicate(
    course_id: str,
    request: Request,
    body: DuplicateCourseIn | None = None,
    session: Session = Depends(get_session),
) -> DuplicateCourseOut:
    from ..services.content.course_duplicate import duplicate_course
    from ..services.content.course_validate import BundleError

    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    payload = body or DuplicateCourseIn()
    try:
        result = duplicate_course(
            session,
            course,
            profile.id,
            request.app.state.settings.blobs_dir,
            request.app.state.blobs,
            title=payload.title,
            copy_materials=payload.copy_materials,
        )
    except BundleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    clone = session.get(Course, result["course_id"])
    if clone is None:
        raise HTTPException(status_code=422, detail="duplicate failed")
    return DuplicateCourseOut(
        course=_course_out(session, clone),
        copy_materials=result["copy_materials"],
        materials_copied=result["materials_copied"],
        nodes_copied=result["nodes_copied"],
        notes_copied=result["notes_copied"],
        quizzes_copied=result["quizzes_copied"],
        exercises_copied=result["exercises_copied"],
        task_assignments_copied=result["task_assignments_copied"],
    )


@router.get("/courses/{course_id}/export")
def export_course(
    course_id: str,
    request: Request,
    include_history: bool = False,
    include_note_versions: bool = False,
    session: Session = Depends(get_session),
) -> Response:
    from ..services.content.course_export import build_course_bundle
    from ..services.content.course_validate import BundleError

    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    try:
        package = build_course_bundle(
            session,
            course,
            request.app.state.settings.blobs_dir,
            include_history=include_history,
            include_note_versions=include_note_versions,
        )
    except BundleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=package,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition(
                f"course-{course.id}-{course.title[:40]}.zip"
            )
        },
    )


@router.post("/courses/import", response_model=CourseImportOut)
async def import_course(
    request: Request,
    dry_run: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from ..services.content.course_import import (
        bundle_preview,
        import_course_bundle,
    )
    from ..services.content.course_validate import (
        BundleError,
        read_course_bundle,
    )

    profile = ensure_default_profile(session)
    data = await request.body()
    if not data:
        raise HTTPException(status_code=422, detail="empty upload")
    try:
        bundle = read_course_bundle(data)
    except BundleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if dry_run:
        return {"dry_run": True, "preview": bundle_preview(bundle)}
    existing_titles = set(
        session.scalars(select(Course.title).where(Course.profile_id == profile.id))
    )
    try:
        result = import_course_bundle(
            session,
            bundle,
            profile.id,
            request.app.state.settings.blobs_dir,
            request.app.state.blobs,
            existing_titles,
        )
    except BundleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"dry_run": False, "imported": ImportedCourseOut.model_validate(result)}


@router.delete("/courses/{course_id}", response_model=CourseDeletedOut)
def delete_course(
    course_id: str,
    request: Request,
    session: Session = Depends(get_session),
    confirmed_backup: bool = False,
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    if not confirmed_backup:
        raise HTTPException(
            status_code=409,
            detail="refusing to delete a course without a confirmed backup",
        )
    from ..services.platform.backup import create_backup

    settings = request.app.state.settings
    create_backup(settings.db_path, settings.blobs_dir, settings.backups_dir, prefix="manual")
    purge_course(session, course)
    session.commit()
    return {"status": "deleted", "course_id": course_id}


@router.put("/materials/{material_id}/study-state", response_model=StudyStateOut)
def set_study_state(
    material_id: str,
    body: StudyStateIn,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    try:
        state = _structure(session).set_study_state(
            material_id, profile.id, body.status, body.progress
        )
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {
        "status": state.status,
        "progress": state.progress,
        "last_opened_at": (state.last_opened_at.isoformat() if state.last_opened_at else None),
    }


@router.get("/study-states", response_model=dict[str, StudyStateOut])
def list_study_states(
    session: Session = Depends(get_session),
) -> dict[str, dict[str, Any]]:
    profile = ensure_default_profile(session)
    states = _structure(session).study_states(profile.id)
    return {str(material_id): state for material_id, state in states.items()}
