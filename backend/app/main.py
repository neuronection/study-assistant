import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from alembic.config import Config
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from alembic import command

from . import __version__
from .ai.describe import GatewayDescriber
from .ai.embeddings import GatewayEmbedder
from .ai.gateway import LLMGateway
from .ai.graphs.chat_turn_adapter import ChatTurnEngine
from .ai.graphs.checkpointer import open_checkpointer, prune_checkpoints
from .ai.tasks import TASK_DEFS
from .api import ws as ws_router
from .api.chat import SessionTurnLocks, make_chat_turn_handler
from .api.desktop import router as desktop_router
from .api.router import api_router
from .core.config import Settings, get_settings
from .core.events import EventBus
from .core.logging import setup_logging
from .core.profile_context import (
    reset_active_profile,
    reset_active_user,
    set_active_profile,
    set_active_user,
)
from .core.vocab import WsTopic
from .jobs.runner import JobRunner
from .ocr.gateway_ocr import GatewayOcr
from .pipelines.compose import make_compose_handler
from .pipelines.drawing_ocr import make_drawing_ocr_handler
from .pipelines.genesis import make_genesis_handler
from .pipelines.image_ocr import make_image_ocr_handler
from .pipelines.ingest import make_ingest_handler
from .pipelines.postprocess import make_postprocess_handler
from .pipelines.url_import import make_url_import_handler
from .services.platform.backup import (
    BackupScheduler,
    EffectiveBackupSettings,
    boot_integrity_check,
    load_effective_settings,
)
from .services.platform.external_source_scheduler import ExternalSourceScheduler
from .services.platform.profiles import (
    get_or_create_default,
    get_owned_profile,
    last_used_profile,
    touch_last_used,
)
from .services.platform.scan_scheduler import ScanScheduler
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


PROFILE_BIND_EXEMPT_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/me",
    "/api/v1/profiles",
    "/api/v1/admin",
    "/api/v1/health",
    "/api/v1/instance",
    "/api/v1/desktop",
    "/api/v1/shell",
    # Browser *navigations* (PDF iframe documents, <img> subresources)
    # cannot carry the X-Profile-Id header at all — the blobs route is
    # exempt from the header requirement and owner-scopes the sha
    # itself (get_blob), so exemption never means open access.
    "/api/v1/blobs",
    "/api/docs",
)


async def _send_json_error(send: Any, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class ProfileBindingMiddleware:
    """X-Profile-Id ownership binding (identity-auth §15).

    Runs *inside* session enforcement (the verified `nx_principal` is in
    scope state) and binds user + profile into contextvars:

    - server: absent header ⇒ 400; malformed, unknown, or unowned
      ⇒ 403 — no silent default in web mode;
    - desktop: absent header ⇒ the last-used profile (Default
      fallback) — the silent boot UX;
    - exempt prefixes (auth, /me, /profiles, /admin, health, docs,
      beacon, desktop/shell plumbing) work without the header.
    """

    def __init__(self, app: Any, *, session_factory: Any, identity_mode: str) -> None:
        self.app = app
        self.session_factory = session_factory
        self.identity_mode = identity_mode

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        principal = scope.get("state", {}).get("nx_principal")
        user_id: str | None = principal.user_id if principal is not None else None
        raw = headers.get("x-profile-id")
        exempt = any(path.startswith(prefix) for prefix in PROFILE_BIND_EXEMPT_PREFIXES)
        profile_id: str | None = None
        with self.session_factory() as session:
            if raw:
                profile = get_owned_profile(session, user_id, raw) if user_id else None
                if profile is None:
                    if not exempt:
                        await _send_json_error(send, 403, "profile not allowed")
                        return
                else:
                    profile_id = profile.id
            elif not exempt:
                if user_id is None:
                    await _send_json_error(send, 401, "Not authenticated")
                    return
                if self.identity_mode != "desktop":
                    await _send_json_error(send, 400, "X-Profile-Id required")
                    return
                profile = last_used_profile(session, user_id) or get_or_create_default(
                    session, user_id
                )
                profile_id = profile.id
            if profile_id is not None and self.identity_mode == "desktop" and raw:
                touch_last_used(session, profile_id)
        user_token = set_active_user(user_id)
        profile_token = set_active_profile(profile_id)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_active_profile(profile_token)
            reset_active_user(user_token)


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
    cors = [
        raw.strip().rstrip("/") for raw in settings.cors_origins.split(",") if raw.strip()
    ]
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
    _run_migrations(app.state.engine)

    with app.state.session_factory() as session:
        from .ai.providers import seed_default_task_assignments
        from .domain.models import TaskAssignment

        for task_def in TASK_DEFS:
            if session.get(TaskAssignment, task_def.task) is None:
                session.add(
                    TaskAssignment(task=task_def.task, model_id=None, fallback_model_id=None)
                )
        seed_default_task_assignments(session)
        from .services.platform.skills import (
            seed_course_types,
            seed_error_patterns,
            seed_skills,
        )
        from .services.platform.trash import purge_expired

        seed_course_types(session)
        seed_error_patterns(session)
        seed_skills(session)
        session.commit()
        purge_expired(session)

    from .jobs.pruning import prune_done_jobs

    prune_done_jobs(app.state.session_factory, settings.jobs_done_ttl_days)

    from nx_auth import AuthConfig, KeyRing
    from nx_auth import install as install_auth_kit
    from nx_auth.shell import generate_shell_secret

    from .auth.stores import (
        StudyAuditSink,
        StudyInstanceStore,
        StudyProfileStore,
        StudySessionStore,
        StudyUserStore,
    )

    instance_store = StudyInstanceStore(app.state.session_factory)
    if instance_store.get("auth_mode") is None:
        initial_mode = settings.auth_mode or (
            "open" if settings.identity_mode == "desktop" else "authenticated"
        )
        instance_store.set("auth_mode", initial_mode)
        if settings.demo_mode:
            instance_store.set("demo_mode", "true")
    effective_auth_mode = instance_store.get("auth_mode")
    # §11 gate arms only when a shell actually attaches: shell.py sets
    # SA_SHELL=1 before create_app. Shell-less desktop dev (run-dev.sh:
    # uvicorn + vite, ADR-0023) has no shell to hold the secret or carry
    # it as `?shell=` — arming the gate there would 403 every auth
    # request from the dev SPA ("invalid shell token").
    shell_attached = settings.identity_mode == "desktop" and os.environ.get("SA_SHELL") == "1"
    if settings.identity_mode == "desktop" and not shell_attached:
        # Fail loud, not silent: this is the shell-less dev shape (ADR-0023)
        # — ungated + open-auth DIM. Safe on loopback only; a non-loopback
        # bind here exposes an owner-level API to the network.
        logging.getLogger(__name__).warning(
            "desktop identity WITHOUT an attached shell (SA_SHELL unset) — "
            "the X-Shell-Token gate is DISARMED (§11 / ADR-0023); bind the "
            "server to loopback only"
        )
        if effective_auth_mode != "open":
            # Init-only trap: a profile stamped `authenticated` under older
            # server-identity dev runs keeps it — the SPA shows the login
            # gate even though the §11 gate is disarmed (§4: mode changes
            # are admin actions, never launch-time).
            logging.getLogger(__name__).warning(
                "local profile auth_mode=%r — the login gate applies to this "
                "instance; `./scripts/run-dev.sh --reset` wipes the local "
                "profile and re-initializes it open (backups kept)",
                effective_auth_mode,
            )
    shell_secret: str | None = None
    if shell_attached:
        shell_secret = settings.shell_secret or generate_shell_secret()
    app.add_middleware(
        ProfileBindingMiddleware,
        session_factory=app.state.session_factory,
        identity_mode=settings.identity_mode,
    )
    auth_config = AuthConfig.from_env(
        "SA",
        iss="study",
        identity_mode=settings.identity_mode,
        require_shell_secret=shell_attached,
    )
    auth_config = replace(
        auth_config,
        # Public instance facts (S8 demo badge) must be readable pre-login.
        auth_exempt_prefixes=(*auth_config.auth_exempt_prefixes, "/api/v1/instance"),
    )
    install_auth_kit(
        app,
        config=auth_config,
        ring=KeyRing.load_or_generate(settings.config_dir / "auth_keys.json", "SA"),
        users=StudyUserStore(app.state.session_factory),
        sessions=StudySessionStore(app.state.session_factory),
        instance=instance_store,
        profiles=StudyProfileStore(app.state.session_factory),
        audit=StudyAuditSink(app.state.session_factory),
        shell_secret=shell_secret,
        # Navigation-served content (PDF iframes, <img>) cannot carry
        # X-Shell-Token — the blobs route skips the shell gate but stays
        # session-authenticated + owner-scoped (ADR-0024).
        shell_exempt_prefixes=("/api/v1/blobs",),
        owner_email="owner@local",
    )

    app.state.blobs = BlobStore(settings.blobs_dir)
    app.state.gateway = gateway if gateway is not None else LLMGateway(app.state.session_factory)
    from .services.platform.editor_ai import EditorTransformService

    app.state.editor_ai = EditorTransformService(app.state.session_factory, app.state.gateway)
    app.state.ocr = ocr if ocr is not None else GatewayOcr(app.state.gateway)
    app.state.embedder = embedder if embedder is not None else GatewayEmbedder(app.state.gateway)
    app.state.describer = (
        describer if describer is not None else GatewayDescriber(app.state.gateway)
    )

    def _chat_turn_group(job: Any) -> str | None:
        if job.type != "chat_turn":
            return None
        chat_session_id = (job.payload or {}).get("chat_session_id")
        if chat_session_id is None:
            return None
        return WsTopic.chat(chat_session_id)

    def _turn_engine() -> ChatTurnEngine | None:
        return getattr(app.state, "chat_turns", None)

    app.state.turn_locks = SessionTurnLocks()
    app.state.jobs = JobRunner(
        app.state.session_factory,
        app.state.bus,
        handlers={
            "ingest": make_ingest_handler(app.state.blobs, app.state.ocr, app.state.gateway),
            "postprocess": make_postprocess_handler(
                app.state.embedder.embed, app.state.describer.describe
            ),
            "chat_turn": make_chat_turn_handler(
                app.state.gateway,
                app.state.embedder,
                app.state.bus,
                turn_engine_provider=_turn_engine,
                search_transport_provider=lambda: getattr(
                    app.state, "search_transport", None
                ),
                turn_locks=app.state.turn_locks,
            ),
            "drawing_ocr": make_drawing_ocr_handler(app.state.gateway, app.state.blobs),
            "image_ocr": make_image_ocr_handler(app.state.gateway, app.state.blobs),
            "genesis": make_genesis_handler(
                app.state.gateway, app.state.blobs, app.state.embedder.embed
            ),
            "compose": make_compose_handler(
                app.state.gateway, app.state.blobs, app.state.embedder.embed
            ),
            "url_import": make_url_import_handler(
                app.state.blobs,
                lambda: getattr(app.state, "search_transport", None),
            ),
        },
        group_key=_chat_turn_group,
    )

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
