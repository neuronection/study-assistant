from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import MaterialStatus
from ...domain.models import (
    Material,
    MaterialFolder,
    MaterialFolderLink,
    MaterialLink,
)
from ..content.folders import folder_member_ids

CAP = 40


def assigned_material_ids(
    session: Session, course_id: int
) -> set[int]:
    assigned: set[int] = set(
        session.scalars(
            select(MaterialLink.material_id).where(
                MaterialLink.course_id == course_id
            )
        )
    )
    folder_ids = list(
        session.scalars(
            select(MaterialFolderLink.folder_id).where(
                MaterialFolderLink.course_id == course_id
            )
        )
    )
    for folder_id in folder_ids:
        folder = session.get(MaterialFolder, folder_id)
        if folder is None:
            continue
        assigned |= folder_member_ids(session, folder)
    return assigned


def unassigned_materials(
    session: Session, course_id: int
) -> list[Material]:
    assigned = assigned_material_ids(session, course_id)
    materials = list(
        session.scalars(
            select(Material)
            .where(Material.course_id == course_id)
            .order_by(Material.id)
        )
    )
    ready = [material for material in materials if material.status == MaterialStatus.READY]
    unassigned = [material for material in ready if material.id not in assigned]
    return unassigned[:CAP]


def unassigned_payload(
    session: Session, course_id: int
) -> dict[str, Any]:
    materials = unassigned_materials(session, course_id)
    return {
        "count": len(materials),
        "materials": [
            {"id": material.id, "title": material.title}
            for material in materials
        ],
    }
