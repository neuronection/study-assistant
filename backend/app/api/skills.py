from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.skills import CONTEXT_VARS
from ..domain.models import CourseType
from ..services.platform.skills import SkillsError, SkillService
from .deps import get_session

router = APIRouter(prefix="/skills", tags=["skills"])


class CourseTypeOut(BaseModel):
    id: int
    key: str
    name: str
    description: str | None


class CourseTypeIn(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class SkillOut(BaseModel):
    key: str
    task: str
    name: str
    description: str | None
    is_system: bool


class VersionOut(BaseModel):
    id: int
    scope_type: str
    scope_ref: int | None
    version: int
    system_template: str
    user_template: str
    params: dict[str, Any] | None
    contract: dict[str, Any] | None
    is_active: bool
    created_at: str


class SaveIn(BaseModel):
    scope_type: str
    scope_ref: int | None = None
    system_template: str = Field(min_length=1)
    user_template: str = ""
    params: dict[str, Any] | None = None
    contract: dict[str, Any] | None = None


class DiffOut(BaseModel):
    system: str
    user: str


class TestRunIn(BaseModel):
    skill_key: str
    context: dict[str, Any] = Field(default_factory=dict)


def _version_out(version: Any) -> VersionOut:
    return VersionOut(
        id=version.id,
        scope_type=version.scope_type,
        scope_ref=version.scope_ref,
        version=version.version,
        system_template=version.system_template,
        user_template=version.user_template,
        params=version.params,
        contract=version.contract,
        is_active=version.is_active,
        created_at=version.created_at.isoformat(),
    )


@router.get("/course-types", response_model=list[CourseTypeOut])
def course_types(session: Session = Depends(get_session)) -> list[CourseTypeOut]:
    return [
        CourseTypeOut(id=entry.id, key=entry.key, name=entry.name, description=entry.description)
        for entry in session.scalars(select(CourseType).order_by(CourseType.id))
    ]


@router.post("/course-types", response_model=CourseTypeOut, status_code=201)
def add_course_type(
    body: CourseTypeIn, session: Session = Depends(get_session)
) -> CourseTypeOut:
    existing = session.scalars(select(CourseType).where(CourseType.key == body.key)).first()
    if existing is not None:
        raise HTTPException(status_code=422, detail="course type key already exists")
    entry = CourseType(key=body.key, name=body.name, description=body.description)
    session.add(entry)
    session.commit()
    return CourseTypeOut(id=entry.id, key=entry.key, name=entry.name, description=entry.description)


@router.patch("/course-types/{course_type_id}", response_model=CourseTypeOut)
def update_course_type(
    course_type_id: int, body: CourseTypeIn, session: Session = Depends(get_session)
) -> CourseTypeOut:
    entry = session.get(CourseType, course_type_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="course type not found")
    entry.key = body.key
    entry.name = body.name
    entry.description = body.description
    session.commit()
    return CourseTypeOut(id=entry.id, key=entry.key, name=entry.name, description=entry.description)


@router.get("", response_model=list[SkillOut])
def list_skills(session: Session = Depends(get_session)) -> list[SkillOut]:
    from ..domain.models import Skill

    return [
        SkillOut(
            key=skill.key,
            task=skill.task,
            name=skill.name,
            description=skill.description,
            is_system=skill.is_system,
        )
        for skill in session.scalars(select(Skill).order_by(Skill.key))
    ]


@router.get("/{skill_key}/versions", response_model=list[VersionOut])
def skill_versions(
    skill_key: str, session: Session = Depends(get_session)
) -> list[VersionOut]:
    service = SkillService(session)
    try:
        versions = service.versions(skill_key)
    except SkillsError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return [_version_out(version) for version in versions]


@router.post("/{skill_key}/versions", response_model=VersionOut, status_code=201)
def save_version(
    skill_key: str, body: SaveIn, session: Session = Depends(get_session)
) -> VersionOut:
    service = SkillService(session)
    try:
        version = service.save_version(
            skill_key,
            scope_type=body.scope_type,
            scope_ref=body.scope_ref,
            system_template=body.system_template,
            user_template=body.user_template,
            params=body.params,
            contract=body.contract,
        )
    except SkillsError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _version_out(version)


@router.post("/{skill_key}/versions/{version_id}/activate", response_model=VersionOut)
def activate_version(
    skill_key: str, version_id: int, session: Session = Depends(get_session)
) -> VersionOut:
    service = SkillService(session)
    try:
        version = service.activate(version_id)
    except SkillsError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    session.commit()
    return _version_out(version)


@router.post("/{skill_key}/restore", response_model=VersionOut)
def restore_default(
    skill_key: str, session: Session = Depends(get_session)
) -> VersionOut:
    service = SkillService(session)
    try:
        version = service.restore_system(skill_key)
    except SkillsError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    session.commit()
    return _version_out(version)


@router.get("/{skill_key}/resolution", response_model=dict[str, Any])
def resolution(
    skill_key: str, course_id: int | None = None, session: Session = Depends(get_session)
) -> dict[str, Any]:
    service = SkillService(session)
    chain = service.resolution_chain(skill_key, course_id)
    version = service.resolve(skill_key, course_id)
    return {
        "chain": chain,
        "active": _version_out(version) if version else None,
    }


@router.post("/{skill_key}/diff/{left_id}/{right_id}", response_model=DiffOut)
def diff_versions(
    skill_key: str,
    left_id: int,
    right_id: int,
    session: Session = Depends(get_session),
) -> DiffOut:
    from ..domain.models import SkillVersion

    left = session.get(SkillVersion, left_id)
    right = session.get(SkillVersion, right_id)
    if left is None or right is None:
        raise HTTPException(status_code=404, detail="version not found")
    diff = SkillService.diff(left, right)
    return DiffOut(system=diff["system"], user=diff["user"])


@router.get("/context-vars", response_model=dict[str, dict[str, str]])
def context_vars() -> dict[str, dict[str, str]]:
    return {key: {"type": value[0], "docs": value[1]} for key, value in CONTEXT_VARS.items()}


@router.post("/test-run", response_model=dict[str, Any])
def test_run(
    body: TestRunIn, session: Session = Depends(get_session)
) -> dict[str, Any]:
    service = SkillService(session)
    version = service.resolve(body.skill_key)
    if version is None:
        raise HTTPException(status_code=404, detail="skill not found")
    system, user = service.render(version, body.context)
    return {
        "system": system,
        "user": user,
        "constraints": [
            {"kind": constraint.kind, "params": constraint.params}
            for constraint in service.constraints(version, body.context)
        ],
        "skill_version_id": version.id,
    }
