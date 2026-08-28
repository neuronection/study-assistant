import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from alembic import command

from . import __version__
from .ai.describe import GatewayDescriber
from .ai.embeddings import GatewayEmbedder
from .ai.gateway import LLMGateway
from .ai.tasks import TASK_DEFS
from .api import ws as ws_router
from .api.chat import make_chat_turn_handler
from .api.router import api_router
from .core.config import Settings, get_settings
from .core.events import EventBus
from .core.logging import setup_logging
from .core.profile_context import reset_active_profile, set_active_profile
from .jobs.runner import JobRunner
from .ocr.gateway_ocr import GatewayOcr
from .pipelines.ingest import make_ingest_handler
from .pipelines.postprocess import make_postprocess_handler
from .services.backup import (
    BackupScheduler,
    EffectiveBackupSettings,
    boot_integrity_check,
    load_effective_settings,
)
from .services.profiles import ensure_default_profile
from .services.scan_scheduler import ScanScheduler
from .storage.blobs import BlobStore
from .storage.db import Engine, make_engine, make_session_factory

ALEMBIC_ROOT = Path(__file__).resolve().parents[1]


def _find_spa_dist(settings: Settings) -> Path | None:
    if settings.spa_dist is not None:
        return settings.spa_dist if (settings.spa_dist / "index.html").is_file() else None
    import sys

    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
        bundled = Path(sys._MEIPASS) / "frontend" / "dist"  # type: ignore[attr-defined]
        if (bundled / "index.html").is_file():
            return bundled
    candidates = [
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
        Path.cwd() / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _run_migrations(engine: Engine) -> None:
    config = Config(str(ALEMBIC_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ALEMBIC_ROOT / "alembic"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    bus: EventBus = app.state.bus
    bus.bind_loop(asyncio.get_running_loop())
    jobs: JobRunner = app.state.jobs
    jobs.start()
    scheduler: ScanScheduler = app.state.scans
    scheduler.start()
    backups: BackupScheduler = app.state.backups
    backups.start()
    yield
    backups.stop()
    scheduler.stop()
    jobs.stop()
    app.state.engine.dispose()


async def profile_middleware(request: Request, call_next: Any) -> Any:
    raw = request.headers.get("x-profile-id")
    profile_id = int(raw) if raw and raw.isdigit() else None
    set_active_profile(profile_id)
    try:
        return await call_next(request)
    finally:
        set_active_profile(None)


class ProfileHeaderMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            raw = headers.get("x-profile-id")
            profile_id = int(raw) if raw and raw.isdigit() else None
            token = set_active_profile(profile_id)
            try:
                await self.app(scope, receive, send)
            finally:
                reset_active_profile(token)
        else:
            await self.app(scope, receive, send)


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Any) -> Any:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith(("api/", "ws/")):
                raise
            return await super().get_response("index.html", scope)


def create_app(
    settings: Settings | None = None,
    gateway: LLMGateway | None = None,
    ocr: GatewayOcr | None = None,
    embedder: GatewayEmbedder | None = None,
    describer: GatewayDescriber | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()
    setup_logging(settings.log_level)

    recovery = boot_integrity_check(
        settings.db_path, settings.backups_dir, settings.blobs_dir
    )
    if recovery is not None:
        import structlog

        logger = structlog.get_logger(__name__)
        logger.warning("boot_integrity_recovery", **recovery)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.debug else None,
    )
    app.state.settings = settings
    app.state.bus = EventBus()
    app.state.engine = make_engine(settings.db_path)
    app.state.session_factory = make_session_factory(app.state.engine)
    _run_migrations(app.state.engine)

    with app.state.session_factory() as session:
        ensure_default_profile(session)
        from .ai.providers import seed_default_task_assignments
        from .domain.models import TaskAssignment

        for task_def in TASK_DEFS:
            if session.get(TaskAssignment, task_def.task) is None:
                session.add(
                    TaskAssignment(task=task_def.task, model_id=None, fallback_model_id=None)
                )
        seed_default_task_assignments(session)
        from .services.skills import (
            seed_course_types,
            seed_error_patterns,
            seed_skills,
        )
        from .services.trash import purge_expired

        seed_course_types(session)
        seed_error_patterns(session)
        seed_skills(session)
        session.commit()
        purge_expired(session)

    from .jobs.pruning import prune_done_jobs

    prune_done_jobs(app.state.session_factory, settings.jobs_done_ttl_days)

    app.state.blobs = BlobStore(settings.blobs_dir)
    app.state.gateway = gateway if gateway is not None else LLMGateway(app.state.session_factory)
    from .services.editor_ai import EditorTransformService

    app.state.editor_ai = EditorTransformService(app.state.session_factory, app.state.gateway)
    app.state.ocr = ocr if ocr is not None else GatewayOcr(app.state.gateway)
    app.state.embedder = embedder if embedder is not None else GatewayEmbedder(app.state.gateway)
    app.state.describer = (
        describer if describer is not None else GatewayDescriber(app.state.gateway)
    )
    app.state.jobs = JobRunner(
        app.state.session_factory,
        app.state.bus,
        handlers={
            "ingest": make_ingest_handler(app.state.blobs, app.state.ocr),
            "postprocess": make_postprocess_handler(
                app.state.embedder.embed, app.state.describer.describe
            ),
            "chat_turn": make_chat_turn_handler(
                app.state.gateway, app.state.embedder, app.state.bus
            ),
        },
    )

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router.router)
    app.add_middleware(ProfileHeaderMiddleware)

    app.state.scans = ScanScheduler(
        app.state.session_factory,
        settings.blobs_dir,
        app.state.jobs,
        app.state.bus.publish_threadsafe,
        interval_sec=settings.source_scan_interval_sec,
    )

    def _backup_settings() -> EffectiveBackupSettings:
        return load_effective_settings(
            EffectiveBackupSettings(
                auto=settings.auto_backup,
                interval_hours=settings.backup_interval_hours,
                keep_daily=settings.backup_keep_daily,
                keep_weekly=settings.backup_keep_weekly,
                sync_dir=str(settings.backup_sync_dir)
                if settings.backup_sync_dir
                else None,
            ),
            settings.data_dir,
        )

    app.state.backups = BackupScheduler(
        _backup_settings,
        settings.db_path,
        settings.blobs_dir,
        settings.backups_dir,
        publish=app.state.bus.publish_threadsafe,
    )

    dist = _find_spa_dist(settings)
    if dist is not None:
        app.mount("/", SpaStaticFiles(directory=dist, html=True), name="spa")
    else:

        @app.get("/")
        def root() -> dict[str, str]:
            return {"detail": "frontend not built; run `pnpm --filter frontend build`"}

    return app
