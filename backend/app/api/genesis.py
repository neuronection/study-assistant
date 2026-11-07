from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai.gateway import ProviderError
from ..extensions.search.provider import (
    SearchError,
    search_with_fallback,
)
from ..services.knowledge.courses import (
    CourseError,
    OutlineService,
    commit_genesis,
    genesis_task_cap,
)
from ..services.platform.profiles import ensure_default_profile
from .courses import CourseOut, _course_out
from .deps import get_session

router = APIRouter(tags=["courses"])


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
    job_id: str | None
    estimated_tasks: int
    task_cap: int


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
        transport = getattr(request.app.state, "search_transport", None)
        lines: list[str] = []
        for suffix in ("overview", "key concepts", "curriculum"):
            try:
                hits = search_with_fallback(
                    session,
                    profile.id,
                    f"{body.topic.strip()} {suffix}",
                    transport=transport,
                )
            except SearchError:
                continue
            if not hits:
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
    job_id: str | None = None
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
