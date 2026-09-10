from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.models import MaterialFolder, MaterialFolderLink
from ..services.content.folders import FolderError, FoldersService
from ..services.knowledge.courses import StructureService
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session
from .schemas import FolderCreate, FolderMove, FolderOut, FolderRename

router = APIRouter(prefix="/folders", tags=["folders"])


def _to_out(folder: MaterialFolder, node_link_count: int = 0) -> FolderOut:
    return FolderOut(
        id=folder.id,
        name=folder.name,
        path=folder.path,
        course_id=folder.course_id,
        parent_id=folder.parent_id,
        source_id=folder.source_id,
        created_at=folder.created_at,
        node_link_count=node_link_count,
    )


@router.get("", response_model=list[FolderOut])
def list_folders(
    course_id: int | None = None, session: Session = Depends(get_session)
) -> list[FolderOut]:
    profile = ensure_default_profile(session)
    folders = FoldersService(session).list(
        profile_id=profile.id, course_id=course_id
    )
    link_counts: dict[int, int] = {}
    if folders:
        for folder_id, count in session.execute(
            select(MaterialFolderLink.folder_id, func.count())
            .where(MaterialFolderLink.folder_id.in_([f.id for f in folders]))
            .group_by(MaterialFolderLink.folder_id)
        ).all():
            link_counts[folder_id] = count
    return [
        _to_out(folder, node_link_count=link_counts.get(folder.id, 0))
        for folder in folders
    ]


@router.post("", response_model=FolderOut, status_code=201)
def create_folder(
    body: FolderCreate, session: Session = Depends(get_session)
) -> FolderOut:
    profile = ensure_default_profile(session)
    try:
        folder = FoldersService(session).create(
            profile_id=profile.id,
            name=body.name,
            course_id=body.course_id,
            parent_id=body.parent_id,
        )
    except FolderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _to_out(folder)


@router.patch("/{folder_id}/rename", response_model=FolderOut)
def rename_folder(
    folder_id: int, body: FolderRename, session: Session = Depends(get_session)
) -> FolderOut:
    profile = ensure_default_profile(session)
    try:
        folder = FoldersService(session).rename(folder_id, profile_id=profile.id, name=body.name)
    except FolderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _to_out(folder)


@router.patch("/{folder_id}/move", response_model=FolderOut)
def move_folder(
    folder_id: int, body: FolderMove, session: Session = Depends(get_session)
) -> FolderOut:
    profile = ensure_default_profile(session)
    try:
        folder = FoldersService(session).move(
            folder_id, profile_id=profile.id, new_parent_id=body.parent_id
        )
    except FolderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _to_out(folder)


class FolderBreadcrumbOut(BaseModel):
    id: int
    title: str


class FolderLinkInfoOut(BaseModel):
    node_id: int
    owner_title: str
    breadcrumb: list[FolderBreadcrumbOut]
    is_course_level: bool
    course_id: int
    course_title: str
    auto_assigned: bool
    rationale: str | None


class FolderNodeLinkOut(BaseModel):
    node_id: int
    owner_title: str
    breadcrumb: list[FolderBreadcrumbOut]
    is_course_level: bool
    course_title: str
    folder_count: int
    material_count: int


class FolderDeleteInfoOut(BaseModel):
    subfolders: int
    materials: int
    node_links: list[FolderNodeLinkOut]


@router.get("/{folder_id}/links", response_model=list[FolderLinkInfoOut])
def folder_links(
    folder_id: int, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    folder = FoldersService(session).get(folder_id, profile_id=profile.id)
    if folder is None:
        raise HTTPException(status_code=404, detail="folder not found")
    return StructureService(session).folder_links(folder_id)


@router.get("/{folder_id}/delete-info", response_model=FolderDeleteInfoOut)
def folder_delete_info(
    folder_id: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    folder = FoldersService(session).get(folder_id, profile_id=profile.id)
    if folder is None:
        raise HTTPException(status_code=404, detail="folder not found")
    return StructureService(session).folder_delete_info(folder_id)


@router.post("/{folder_id}/unlink", status_code=204)
def unlink_folder(
    folder_id: int, session: Session = Depends(get_session)
) -> None:
    profile = ensure_default_profile(session)
    try:
        FoldersService(session).unlink(folder_id, profile_id=profile.id)
    except FolderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()


@router.delete("/{folder_id}", status_code=204)
def delete_folder(
    folder_id: int,
    force: bool = False,
    session: Session = Depends(get_session),
) -> None:
    profile = ensure_default_profile(session)
    try:
        FoldersService(session).delete(
            folder_id, profile_id=profile.id, force=force
        )
    except FolderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
