import os
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/desktop", tags=["desktop"])


class DesktopFileAccess:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._roots: set[Path] = set()

    def register_root(self, raw: str) -> Path:
        root = Path(raw).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"not a directory: {raw}")
        with self._lock:
            self._roots.add(root)
        return root

    def root_for(self, path: Path) -> Path | None:
        with self._lock:
            roots = tuple(self._roots)
        for root in sorted(roots, key=lambda item: len(item.parts), reverse=True):
            if path == root or root in path.parents:
                return root
        return None

    def allows(self, path: Path) -> bool:
        return self.root_for(path) is not None


class DesktopFileEntry(BaseModel):
    path: str
    rel: str
    size: int
    mtime: int


class DesktopFolderOut(BaseModel):
    path: str
    files: list[DesktopFileEntry]


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
    files: list[DesktopFileEntry] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
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
                    rel=f"{containing.name}/{resolved.relative_to(containing).as_posix()}",
                    size=stat.st_size,
                    mtime=int(stat.st_mtime),
                )
            )
    return DesktopFolderOut(path=str(root), files=files)


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
