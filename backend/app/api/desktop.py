import os
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/desktop", tags=["desktop"])


class DesktopFileEntry(BaseModel):
    path: str
    rel: str
    size: int
    mtime: int


class DesktopFileAccess:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._roots: set[Path] = set()
        self._files: set[Path] = set()

    def register_root(self, raw: str) -> Path:
        root = Path(raw).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"not a directory: {raw}")
        with self._lock:
            self._roots.add(root)
        return root

    def register_paths(self, raw_paths: list[str]) -> list[DesktopFileEntry]:
        entries: list[DesktopFileEntry] = []
        for raw in raw_paths:
            path = Path(raw).expanduser().resolve()
            if path.is_dir():
                self.register_root(str(path))
                entries.extend(_walk_folder(self, path, path))
            elif path.is_file():
                try:
                    stat = path.stat()
                except OSError:
                    continue
                with self._lock:
                    self._files.add(path)
                entries.append(
                    DesktopFileEntry(
                        path=str(path),
                        rel=path.name,
                        size=stat.st_size,
                        mtime=int(stat.st_mtime),
                    )
                )
        return entries

    def root_for(self, path: Path) -> Path | None:
        with self._lock:
            roots = tuple(self._roots)
        for root in sorted(roots, key=lambda item: len(item.parts), reverse=True):
            if path == root or root in path.parents:
                return root
        return None

    def allows(self, path: Path) -> bool:
        if self.root_for(path) is not None:
            return True
        with self._lock:
            return path in self._files


class DesktopFolderOut(BaseModel):
    path: str
    files: list[DesktopFileEntry]


class DesktopDropsIn(BaseModel):
    paths: list[str]


class DesktopDropsOut(BaseModel):
    files: list[DesktopFileEntry]


def _walk_folder(
    access: DesktopFileAccess, walk_root: Path, rel_root: Path
) -> list[DesktopFileEntry]:
    files: list[DesktopFileEntry] = []
    for dirpath, dirnames, filenames in os.walk(walk_root, followlinks=False):
        dirnames.sort()
        for filename in sorted(filenames):
            resolved = (Path(dirpath) / filename).resolve()
            if not access.allows(resolved):
                continue
            try:
                stat = resolved.stat()
            except OSError:
                continue
            files.append(
                DesktopFileEntry(
                    path=str(resolved),
                    rel=f"{rel_root.name}/{resolved.relative_to(rel_root).as_posix()}",
                    size=stat.st_size,
                    mtime=int(stat.st_mtime),
                )
            )
    return files


def _access(request: Request) -> DesktopFileAccess:
    candidate = getattr(request.app.state, "desktop_files", None)
    if not isinstance(candidate, DesktopFileAccess):
        raise HTTPException(status_code=404, detail="desktop file access unavailable")
    return candidate


@router.get("/folder", response_model=DesktopFolderOut)
def list_desktop_folder(path: str, request: Request) -> DesktopFolderOut:
    access = _access(request)
    root = Path(path).expanduser().resolve()
    containing = access.root_for(root)
    if containing is None:
        raise HTTPException(status_code=404, detail="path not allowed")
    if not root.is_dir():
        raise HTTPException(status_code=422, detail="not a directory")
    return DesktopFolderOut(path=str(root), files=_walk_folder(access, root, containing))


@router.post("/drops", response_model=DesktopDropsOut)
def register_desktop_drops(body: DesktopDropsIn, request: Request) -> DesktopDropsOut:
    access = _access(request)
    return DesktopDropsOut(files=access.register_paths(body.paths))


@router.get("/file")
def read_desktop_file(path: str, request: Request) -> FileResponse:
    access = _access(request)
    resolved = Path(path).expanduser().resolve()
    if not access.allows(resolved) or not resolved.is_file():
        raise HTTPException(status_code=404, detail="file not available")
    try:
        return FileResponse(resolved)
    except OSError as error:
        raise HTTPException(status_code=404, detail="file not available") from error
