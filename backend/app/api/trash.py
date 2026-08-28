from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..domain.models import DeletedItem
from ..services import trash
from ..services.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/deleted-items", tags=["trash"])


def _load_item(session: Session, item_id: int, profile_id: int) -> DeletedItem:
    item = session.get(DeletedItem, item_id)
    if item is None or item.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="deleted item not found")
    return item


@router.get("")
def list_deleted_items(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    return trash.list_items(session, profile.id)


@router.post("/{item_id}/restore")
def restore_deleted_item(
    item_id: int, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    item = _load_item(session, item_id, profile.id)
    title = item.title
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
