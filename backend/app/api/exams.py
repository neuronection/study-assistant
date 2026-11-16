from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.models import Attempt, Course, ExamPaper
from ..services.knowledge.tree import TreeError, TreeService
from ..services.platform.profiles import ensure_default_profile
from ..services.study.exam_room import (
    ExamRoomError,
    SectionSpec,
    assemble_paper,
    delete_paper,
    paper_marks,
    paper_report,
)
from .deps import get_session

router = APIRouter(tags=["exams"])


class PaperSectionIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    marks: int = Field(ge=1, le=1000)
    count: int = Field(ge=1, le=50)
    difficulty: float | None = Field(default=None, ge=1, le=5)
    types: list[str] | None = None


class GradeBandIn(BaseModel):
    label: str = Field(min_length=1, max_length=10)
    min: float = Field(ge=0, le=100)


class PaperIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    duration_min: int = Field(default=90, ge=5, le=360)
    node_id: str | None = None
    instructions_md: str | None = None
    sections: list[PaperSectionIn] = Field(min_length=1, max_length=8)
    grade_bands: list[GradeBandIn] | None = None
    seed: int | None = Field(default=None, ge=0)


class PaperSectionOut(BaseModel):
    id: str
    title: str
    marks: int
    count: int


class PaperOut(BaseModel):
    id: str
    course_id: str
    activity_id: str
    node_id: str | None
    title: str
    instructions_md: str | None
    duration_min: int
    total_marks: int
    source: str
    latest_attempt_id: str | None
    latest_percent: float | None
    attempt_count: int
    created_at: datetime
    sections: list[PaperSectionOut]


class PaperReportSectionOut(BaseModel):
    id: str | None
    title: str | None
    marks: int | None
    earned: float


class PaperTopicOut(BaseModel):
    concept_id: str
    name: str
    lost: float
    marks: int


class PaperReportOut(BaseModel):
    paper_id: str
    attempt_id: str | None
    finished_at: str | None
    earned: float
    total: int
    percent: float
    grade: str | None
    answered: int
    question_count: int
    sections: list[PaperReportSectionOut]
    topics: list[PaperTopicOut]


def _out(paper: ExamPaper, session: Session) -> PaperOut:
    completed = list(
        session.scalars(
            select(Attempt)
            .where(
                Attempt.activity_id == paper.activity_id,
                Attempt.finished_at.is_not(None),
            )
            .order_by(Attempt.finished_at.desc())
        )
    )
    latest = completed[0] if completed else None
    _earned, _total, percent = paper_marks(session, paper, latest)
    sections = [
        PaperSectionOut(
            id=str(section.get("id", "")),
            title=str(section.get("title", "")),
            marks=int(section.get("marks", 0)),
            count=len(section.get("questions", [])),
        )
        for section in (paper.document or {}).get("sections", [])
    ]
    return PaperOut(
        id=paper.id,
        course_id=paper.course_id,
        activity_id=paper.activity_id,
        node_id=paper.node_id,
        title=paper.title,
        instructions_md=paper.instructions_md,
        duration_min=paper.duration_min,
        total_marks=paper.total_marks,
        source=paper.source,
        latest_attempt_id=latest.id if latest is not None else None,
        latest_percent=percent if latest is not None else None,
        attempt_count=len(completed),
        created_at=paper.created_at,
        sections=sections,
    )


def _course(session: Session, course_id: str, profile_id: str) -> Course:
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="course not found")
    return course


@router.post("/courses/{course_id}/papers", response_model=PaperOut, status_code=201)
def create_paper(
    course_id: str,
    body: PaperIn,
    session: Session = Depends(get_session),
) -> PaperOut:
    profile = ensure_default_profile(session)
    _course(session, course_id, profile.id)
    try:
        node_id = TreeService(session).placement_node(course_id, body.node_id)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        result = assemble_paper(
            session,
            profile_id=profile.id,
            course_id=course_id,
            title=body.title,
            duration_min=body.duration_min,
            node_id=node_id,
            instructions_md=body.instructions_md,
            seed=body.seed,
            sections=[
                SectionSpec(
                    title=section.title,
                    marks=section.marks,
                    count=section.count,
                    difficulty=section.difficulty,
                    types=section.types,
                )
                for section in body.sections
            ],
            grade_bands=[
                {"label": band.label, "min": band.min}
                for band in body.grade_bands or []
            ]
            or None,
        )
    except ExamRoomError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(result.paper, session)


@router.get("/courses/{course_id}/papers", response_model=list[PaperOut])
def list_papers(
    course_id: str,
    session: Session = Depends(get_session),
) -> list[PaperOut]:
    profile = ensure_default_profile(session)
    _course(session, course_id, profile.id)
    papers = session.scalars(
        select(ExamPaper)
        .where(
            ExamPaper.profile_id == profile.id,
            ExamPaper.course_id == course_id,
        )
        .order_by(ExamPaper.created_at.desc())
    )
    return [_out(paper, session) for paper in papers]


@router.get("/papers/{paper_id}", response_model=PaperOut)
def get_paper(paper_id: str, session: Session = Depends(get_session)) -> PaperOut:
    profile = ensure_default_profile(session)
    paper = session.get(ExamPaper, paper_id)
    if paper is None or paper.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="paper not found")
    return _out(paper, session)


@router.delete("/papers/{paper_id}", status_code=204)
def remove_paper(paper_id: str, session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    paper = session.get(ExamPaper, paper_id)
    if paper is None or paper.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="paper not found")
    delete_paper(session, paper)
    session.commit()


@router.get("/papers/{paper_id}/report", response_model=PaperReportOut)
def paper_result(
    paper_id: str,
    attempt_id: str | None = None,
    session: Session = Depends(get_session),
) -> PaperReportOut:
    profile = ensure_default_profile(session)
    paper = session.get(ExamPaper, paper_id)
    if paper is None or paper.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="paper not found")
    try:
        report: dict[str, Any] = paper_report(session, paper, attempt_id)
    except ExamRoomError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return PaperReportOut(
        paper_id=report["paper_id"],
        attempt_id=report["attempt_id"],
        finished_at=report["finished_at"],
        earned=report["earned"],
        total=report["total"],
        percent=report["percent"],
        grade=report["grade"],
        answered=report["answered"],
        question_count=report["question_count"],
        sections=[PaperReportSectionOut(**entry) for entry in report["sections"]],
        topics=[PaperTopicOut(**entry) for entry in report["topics"]],
    )
