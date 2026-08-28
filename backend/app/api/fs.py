from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .deps import get_session

router = APIRouter(prefix="/fs", tags=["fs"])


class FsDir(BaseModel):
    name: str
    path: str


class FsDirsOut(BaseModel):
    path: str
    parent: str | None
    home: str
    dirs: list[FsDir]


@router.get("/dirs", response_model=FsDirsOut)
def list_dirs(path: str | None = None, session: Session = Depends(get_session)) -> FsDirsOut:
    del session
    home = str(Path.home())
    target = Path(path).expanduser() if path else Path(home)
    try:
        resolved = target.resolve()
        if not resolved.is_dir():
            raise HTTPException(status_code=422, detail="not a directory")
        entries = sorted(resolved.iterdir(), key=lambda entry: entry.name.lower())
    except (OSError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=f"cannot open directory: {error}") from error
    dirs = [
        FsDir(name=entry.name, path=str(entry))
        for entry in entries
        if entry.is_dir() and not entry.name.startswith(".")
        and not entry.is_symlink()
    ]
    parent = str(resolved.parent) if resolved.parent != resolved else None
    return FsDirsOut(path=str(resolved), parent=parent, home=home, dirs=dirs)
