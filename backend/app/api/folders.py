from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..domain.models import MaterialFolder
from ..services.courses import StructureService
from ..services.folders import FolderError, FoldersService
from ..services.profiles import ensure_default_profile
from .deps import get_session
from .schemas import FolderCreate, FolderMove, FolderOut, FolderRename

router = APIRouter(prefix="/folders", tags=["folders"])


def _to_out(folder: MaterialFolder) -> FolderOut:
    return FolderOut(
        id=folder.id,
        name=folder.name,
        path=folder.path,
        course_id=folder.course_id,
        parent_id=folder.parent_id,
        source_id=folder.source_id,
        created_at=folder.created_at,
    )


@router.get("", response_model=list[FolderOut])
def list_folders(
    course_id: int | None = None, session: Session = Depends(get_session)
) -> list[FolderOut]:
    profile = ensure_default_profile(session)
    return [
        _to_out(folder)
        for folder in FoldersService(session).list(
            profile_id=profile.id, course_id=course_id
        )
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


@router.get("/{folder_id}/delete-info")
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
