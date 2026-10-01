"""Family auth-kit installation (identity-auth §4/§5/§8/§10/§11).

`install_identity` mounts nx_auth at its exact §12 paths and wires the
ADR-0028 glue:

- init-only instance modes via `nx_auth.instance.initialize_instance`
  (DB authoritative, env flips ignored loudly, fail-closed; §4);
- the §16 knob set routed from `Settings` through
  `nx_auth.config.knob_overrides` so deployment `.env` values reach the
  kit config exactly like process-environment ones (OS env wins per key);
- one `KeyRing.load_for` resolution for signing AND secrets at rest (§8);
- the §11 shell gate: armed only when a shell actually attaches
  (`SA_SHELL=1`), disarmed with loud warnings otherwise (ADR-0023).

Profile binding is separate middleware (`app.middleware`) and must be
registered **before** this call so session enforcement stays outermost.
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from typing import Any, Literal

from fastapi import FastAPI
from nx_auth import AuthConfig, KeyRing
from nx_auth import install as install_auth_kit
from nx_auth.config import knob_overrides
from nx_auth.instance import IdentityMode, initialize_instance
from nx_auth.shell import generate_shell_secret

from ..core.config import Settings

logger = logging.getLogger(__name__)


def _settings_knob(settings: Settings, name: str) -> object | None:
    """§16 knob map getter (ADR-0028): env name → Settings field."""
    return getattr(settings, name.removeprefix("SA_").lower(), None)


def install_identity(
    application: FastAPI, settings: Settings, session_factory: Any
) -> None:
    """Mount the family auth-kit (identity-auth §4/§5/§8/§10/§11)."""
    from .stores import (
        StudyAuditSink,
        StudyInstanceStore,
        StudyProfileStore,
        StudySessionStore,
        StudyUserStore,
    )

    instance_store = StudyInstanceStore(session_factory)
    # §4 init-only rules (ADR-0028): one family implementation — §4.4
    # open-on-server coercion, unknown values fail closed, post-init env
    # flips ignored loudly, demo_mode written explicitly.
    effective_auth_mode = initialize_instance(
        instance_store,
        identity_mode=settings.identity_mode,
        auth_mode_env=settings.auth_mode,
        demo_mode_env=settings.demo_mode,
        product="SA",
    )

    # §11 gate arms only when a shell actually attaches: shell.py sets
    # SA_SHELL=1 before create_app. Shell-less desktop dev (run-dev.sh:
    # uvicorn + vite, ADR-0023) has no shell to hold the secret or carry
    # it as `?shell=` — arming the gate there would 403 every auth
    # request from the dev SPA ("invalid shell token").
    shell_attached = (
        settings.identity_mode is IdentityMode.DESKTOP
        and os.environ.get("SA_SHELL") == "1"
    )
    if settings.identity_mode is IdentityMode.DESKTOP and not shell_attached:
        # Fail loud, not silent: this is the shell-less dev shape (ADR-0023)
        # — ungated + open-auth DIM. Safe on loopback only; a non-loopback
        # bind here exposes an owner-level API to the network.
        logger.warning(
            "desktop identity WITHOUT an attached shell (SA_SHELL unset) — "
            "the X-Shell-Token gate is DISARMED (§11 / ADR-0023); bind the "
            "server to loopback only"
        )
        if effective_auth_mode != "open":
            # Init-only trap: a profile stamped `authenticated` under older
            # server-identity dev runs keeps it — the SPA shows the login
            # gate even though the §11 gate is disarmed (§4: mode changes
            # are admin actions, never launch-time).
            logger.warning(
                "local profile auth_mode=%r — the login gate applies to this "
                "instance; `./scripts/run-dev.sh --reset` wipes the local "
                "profile and re-initializes it open (backups kept)",
                effective_auth_mode,
            )
    shell_secret: str | None = None
    if shell_attached:
        shell_secret = settings.shell_secret or generate_shell_secret()

    kit_identity: Literal["server", "desktop"] = (
        "desktop" if settings.identity_mode is IdentityMode.DESKTOP else "server"
    )
    auth_config = AuthConfig.from_env(
        "SA",
        iss="study",
        identity_mode=kit_identity,
        require_shell_secret=shell_attached,
        # §16 knobs routed through Settings (ADR-0028): the `.env` file
        # and the process environment both reach the kit config (OS env
        # wins per key) — the kit's own `os.environ` read is the fallback.
        **knob_overrides("SA", lambda name: _settings_knob(settings, name)),
    )
    auth_config = replace(
        auth_config,
        # Public instance facts (S8 demo badge) must be readable pre-login.
        auth_exempt_prefixes=(*auth_config.auth_exempt_prefixes, "/api/v1/instance"),
    )
    install_auth_kit(
        application,
        config=auth_config,
        ring=KeyRing.load_for(
            "SA",
            settings.config_dir,
            pinned=(settings.session_key, settings.refresh_key, settings.data_key),
        ),
        users=StudyUserStore(session_factory),
        sessions=StudySessionStore(session_factory),
        instance=instance_store,
        profiles=StudyProfileStore(session_factory),
        audit=StudyAuditSink(session_factory),
        shell_secret=shell_secret,
        # Navigation-served content (PDF iframes, <img>) cannot carry
        # X-Shell-Token — the blobs route skips the shell gate but stays
        # session-authenticated + owner-scoped (ADR-0024).
        shell_exempt_prefixes=("/api/v1/blobs",),
        owner_email="owner@local",
    )
