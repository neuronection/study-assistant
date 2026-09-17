from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..domain.models import DeletedItem
from ..jobs.runner import JobRunner
from ..services.knowledge.tree import TreeError
from ..services.platform import trash
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/deleted-items", tags=["trash"])


class DeletedItemOut(BaseModel):
    id: int
    entity_type: str
    title: str
    deleted_at: str
    purge_after: str


class RestoreDeletedOut(BaseModel):
    status: str
    entity_type: str
    title: str
    node_id: int | None = None
    material_id: int | None = None
    detail: dict[str, Any] | None = None



def _load_item(session: Session, item_id: int, profile_id: int) -> DeletedItem:
    item = session.get(DeletedItem, item_id)
    if item is None or item.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="deleted item not found")
    return item


@router.get("", response_model=list[DeletedItemOut])
def list_deleted_items(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return trash.list_items(session, profile.id)


@router.post("/{item_id}/restore", response_model=RestoreDeletedOut)
def restore_deleted_item(
    item_id: int, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    item = _load_item(session, item_id, profile.id)
    title = item.title

    if item.entity_type == "node":
        from .courses import _tree

        try:
            result = _tree(session).restore_subtree_from_trash(item.payload)
        except TreeError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        session.delete(item)
        session.commit()
        return {
            "status": "restored",
            "entity_type": "node",
            "title": title,
            "node_id": result.get("node_id"),
            "detail": result,
        }

    if item.entity_type == "material":
        try:
            status, material_id = trash.restore_material(session, item)
        except trash.TrashError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if material_id is not None and status == "restored":
            JobRunner.enqueue(session, "postprocess", {"material_id": material_id})
        session.commit()
        request.app.state.jobs.wake()
        return {
            "status": status,
            "entity_type": "material",
            "title": title,
            "material_id": material_id,
        }

    try:
        entity_type = trash.restore(session, item, request.app.state.blobs)
    except trash.TrashError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return {"status": "restored", "entity_type": entity_type, "title": title}


@router.delete("/{item_id}", status_code=204)
def purge_deleted_item(
    item_id: int, session: Session = Depends(get_session)
) -> None:
    profile = ensure_default_profile(session)
    item = _load_item(session, item_id, profile.id)
    trash.purge_one(session, item)
