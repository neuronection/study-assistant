import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from ..services.backup import (
    STAMP_PATTERN,
    BackupError,
    BackupSettingsOverride,
    EffectiveBackupSettings,
    build_backup,
    database_is_healthy,
    list_backups,
    load_effective_settings,
    read_archive,
    store_settings_override,
)
from ..services.profiles import ensure_default_profile

router = APIRouter(prefix="/backup", tags=["backup"])

MAX_UPLOAD = 512 * 1024 * 1024


class BackupSettingsIn(BaseModel):
    auto: bool | None = None
    interval_hours: int | None = Field(default=None, ge=1, le=168)
    keep_daily: int | None = Field(default=None, ge=1, le=365)
    keep_weekly: int | None = Field(default=None, ge=0, le=104)
    sync_dir: str | None = Field(default=None, max_length=1024)


def _settings_dir(request: Request) -> Path:
    settings = request.app.state.settings
    return Path(settings.data_dir)


def _defaults_from_settings(request: Request) -> EffectiveBackupSettings:
    settings = request.app.state.settings
    return EffectiveBackupSettings(
        auto=settings.auto_backup,
        interval_hours=settings.backup_interval_hours,
        keep_daily=settings.backup_keep_daily,
        keep_weekly=settings.backup_keep_weekly,
        sync_dir=str(settings.backup_sync_dir)
        if settings.backup_sync_dir
        else None,
    )


def _status(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    effective = load_effective_settings(
        _defaults_from_settings(request), _settings_dir(request)
    )
    recovery_path = settings.data_dir / "last-recovery.json"
    recovery: dict[str, Any] | None = None
    if recovery_path.is_file():
        try:
            recovery = json.loads(recovery_path.read_text())
        except ValueError:
            recovery = None
    return {
        "settings": {
            "auto": effective.auto,
            "interval_hours": effective.interval_hours,
            "keep_daily": effective.keep_daily,
            "keep_weekly": effective.keep_weekly,
            "sync_dir": effective.sync_dir,
        },
        "backups": list_backups(settings.backups_dir),
        "last_recovery": recovery,
    }


@router.get("/status")
def backup_status(request: Request) -> dict[str, Any]:
    return _status(request)


@router.put("/settings")
def backup_settings(body: BackupSettingsIn, request: Request) -> dict[str, Any]:
    sync_value = body.sync_dir.strip() if body.sync_dir is not None else None
    if sync_value:
        candidate = Path(sync_value).expanduser()
        if not candidate.is_dir():
            raise HTTPException(status_code=422, detail="sync dir does not exist")
    effective = store_settings_override(
        BackupSettingsOverride(
            auto=body.auto,
            interval_hours=body.interval_hours,
            keep_daily=body.keep_daily,
            keep_weekly=body.keep_weekly,
            sync_dir=sync_value,
        ),
        _settings_dir(request),
    )
    request.app.state.backups.wake()
    return {
        "settings": {
            "auto": effective.auto,
            "interval_hours": effective.interval_hours,
            "keep_daily": effective.keep_daily,
            "keep_weekly": effective.keep_weekly,
            "sync_dir": effective.sync_dir,
        }
    }


@router.post("/create")
def create_backup_now(request: Request) -> dict[str, Any]:
    try:
        path = request.app.state.backups.run_once(prefix="manual")
    except BackupError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    if path is None:
        raise HTTPException(status_code=500, detail="backup creation failed")
    return _status(request)


@router.delete("/{name}")
def delete_backup(name: str, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    if STAMP_PATTERN.match(name) is None:
        raise HTTPException(status_code=422, detail="invalid backup name")
    path = settings.backups_dir / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="backup not found")
    path.unlink()
    return _status(request)


@router.get("/export")
def export_backup(request: Request) -> Response:
    settings = request.app.state.settings
    package = build_backup(settings.db_path, settings.blobs_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=package,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="studyassistant-{stamp}.zip"'
        },
    )


def _apply_restore(request: Request, data: bytes) -> dict[str, Any]:
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=422, detail="backup too large")
    try:
        database, blobs = read_archive(data)
    except BackupError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not database_is_healthy(database):
        raise HTTPException(
            status_code=422, detail="backup database failed integrity check"
        )

    settings = request.app.state.settings
    request.app.state.engine.dispose()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    for sidecar in (
        settings.db_path.with_name(settings.db_path.name + "-wal"),
        settings.db_path.with_name(settings.db_path.name + "-shm"),
    ):
        sidecar.unlink(missing_ok=True)
    tmp_path = settings.db_path.with_name(settings.db_path.name + ".restore-tmp")
    try:
        tmp_path.write_bytes(database)
        os.replace(tmp_path, settings.db_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    for rel_path, blob_data in blobs.items():
        target = settings.blobs_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob_data)

    from ..main import _run_migrations

    _run_migrations(request.app.state.engine)

    from sqlalchemy import text

    from ..ai.providers import seed_default_task_assignments
    from ..ai.tasks import TASK_DEFS
    from ..domain.models import TaskAssignment

    with request.app.state.session_factory() as db:
        ensure_default_profile(db)
        for task_def in TASK_DEFS:
            if db.get(TaskAssignment, task_def.task) is None:
                db.add(
                    TaskAssignment(
                        task=task_def.task, model_id=None, fallback_model_id=None
                    )
                )
        seed_default_task_assignments(db)
        db.commit()
        count = db.execute(text("SELECT COUNT(*) FROM materials")).one()
    return {"status": "restored", "materials": int(count[0]), "blobs": len(blobs)}


@router.post("/restore", status_code=200)
async def restore_backup(request: Request, file: UploadFile) -> dict[str, Any]:
    return _apply_restore(request, await file.read())


@router.post("/{name}/restore", status_code=200)
def restore_backup_by_name(name: str, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    if STAMP_PATTERN.match(name) is None:
        raise HTTPException(status_code=422, detail="invalid backup name")
    path = settings.backups_dir / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="backup not found")
    return _apply_restore(request, path.read_bytes())
