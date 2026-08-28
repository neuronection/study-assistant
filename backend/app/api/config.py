from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..core.config import default_data_dir
from ..core.working_dir import clear_override, read_override, write_override

router = APIRouter(prefix="/config", tags=["config"])


class WorkingDirIn(BaseModel):
    path: str = Field(min_length=1, max_length=1024)


def _is_writable(directory: Path) -> bool:
    probe = directory / ".sa-write-probe"
    try:
        probe.write_text("", encoding="utf-8")
    except OSError:
        return False
    finally:
        probe.unlink(missing_ok=True)
    return True


def _nearest_existing_ancestor(path: Path) -> Path:
    ancestor = path
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    return ancestor


def _validate_target(current: Path, raw: str) -> tuple[Path | None, str | None, dict[str, Any]]:
    info: dict[str, Any] = {"exists": False, "empty": False, "has_app_db": False}
    try:
        candidate = Path(raw).expanduser()
    except (OSError, RuntimeError, ValueError):
        return None, "invalid_path", info
    if not candidate.is_absolute():
        return None, "relative_path", info
    if candidate == current:
        return None, "already_current", info
    if candidate in current.parents:
        return None, "contains_current", info
    if current in candidate.parents:
        return None, "inside_current", info
    if candidate.exists():
        info["exists"] = True
        if not candidate.is_dir():
            return None, "not_a_directory", info
        if not _is_writable(candidate):
            return None, "not_writable", info
        info["empty"] = not any(candidate.iterdir())
        info["has_app_db"] = (candidate / "app.db").is_file()
        if not info["empty"] and not info["has_app_db"]:
            return None, "not_empty", info
        return candidate, None, info
    ancestor = _nearest_existing_ancestor(candidate)
    if not ancestor.is_dir() or not _is_writable(ancestor):
        return None, "not_writable", info
    return candidate, None, info


@router.get("/working-dir")
def get_working_dir(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    pointer = read_override(Path(settings.config_dir))
    current = Path(settings.data_dir)
    return {
        "path": str(current),
        "default_path": str(default_data_dir()),
        "custom": pointer is not None,
        "restart_pending": pointer is not None and pointer != current,
    }


@router.post("/working-dir/validate")
def validate_working_dir(request: Request, body: WorkingDirIn) -> dict[str, Any]:
    settings = request.app.state.settings
    target, reason, info = _validate_target(Path(settings.data_dir), body.path)
    return {"valid": target is not None, "reason": reason, **info}


@router.put("/working-dir")
def set_working_dir(request: Request, body: WorkingDirIn) -> dict[str, Any]:
    settings = request.app.state.settings
    target, reason, _ = _validate_target(Path(settings.data_dir), body.path)
    if target is None:
        raise HTTPException(status_code=422, detail=f"invalid working directory: {reason}")
    write_override(Path(settings.config_dir), target)
    return {"path": str(target), "restart_required": True}


@router.delete("/working-dir")
def reset_working_dir(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    pointer = read_override(Path(settings.config_dir))
    removed = clear_override(Path(settings.config_dir))
    return {
        "restart_required": removed and pointer is not None and pointer != Path(settings.data_dir)
    }
