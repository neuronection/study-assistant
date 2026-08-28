from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..domain.models import (
    Course,
    Material,
    MaterialFolder,
    MaterialFolderLink,
    MaterialSource,
)
from .materials import purge_material


class FolderError(ValueError):
    pass


def folder_has_links(session: Session, folder_id: int) -> bool:
    return (
        session.scalars(
            select(MaterialFolderLink.id)
            .where(MaterialFolderLink.folder_id == folder_id)
            .limit(1)
        ).first()
        is not None
    )


def subtree_folder_ids(session: Session, folder: MaterialFolder) -> list[int]:
    if folder.source_id is not None:
        return [folder.id]
    folder_ids = [folder.id]
    folder_ids.extend(
        session.scalars(
            select(MaterialFolder.id).where(
                MaterialFolder.profile_id == folder.profile_id,
                MaterialFolder.course_id == folder.course_id,
                MaterialFolder.path.like(f"{folder.path}/%"),
            )
        )
    )
    return folder_ids


def folder_member_ids(session: Session, folder: MaterialFolder) -> set[int]:
    if folder.source_id is not None:
        return set(
            session.scalars(
                select(Material.id).where(Material.source_id == folder.source_id)
            )
        )
    folder_ids = subtree_folder_ids(session, folder)
    return set(
        session.scalars(
            select(Material.id).where(Material.folder_id.in_(folder_ids))
        )
    )


def folder_links_by_node(
    session: Session, node_ids: list[int]
) -> dict[int, list[MaterialFolderLink]]:
    result: dict[int, list[MaterialFolderLink]] = {node_id: [] for node_id in node_ids}
    if not node_ids:
        return result
    for link in session.scalars(
        select(MaterialFolderLink).where(
            MaterialFolderLink.node_id.in_(node_ids)
        )
    ):
        result.setdefault(link.node_id, []).append(link)
    return result


def unlink_source_folder(session: Session, folder: MaterialFolder) -> None:
    if folder.source_id is None:
        return
    source = session.get(MaterialSource, folder.source_id)
    if source is not None:
        for material in session.scalars(
            select(Material).where(Material.source_id == source.id)
        ):
            material.source_id = None
            material.external_path = None
            material.folder_id = None
        session.delete(source)


def _valid_name(name: str) -> str:
    name = name.strip()
    if not name or "/" in name or len(name) > 200:
        raise FolderError("invalid folder name")
    return name


class FoldersService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _get(self, folder_id: int, profile_id: int) -> MaterialFolder | None:
        folder = self._session.get(MaterialFolder, folder_id)
        if folder is None or folder.profile_id != profile_id:
            return None
        return folder

    def get(self, folder_id: int, *, profile_id: int) -> MaterialFolder | None:
        return self._get(folder_id, profile_id)

    def _path_exists(self, profile_id: int, course_id: int, path: str) -> bool:
        return (
            self._session.scalars(
                select(MaterialFolder).where(
                    MaterialFolder.profile_id == profile_id,
                    MaterialFolder.course_id == course_id,
                    MaterialFolder.path == path,
                )
            ).first()
            is not None
        )

    def create(
        self,
        *,
        profile_id: int,
        name: str,
        course_id: int,
        parent_id: int | None = None,
    ) -> MaterialFolder:
        name = _valid_name(name)
        course = self._session.get(Course, course_id)
        if course is None or course.profile_id != profile_id:
            raise FolderError("course not found")
        parent_path = ""
        if parent_id is not None:
            parent = self._get(parent_id, profile_id)
            if parent is None:
                raise FolderError("parent folder not found")
            if parent.course_id != course_id:
                raise FolderError("parent folder belongs to a different course")
            parent_path = parent.path
        path = f"{parent_path}/{name}" if parent_path else name
        if self._path_exists(profile_id, course_id, path):
            raise FolderError("a folder with this name already exists here")
        folder = MaterialFolder(
            profile_id=profile_id,
            course_id=course_id,
            parent_id=parent_id,
            name=name,
            path=path,
        )
        self._session.add(folder)
        self._session.flush()
        return folder

    def list(
        self, *, profile_id: int, course_id: int | None = None
    ) -> list[MaterialFolder]:
        query = select(MaterialFolder).where(MaterialFolder.profile_id == profile_id)
        if course_id is not None:
            query = query.where(MaterialFolder.course_id == course_id)
        return list(
            self._session.scalars(query.order_by(MaterialFolder.path))
        )

    def rename(self, folder_id: int, *, profile_id: int, name: str) -> MaterialFolder:
        folder = self._get(folder_id, profile_id)
        if folder is None:
            raise FolderError("folder not found")
        name = _valid_name(name)
        parent_path = ""
        if "/" in folder.path:
            parent_path = folder.path[: len(folder.path) - len(folder.name)]
        new_path = f"{parent_path}{name}" if parent_path else name
        if new_path != folder.path and self._path_exists(profile_id, folder.course_id, new_path):
            raise FolderError("a folder with this name already exists here")
        old_path = folder.path
        folder.name = name
        folder.path = new_path
        for other in self.list(profile_id=profile_id, course_id=folder.course_id):
            if other.id != folder.id and other.path.startswith(f"{old_path}/"):
                other.path = f"{new_path}{other.path[len(old_path):]}"
        self._session.flush()
        return folder

    def move(self, folder_id: int, *, profile_id: int, new_parent_id: int | None) -> MaterialFolder:
        folder = self._get(folder_id, profile_id)
        if folder is None:
            raise FolderError("folder not found")
        if new_parent_id == folder.id:
            raise FolderError("cannot move a folder into itself")
        parent_path = ""
        if new_parent_id is not None:
            parent = self._get(new_parent_id, profile_id)
            if parent is None:
                raise FolderError("parent folder not found")
            if parent.course_id != folder.course_id:
                raise FolderError("cannot move a folder to another course")
            if parent.path.startswith(f"{folder.path}/") or parent.path == folder.path:
                raise FolderError("cannot move a folder into its own subtree")
            parent_path = parent.path
        old_path = folder.path
        new_path = f"{parent_path}/{folder.name}" if parent_path else folder.name
        if new_path == old_path:
            return folder
        if self._path_exists(profile_id, folder.course_id, new_path):
            raise FolderError("a folder with this name already exists there")
        folder.parent_id = new_parent_id
        folder.path = new_path
        for other in self.list(profile_id=profile_id, course_id=folder.course_id):
            if other.id != folder.id and other.path.startswith(f"{old_path}/"):
                other.path = f"{new_path}{other.path[len(old_path):]}"
        self._session.flush()
        return folder

    def unlink(self, folder_id: int, *, profile_id: int) -> None:
        folder = self._get(folder_id, profile_id)
        if folder is None:
            raise FolderError("folder not found")
        if folder.source_id is None:
            raise FolderError("only linked-source folders can be unlinked")
        if folder_has_links(self._session, folder.id):
            raise FolderError(
                "folder is assigned to nodes — unassign it there first"
            )
        unlink_source_folder(self._session, folder)
        self._session.delete(folder)
        self._session.flush()

    def delete(
        self, folder_id: int, *, profile_id: int, force: bool = False
    ) -> None:
        folder = self._get(folder_id, profile_id)
        if folder is None:
            raise FolderError("folder not found")
        folder_ids = subtree_folder_ids(self._session, folder)
        member_ids = folder_member_ids(self._session, folder)
        subtree_source_ids = [
            entry.source_id
            for entry in self._session.scalars(
                select(MaterialFolder).where(MaterialFolder.id.in_(folder_ids))
            )
            if entry.source_id is not None
        ]
        if subtree_source_ids:
            member_ids.update(
                self._session.scalars(
                    select(Material.id).where(
                        Material.source_id.in_(subtree_source_ids)
                    )
                )
            )
        links_exist = (
            self._session.scalars(
                select(MaterialFolderLink.id)
                .where(MaterialFolderLink.folder_id.in_(folder_ids))
                .limit(1)
            ).first()
            is not None
        )
        if links_exist and not force:
            raise FolderError(
                "folder is assigned to nodes — unassign it there first"
            )
        if links_exist:
            self._session.execute(
                delete(MaterialFolderLink).where(
                    MaterialFolderLink.folder_id.in_(folder_ids)
                )
            )
        for material in self._session.scalars(
            select(Material).where(Material.id.in_(member_ids))
        ):
            purge_material(self._session, material)
        descendants = sorted(
            self._session.scalars(
                select(MaterialFolder).where(MaterialFolder.id.in_(folder_ids[1:]))
            ),
            key=lambda entry: entry.path.count("/"),
            reverse=True,
        )
        for other in descendants:
            self._session.execute(
                delete(MaterialFolder).where(MaterialFolder.id == other.id)
            )
        self._session.execute(
            delete(MaterialFolder).where(MaterialFolder.id == folder.id)
        )
        for source_id in subtree_source_ids:
            source = self._session.get(MaterialSource, source_id)
            if source is not None:
                self._session.delete(source)
        self._session.flush()
