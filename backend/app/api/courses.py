from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import ProviderError
from ..core.secrets import get_secret
from ..core.vocab import CourseOrigin, PlanItemKind, PlanItemOrigin, StudyStatus
from ..domain.models import (
    Concept,
    Course,
    Material,
    MaterialIndexCard,
    MaterialLink,
    NodeConcept,
    Note,
    PlanItem,
    TreeNode,
    utcnow,
)
from ..search.provider import (
    SEARCH_KEYRING_REF,
    SearchError,
    perform_search,
    search_provider_config,
)
from ..services.knowledge.concepts import (
    ConceptsError,
    commit_concepts,
    concept_graph,
    extract_concepts,
)
from ..services.knowledge.courses import (
    CourseError,
    OutlineService,
    StructureService,
    commit_genesis,
    ensure_scratch_course,
    genesis_task_cap,
    purge_course,
    scratch_content_count,
)
from ..services.knowledge.tree import TreeError, TreeService
from ..services.platform.profiles import ensure_default_profile
from ..services.study.organizer import (
    OrganizerError,
    missing_note_markdown,
    node_context,
    review_node,
    review_report_markdown,
)
from ..services.study.planner import PlannerError, generate_plan
from .courses_schemas import (
    ConceptDraftOut,
    ConceptGraphOut,
    ConceptsCommitOut,
    CourseDeletedOut,
    CourseImportOut,
    CourseMaterialsEntryOut,
    DraftNoteOut,
    FolderAssignedOut,
    ImportedCourseOut,
    MaterialAssignedOut,
    NodeArtifactsOut,
    NodeConceptLinkedOut,
    NodeCreatedOut,
    NodeDeletedOut,
    NodeDetailOut,
    NodeMovedOut,
    NodeRestoredOut,
    NodeReviewOut,
    NodeUpdatedOut,
    NodeWorkspaceOut,
    OutlineCommitOut,
    OutlineDraftOut,
    StudyStateOut,
    TreeNodeOut,
)
from .deps import content_disposition, get_session
from .plan import (
    PlanGenerateOut,
    PlanItemCreateIn,
    PlanItemOut,
    PlanItemUpdateIn,
)

router = APIRouter(tags=["courses"])


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subject: str | None = None
    level: str | None = None
    description: str | None = None
    color: str | None = None
    course_type_id: int | None = None


class CourseUpdate(BaseModel):
    title: str | None = None
    subject: str | None = None
    level: str | None = None
    description: str | None = None
    color: str | None = None
    course_type_id: int | None = None
    archived: bool | None = None
    exam_date: date | None = None


class CourseOut(BaseModel):
    id: int
    title: str
    subject: str | None
    level: str | None
    description: str | None
    color: str | None
    course_type_id: int | None = None
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


class GenesisDraftIn(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    level: str | None = None
    ground: bool = False


class GenesisSectionOut(BaseModel):
    title: str
    objectives: list[str]


class GenesisChapterOut(BaseModel):
    title: str
    summary: str | None
    sections: list[GenesisSectionOut]


class GenesisDraftOut(BaseModel):
    title: str
    description: str | None
    subject: str | None
    level: str | None
    goals: list[str]
    chapters: list[GenesisChapterOut]
    sources: list[str] = []


class GenesisCommitIn(BaseModel):
    draft: dict[str, Any]
    lessons: bool = True
    quizzes: bool = False
    flashcards: bool = False
    sources: list[str] = Field(default_factory=list, max_length=8)


class GenesisCommitOut(BaseModel):
    course: CourseOut
    job_id: int | None
    estimated_tasks: int
    task_cap: int


class NodeCreate(BaseModel):
    course_id: int
    parent_id: int
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = None
    objectives: list[str] | None = None


class NodeUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    objectives: list[str] | None = None
    ai_hint: str | None = Field(default=None, max_length=4000)


class NodeMove(BaseModel):
    parent_id: int
    position: int


class NodeRestore(BaseModel):
    undo_token: str


class AllocationIn(BaseModel):
    material_id: int
    rationale: str | None = None


class FolderAllocationIn(BaseModel):
    folder_id: int
    rationale: str | None = None


class MirrorFolderIn(BaseModel):
    folder_id: int
    recursive: bool = True
    rationale: str | None = None


class MirrorFolderOut(BaseModel):
    created_nodes: int
    reused_nodes: int
    folder_links: int
    skipped_folders: list[str] = Field(default_factory=list)


class OutlineCommit(BaseModel):
    chapters: list[dict[str, Any]]


class StudyStateIn(BaseModel):
    status: StudyStatus
    progress: float | None = None


class NodeConceptIn(BaseModel):
    concept_id: int


class ConceptsCommit(BaseModel):
    concepts: list[dict[str, Any]]
    links: list[dict[str, Any]]
    nodes: list[dict[str, Any]]


def _course_out(session: Session, course: Course) -> CourseOut:
    count = len(
        session.scalars(
            select(Material.id).where(
                Material.course_id == course.id, Material.status == "ready"
            )
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


def _load_course(session: Session, course_id: int) -> Course:
    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    return course


def _load_node(session: Session, node_id: int) -> TreeNode:
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


def _item_out(item: PlanItem) -> PlanItemOut:
    return PlanItemOut(
        id=item.id,
        course_id=item.course_id,
        node_id=item.node_id,
        title=item.title,
        detail=item.detail,
        kind=PlanItemKind(item.kind),
        due_date=item.due_date,
        done_at=item.done_at.isoformat() if item.done_at else None,
        origin=PlanItemOrigin(item.origin),
        sort_key=item.sort_key,
    )

@router.get("/courses/{course_id}/plan", response_model=list[PlanItemOut])
def list_course_plan(
    course_id: int, session: Session = Depends(get_session)
) -> list[PlanItemOut]:
    profile = ensure_default_profile(session)
    items = session.scalars(
        select(PlanItem)
        .where(PlanItem.course_id == course_id, PlanItem.profile_id == profile.id)
        .order_by(PlanItem.due_date, PlanItem.sort_key, PlanItem.id)
    )
    return [_item_out(item) for item in items]


@router.post("/courses/{course_id}/plan", response_model=PlanItemOut, status_code=201)
def create_plan_item(
    course_id: int, body: PlanItemCreateIn, session: Session = Depends(get_session)
) -> PlanItemOut:
    profile = ensure_default_profile(session)
    if body.node_id is not None:
        try:
            placement = TreeService(session).placement_node(course_id, body.node_id)
        except Exception as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if placement is None:
            raise HTTPException(status_code=422, detail="node not in this course")
    item = PlanItem(
        profile_id=profile.id,
        course_id=course_id,
        node_id=body.node_id,
        title=body.title.strip()[:300] or "Plan item",
        detail=body.detail,
        kind=body.kind.value,
        due_date=body.due_date,
        origin=PlanItemOrigin.MANUAL.value,
        sort_key=0,
    )
    session.add(item)
    session.commit()
    return _item_out(item)


@router.patch("/courses/{course_id}/plan/{item_id}", response_model=PlanItemOut)
def update_plan_item(
    course_id: int,
    item_id: int,
    body: PlanItemUpdateIn,
    session: Session = Depends(get_session),
) -> PlanItemOut:
    profile = ensure_default_profile(session)
    item = session.get(PlanItem, item_id)
    if (
        item is None
        or item.course_id != course_id
        or item.profile_id != profile.id
    ):
        raise HTTPException(status_code=404, detail="plan item not found")
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="title cannot be empty")
        item.title = title[:300]
    if body.kind is not None:
        item.kind = body.kind.value
    if body.due_date is not None:
        item.due_date = body.due_date
    if body.done is not None:
        item.done_at = utcnow() if body.done else None
    session.commit()
    return _item_out(item)


@router.delete("/courses/{course_id}/plan/{item_id}", status_code=204)
def delete_plan_item(
    course_id: int, item_id: int, session: Session = Depends(get_session)
) -> None:
    profile = ensure_default_profile(session)
    item = session.get(PlanItem, item_id)
    if (
        item is None
        or item.course_id != course_id
        or item.profile_id != profile.id
    ):
        raise HTTPException(status_code=404, detail="plan item not found")
    session.delete(item)
    session.commit()


@router.post(
    "/courses/{course_id}/plan/generate", response_model=PlanGenerateOut
)
def generate_course_plan(
    course_id: int, session: Session = Depends(get_session)
) -> PlanGenerateOut:
    from ..domain.models import Course

    profile = ensure_default_profile(session)
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="course not found")
    try:
        items = generate_plan(session, course, profile.id)
    except PlannerError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return PlanGenerateOut(created=len(items), items=[_item_out(item) for item in items])


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
def get_course(course_id: int, session: Session = Depends(get_session)) -> CourseOut:
    return _course_out(session, _load_course(session, course_id))


@router.post("/courses/genesis/draft", response_model=GenesisDraftOut)
def genesis_draft(
    body: GenesisDraftIn,
    request: Request,
    session: Session = Depends(get_session),
) -> GenesisDraftOut:
    profile = ensure_default_profile(session)
    sources_block: str | None = None
    found_sources: list[str] = []
    if body.ground:
        config = search_provider_config(session, profile.id)
        if config is not None:
            transport = getattr(request.app.state, "search_transport", None)
            lines: list[str] = []
            for suffix in ("overview", "key concepts", "curriculum"):
                try:
                    hits = perform_search(
                        config["base_url"],
                        config["flavor"],
                        f"{body.topic.strip()} {suffix}",
                        api_key=get_secret(SEARCH_KEYRING_REF) or "",
                        transport=transport,
                    )
                except SearchError:
                    continue
                for hit in hits[:2]:
                    if hit["url"] in found_sources:
                        continue
                    found_sources.append(hit["url"])
                    lines.append(f"- {hit['title']} — {hit['url']}\n  {hit['content']}")
            sources_block = "\n".join(lines) if lines else None
    try:
        draft = OutlineService(request.app.state.gateway).draft_genesis(
            profile_id=profile.id,
            topic=body.topic,
            level=body.level,
            sources_block=sources_block,
        )
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    session.commit()
    out = GenesisDraftOut.model_validate(draft)
    out.sources = found_sources
    return out


@router.post("/courses/genesis", response_model=GenesisCommitOut, status_code=201)
def genesis_commit(
    body: GenesisCommitIn,
    request: Request,
    session: Session = Depends(get_session),
) -> GenesisCommitOut:
    profile = ensure_default_profile(session)
    try:
        course, estimate = commit_genesis(
            session,
            profile_id=profile.id,
            draft=body.draft,
            lessons=body.lessons,
            quizzes=body.quizzes,
            flashcards=body.flashcards,
            sources=body.sources,
        )
    except CourseError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    job_id: int | None = None
    if estimate > 0:
        job = request.app.state.jobs.enqueue(
            session,
            "genesis",
            {
                "course_id": course.id,
                "lessons": body.lessons,
                "quizzes": body.quizzes,
                "flashcards": body.flashcards,
            },
        )
        job_id = job.id
    session.commit()
    return GenesisCommitOut(
        course=_course_out(session, course),
        job_id=job_id,
        estimated_tasks=estimate,
        task_cap=genesis_task_cap(session, profile.id),
    )


@router.post("/courses/{course_id}/nodes/{node_id}/promote", response_model=CourseOut)
def promote_node(
    course_id: int,
    node_id: int,
    body: PromoteIn,
    session: Session = Depends(get_session),
) -> CourseOut:
    node = _load_node(session, node_id)
    if node.course_id != course_id:
        raise HTTPException(status_code=404, detail="node not found")
    source_course = _load_course(session, course_id)
    if source_course.origin != CourseOrigin.SCRATCH.value:
        raise HTTPException(
            status_code=409, detail="only scratchpad nodes can be promoted"
        )
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
    course_id: int, body: CourseUpdate, session: Session = Depends(get_session)
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


@router.get("/courses/{course_id}/export")
def export_course(
    course_id: int,
    request: Request,
    include_history: bool = False,
    include_note_versions: bool = False,
    session: Session = Depends(get_session),
) -> Response:
    from ..services.content.course_bundle import BundleError, build_course_bundle

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
    from ..services.content.course_bundle import (
        BundleError,
        bundle_preview,
        import_course_bundle,
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
    course_id: int,
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
    create_backup(
        settings.db_path, settings.blobs_dir, settings.backups_dir, prefix="manual"
    )
    purge_course(session, course)
    session.commit()
    return {"status": "deleted", "course_id": course_id}


@router.get("/courses/{course_id}/tree", response_model=list[TreeNodeOut])
def course_tree(course_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    _load_course(session, course_id)
    profile = ensure_default_profile(session)
    return _tree(session).tree(course_id, profile.id)


@router.post("/courses/{course_id}/nodes", status_code=201, response_model=NodeCreatedOut)
def add_node(
    course_id: int, body: NodeCreate, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    try:
        node = _tree(session).create_node(
            course_id,
            body.parent_id,
            body.title,
            summary=body.summary,
            objectives=body.objectives,
        )
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"id": node.id, "title": node.title, "order_idx": node.order_idx, "depth": node.depth}


@router.get("/nodes/{node_id}", response_model=NodeDetailOut)
def get_node(node_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    node = _load_node(session, node_id)
    return {
        "id": node.id,
        "course_id": node.course_id,
        "parent_id": node.parent_id,
        "title": node.title,
        "summary": node.summary,
        "objectives": node.objectives or [],
        "ai_hint": node.ai_hint,
        "depth": node.depth,
        "is_root": node.is_root,
        "order_idx": node.order_idx,
    }


@router.patch("/nodes/{node_id}", response_model=NodeUpdatedOut)
def patch_node(
    node_id: int, body: NodeUpdate, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    try:
        node = _tree(session).update_node(
            node_id,
            title=body.title,
            summary=body.summary,
            objectives=body.objectives,
            ai_hint=body.ai_hint,
        )
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"id": node.id, "title": node.title, "ai_hint": node.ai_hint}


@router.patch("/nodes/{node_id}/move", response_model=NodeMovedOut)
def move_node(
    node_id: int, body: NodeMove, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    try:
        node = _tree(session).move_node(node_id, body.parent_id, body.position)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"id": node.id, "parent_id": node.parent_id, "order_idx": node.order_idx}


@router.delete("/nodes/{node_id}", response_model=NodeDeletedOut)
def delete_node(node_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    _load_node(session, node_id)
    try:
        token = _tree(session).delete_node(node_id, snapshot=True)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"undo_token": token}


@router.post("/nodes/restore", status_code=200, response_model=NodeRestoredOut)
def restore_node(body: NodeRestore, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        node_id = _tree(session).restore_node(body.undo_token)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"id": node_id}


@router.post("/nodes/{node_id}/concepts", status_code=201, response_model=NodeConceptLinkedOut)
def add_node_concept(
    node_id: int, body: NodeConceptIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    node = _load_node(session, node_id)
    concept = session.get(Concept, body.concept_id)
    if concept is None or concept.course_id != node.course_id:
        raise HTTPException(status_code=422, detail="concept not in this course")
    existing = session.scalars(
        select(NodeConcept).where(
            NodeConcept.node_id == node_id,
            NodeConcept.concept_id == concept.id,
        )
    ).first()
    if existing is None:
        session.add(NodeConcept(node_id=node_id, concept_id=concept.id))
        session.commit()
    return {"node_id": node_id, "concept_id": concept.id}


@router.delete("/nodes/{node_id}/concepts/{concept_id}", status_code=204)
def remove_node_concept(
    node_id: int, concept_id: int, session: Session = Depends(get_session)
) -> None:
    _load_node(session, node_id)
    existing = session.scalars(
        select(NodeConcept).where(
            NodeConcept.node_id == node_id,
            NodeConcept.concept_id == concept_id,
        )
    ).first()
    if existing is not None:
        session.delete(existing)
        session.commit()


@router.get("/nodes/{node_id}/workspace", response_model=NodeWorkspaceOut)
def node_workspace(
    node_id: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    _load_node(session, node_id)
    return _tree(session).workspace(node_id, profile.id)


def _assign(session: Session, node_id: int, body: AllocationIn) -> dict[str, Any]:
    try:
        link = _structure(session).assign(
            node_id,
            body.material_id,
            rationale=body.rationale,
            auto_assigned=False,
        )
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "node_id": link.node_id,
        "material_id": link.material_id,
    }


@router.post("/nodes/{node_id}/materials", status_code=201, response_model=MaterialAssignedOut)
def assign_material(
    node_id: int, body: AllocationIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    result = _assign(session, node_id, body)
    session.commit()
    return result


@router.delete("/nodes/{node_id}/materials/{material_id}", status_code=204)
def unassign_material(
    node_id: int, material_id: int, session: Session = Depends(get_session)
) -> None:
    _load_node(session, node_id)
    try:
        _structure(session).unassign(node_id, material_id)
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()


@router.post("/nodes/{node_id}/folder-materials", status_code=201, response_model=FolderAssignedOut)
def assign_folder_materials(
    node_id: int, body: FolderAllocationIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    try:
        link = _structure(session).assign_folder(
            node_id, body.folder_id, rationale=body.rationale
        )
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"node_id": link.node_id, "folder_id": link.folder_id}


@router.delete("/nodes/{node_id}/folder-materials/{folder_id}", status_code=204)
def unassign_folder_materials(
    node_id: int, folder_id: int, session: Session = Depends(get_session)
) -> None:
    _load_node(session, node_id)
    _structure(session).unassign_folder(node_id, folder_id)
    session.commit()


@router.post(
    "/nodes/{node_id}/mirror-folder",
    status_code=201,
    response_model=MirrorFolderOut,
)
def mirror_folder(
    node_id: int, body: MirrorFolderIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_node(session, node_id)
    try:
        result = _structure(session).mirror_folder(
            node_id, body.folder_id, recursive=body.recursive, rationale=body.rationale
        )
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return result


@router.get(
    "/courses/{course_id}/materials", response_model=list[CourseMaterialsEntryOut]
)
def course_materials(
    course_id: int, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    _load_course(session, course_id)
    return _structure(session).course_materials(course_id)


@router.post(
    "/courses/{course_id}/materials",
    status_code=201,
    response_model=MaterialAssignedOut,
)
def assign_course_material(
    course_id: int, body: AllocationIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    root = _tree(session).ensure_root(course_id)
    result = _assign(session, root.id, body)
    session.commit()
    return result


@router.delete("/courses/{course_id}/materials/{material_id}", status_code=204)
def unassign_course_material(
    course_id: int, material_id: int, session: Session = Depends(get_session)
) -> None:
    _load_course(session, course_id)
    root = _tree(session).ensure_root(course_id)
    try:
        _structure(session).unassign(root.id, material_id)
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()


@router.post(
    "/courses/{course_id}/folder-materials",
    status_code=201,
    response_model=FolderAssignedOut,
)
def assign_course_folder_materials(
    course_id: int, body: FolderAllocationIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    root = _tree(session).ensure_root(course_id)
    try:
        link = _structure(session).assign_folder(
            root.id, body.folder_id, rationale=body.rationale
        )
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"node_id": link.node_id, "folder_id": link.folder_id}


@router.delete("/courses/{course_id}/folder-materials/{folder_id}", status_code=204)
def unassign_course_folder_materials(
    course_id: int, folder_id: int, session: Session = Depends(get_session)
) -> None:
    _load_course(session, course_id)
    root = _tree(session).ensure_root(course_id)
    _structure(session).unassign_folder(root.id, folder_id)
    session.commit()


@router.post(
    "/courses/{course_id}/outline/draft", response_model=OutlineDraftOut
)
def outline_draft(
    course_id: int, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    course = _load_course(session, course_id)
    materials = list(
        session.scalars(
            select(Material).where(
                Material.course_id == course_id, Material.status == "ready"
            )
        )
    )
    cards = {
        card.material_id: card
        for card in session.scalars(
            select(MaterialIndexCard).where(
                MaterialIndexCard.material_id.in_([material.id for material in materials])
            )
        )
    }
    try:
        return OutlineService(request.app.state.gateway).draft(course, materials, cards)
    except CourseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post(
    "/courses/{course_id}/outline/commit", response_model=OutlineCommitOut
)
def outline_commit(
    course_id: int, body: OutlineCommit, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    try:
        result = _structure(session).commit_outline(course_id, {"chapters": body.chapters})
    except (CourseError, TreeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return result


@router.post(
    "/courses/{course_id}/concepts/extract", response_model=ConceptDraftOut
)
def extract_course_concepts(
    course_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    course = _load_course(session, course_id)
    materials = list(
        session.scalars(
            select(Material).where(
                Material.course_id == course_id, Material.status == "ready"
            )
        )
    )
    if not materials:
        raise HTTPException(status_code=422, detail="course has no ready materials")
    cards = {
        card.material_id: card
        for card in session.scalars(
            select(MaterialIndexCard).where(
                MaterialIndexCard.material_id.in_([m.id for m in materials])
            )
        )
    }
    tree = _tree(session).tree(course_id)
    node_by_material: dict[int, str] = {}

    def walk(entry: dict[str, Any]) -> None:
        for allocation in entry["materials"]:
            if allocation["material_id"] not in node_by_material:
                node_by_material[allocation["material_id"]] = entry["title"]
        for child in entry["children"]:
            walk(child)

    for root in tree:
        walk(root)
    known_nodes: set[str] = set()

    def collect(entry: dict[str, Any]) -> None:
        known_nodes.add(entry["title"])
        for child in entry["children"]:
            collect(child)

    for root in tree:
        collect(root)
    payload = [
        {
            "title": material.title,
            "topics": (cards[material.id].topics if material.id in cards else None),
            "summary": (cards[material.id].summary if material.id in cards else None),
            "node_title": node_by_material.get(material.id),
        }
        for material in materials
    ]
    try:
        draft = extract_concepts(request.app.state.gateway, course, payload)
    except ConceptsError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    draft["nodes"] = [
        entry
        for entry in draft["nodes"]
        if not known_nodes or entry["node_title"] in known_nodes
    ]
    return draft


@router.post(
    "/courses/{course_id}/concepts/commit", response_model=ConceptsCommitOut
)
def commit_course_concepts(
    course_id: int,
    body: ConceptsCommit,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    _load_course(session, course_id)
    result = commit_concepts(
        session,
        course_id,
        {
            "concepts": body.concepts,
            "links": body.links,
            "nodes": body.nodes,
        },
    )
    session.commit()
    return result


@router.get("/courses/{course_id}/concepts", response_model=ConceptGraphOut)
def course_concept_graph(
    course_id: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _load_course(session, course_id)
    return concept_graph(session, course_id)


@router.post("/nodes/{node_id}/review", response_model=NodeReviewOut)
def review_node_endpoint(
    node_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    node = _load_node(session, node_id)
    try:
        node, children, unassigned, concepts = node_context(session, node_id)
    except OrganizerError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    try:
        findings = review_node(
            request.app.state.gateway, node, children, unassigned, concepts
        )
    except OrganizerError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    from datetime import UTC
    from datetime import datetime as dt

    from ..pipelines.compose import ComposeService, find_live_artifact
    from ..services.content.materials import MaterialsService

    report = review_report_markdown(node.title, findings)
    dated = dt.now(UTC).date().isoformat()
    title = f"{node.title} — Review {dated}"
    existing_same_day = find_live_artifact(
        session, node.course_id, node.id, "node_review"
    )
    if existing_same_day is not None and existing_same_day.title == title:
        MaterialsService(session, request.app.state.blobs).edit_extraction(
            existing_same_day, report
        )
        material = existing_same_day
    else:
        material = ComposeService(
            session, request.app.state.gateway
        ).compose_organizer_artifact(
            profile_id=profile.id,
            course_id=node.course_id,
            node_id=node.id,
            kind="node_review",
            title=title,
            markdown=report,
            model_label=None,
            blobs=request.app.state.blobs,
        )
        MaterialsService(session, request.app.state.blobs).queue_ingest(
            material, request.app.state.jobs
        )
    session.commit()
    return {
        "node_id": node_id,
        "node_title": node.title,
        "findings": findings,
        "material_id": material.id,
    }


@router.post("/nodes/{node_id}/draft-note", response_model=DraftNoteOut)
def draft_node_note(
    node_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    node = _load_node(session, node_id)
    existing = session.scalars(
        select(Note)
        .where(
            Note.node_id == node_id,
            Note.course_id == node.course_id,
            Note.tags.like('%"ai-draft"%'),
        )
        .order_by(Note.id.desc())
        .limit(1)
    ).first()
    if existing is not None:
        markdown = "\n\n".join(
            str(block.get("md") or "")
            for block in existing.body or []
            if block.get("md")
        )
        return {
            "note_id": existing.id,
            "markdown": markdown,
            "existing": True,
        }
    materials = [
        {"title": material.title, "summary": None}
        for material in session.scalars(
            select(Material)
            .join(MaterialLink, MaterialLink.material_id == Material.id)
            .where(
                MaterialLink.course_id == node.course_id,
                MaterialLink.node_id.in_(
                    _tree(session).subtree_ids(node)
                ),
            )
        )
    ]
    if not materials:
        raise HTTPException(status_code=422, detail="node has no material assigned")
    try:
        markdown = missing_note_markdown(request.app.state.gateway, node, materials)
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    note = Note(
        profile_id=profile.id,
        course_id=node.course_id,
        node_id=node.id,
        title=f"{node.title} — AI draft",
        body=[{"type": "text", "md": markdown}],
    )
    note.search_text = f"{note.title}\n{markdown}"
    note.tags = ["ai-draft"]
    session.add(note)
    session.commit()
    return {"note_id": note.id, "markdown": markdown, "existing": False}

@router.get("/nodes/{node_id}/artifacts", response_model=NodeArtifactsOut)
def node_artifacts(
    node_id: int,
    kind: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    node = _load_node(session, node_id)
    rows = session.execute(
        select(Material)
        .join(MaterialLink, MaterialLink.material_id == Material.id)
        .where(
            MaterialLink.course_id == node.course_id,
            MaterialLink.node_id == node_id,
            Material.provenance.is_not(None),
        )
        .order_by(Material.id.desc())
    ).scalars()
    cheat_sheet: dict[str, Any] | None = None
    reviews: list[dict[str, Any]] = []
    artifact: dict[str, Any] | None = None
    for material in rows:
        provenance = material.provenance
        if not isinstance(provenance, dict):
            continue
        entry_kind = provenance.get("kind")
        if entry_kind == "cheat_sheet" and cheat_sheet is None:
            cheat_sheet = {"material_id": material.id, "title": material.title}
        elif entry_kind == "node_review":
            reviews.append(
                {"material_id": material.id, "title": material.title}
            )
        if kind is not None and entry_kind == kind and artifact is None:
            artifact = {"material_id": material.id, "title": material.title}
    result: dict[str, Any] = {"cheat_sheet": cheat_sheet, "reviews": reviews[:5]}
    if kind is not None:
        result["artifact"] = artifact
    return result

@router.put(
    "/materials/{material_id}/study-state", response_model=StudyStateOut
)
def set_study_state(
    material_id: int,
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
        "last_opened_at": (
            state.last_opened_at.isoformat() if state.last_opened_at else None
        ),
    }


@router.get("/study-states", response_model=dict[str, StudyStateOut])
def list_study_states(
    session: Session = Depends(get_session),
) -> dict[str, dict[str, Any]]:
    profile = ensure_default_profile(session)
    states = _structure(session).study_states(profile.id)
    return {str(material_id): state for material_id, state in states.items()}
