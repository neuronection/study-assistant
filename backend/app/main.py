"""Application factory (plan 20 Phase 4 split).

Wiring only: middleware registration, service construction, router and
scheduler mounting. Identity lives in `app.auth.install`, profile binding
and SPA fallback in `app.middleware`, per-boot seeding in `app.seeds`,
job handlers in `app.jobs.registry`, and migrations are an entrypoint
responsibility (`app.local` / the docker `migrate` service / test
fixtures — D6): `create_app` never runs them.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from . import __version__
from .ai.describe import GatewayDescriber
from .ai.embeddings import GatewayEmbedder
from .ai.gateway import LLMGateway
from .ai.graphs.chat_turn_adapter import ChatTurnEngine
from .ai.graphs.checkpointer import open_checkpointer, prune_checkpoints
from .auth.install import install_identity
from .core.config import Settings, get_settings
from .core.events import EventBus
from .core.logging import setup_logging
from .jobs.registry import build_job_runner
from .jobs.runner import JobRunner
from .middleware import ProfileBindingMiddleware, SpaStaticFiles
from .ocr.gateway_ocr import GatewayOcr
from .seeds import run_startup_seeds
from .services.platform.backup import (
    BackupScheduler,
    EffectiveBackupSettings,
    boot_integrity_check,
    load_effective_settings,
)
from .services.platform.external_source_scheduler import ExternalSourceScheduler
from .services.platform.scan_scheduler import ScanScheduler
from .storage.blobs import BlobStore
from .storage.db import make_engine, make_session_factory


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    bus: EventBus = app.state.bus
    bus.bind_loop(asyncio.get_running_loop())
    async with AsyncExitStack() as stack:
        app.state.checkpointer = await stack.enter_async_context(
            open_checkpointer(
                app.state.engine.dialect.name,
                app.state.settings.checkpoints_path,
                postgres_uri=(
                    app.state.settings.db_url.replace("+psycopg", "")
                    if app.state.engine.dialect.name == "postgresql"
                    else None
                ),
            )
        )
        app.state.chat_turns = ChatTurnEngine(app.state.checkpointer, bus)
        prune_checkpoints(
            app.state.settings.checkpoints_path,
            app.state.settings.checkpoint_ttl_days,
            engine=app.state.engine,
        )
        jobs: JobRunner = app.state.jobs
        jobs.start()
        scheduler: ScanScheduler = app.state.scans
        scheduler.start()
        external_scheduler: ExternalSourceScheduler = app.state.external_scans
        external_scheduler.start()
        backups: BackupScheduler = app.state.backups
        backups.start()
        yield
        backups.stop()
        external_scheduler.stop()
        scheduler.stop()
        jobs.stop()
    app.state.engine.dispose()


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

    # Production boot guards (ADR-0028): fail fast on unsafe config —
    # partial/weak key pins, DEBUG/DEMO_MODE in production. Dev/test
    # boots are unaffected.
    from nx_auth.boot import validate_boot_config

    from .core.keys import data_key_previous

    for warning in validate_boot_config(
        production=settings.is_production,
        identity_mode=settings.identity_mode,
        session_key=settings.session_key,
        refresh_key=settings.refresh_key,
        data_key=settings.data_key,
        data_key_previous=data_key_previous(settings),
        key_env_prefix="SA",
        debug=settings.debug,
        demo_mode=settings.demo_mode,
    ):
        logging.getLogger(__name__).warning("boot guard: %s", warning)

    recovery = boot_integrity_check(
        settings.db_path,
        settings.backups_dir,
        settings.blobs_dir,
        database_url=settings.db_url,
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
    cors = [raw.strip().rstrip("/") for raw in settings.cors_origins.split(",") if raw.strip()]
    if cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["content-type", "x-profile-id", "x-csrf-token"],
        )
    app.state.settings = settings
    app.state.bus = EventBus()
    app.state.engine = make_engine(settings.db_url)
    app.state.session_factory = make_session_factory(app.state.engine)

    run_startup_seeds(app.state.session_factory, jobs_done_ttl_days=settings.jobs_done_ttl_days)

    # Order matters: profile binding registers first so the kit's session
    # enforcement stays the outermost middleware (§15 runs inside it).
    app.add_middleware(
        ProfileBindingMiddleware,
        session_factory=app.state.session_factory,
        identity_mode=settings.identity_mode,
    )
    install_identity(app, settings, app.state.session_factory)

    app.state.blobs = BlobStore(settings.blobs_dir)
    app.state.gateway = gateway if gateway is not None else LLMGateway(app.state.session_factory)
    from .services.platform.editor_ai import EditorTransformService

    app.state.editor_ai = EditorTransformService(app.state.session_factory, app.state.gateway)
    app.state.ocr = ocr if ocr is not None else GatewayOcr(app.state.gateway)
    app.state.embedder = embedder if embedder is not None else GatewayEmbedder(app.state.gateway)
    app.state.describer = (
        describer if describer is not None else GatewayDescriber(app.state.gateway)
    )

    app.state.jobs = build_job_runner(app)

    from .api import ws as ws_router
    from .api.desktop import router as desktop_router
    from .api.router import api_router

    app.include_router(api_router, prefix="/api/v1")
    if settings.identity_mode == "desktop":
        app.include_router(desktop_router, prefix="/api/v1")
    app.include_router(ws_router.router)

    app.state.scans = ScanScheduler(
        app.state.session_factory,
        settings.blobs_dir,
        app.state.jobs,
        app.state.bus.publish_threadsafe,
        interval_sec=settings.source_scan_interval_sec,
    )
    app.state.external_scans = ExternalSourceScheduler(
        app.state.session_factory,
        app.state.bus.publish_threadsafe,
    )

    def _backup_settings() -> EffectiveBackupSettings:
        return load_effective_settings(
            EffectiveBackupSettings(
                auto=settings.auto_backup,
                interval_hours=settings.backup_interval_hours,
                keep_daily=settings.backup_keep_daily,
                keep_weekly=settings.backup_keep_weekly,
                sync_dir=str(settings.backup_sync_dir) if settings.backup_sync_dir else None,
            ),
            settings.data_dir,
        )

    app.state.backups = BackupScheduler(
        _backup_settings,
        settings.db_path,
        settings.blobs_dir,
        settings.backups_dir,
        publish=app.state.bus.publish_threadsafe,
        database_url=settings.db_url,
    )

    dist = _find_spa_dist(settings)
    if dist is not None:
        app.mount("/", SpaStaticFiles(directory=dist, html=True), name="spa")
    else:

        @app.get("/")
        def root() -> dict[str, str]:
            return {"detail": "frontend not built; run `pnpm --filter frontend build`"}

    return app
