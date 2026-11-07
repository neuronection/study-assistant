"""Local (desktop) profile bootstrap: data dir, env, migrations.

Imported by the `studyassistant` entrypoint — the env defaults must be
set **before** `get_settings()` is first called so plain environment
variables carry the desktop profile into `Settings` (family reference
shape: career-assistant's `app/local.py`; plan 20 Phase 4).

Migrations are an entrypoint/CLI responsibility (D6): `run_migrations()`
is called here for desktop/mcp boots, by the docker `migrate` service
for servers, by `scripts/run-dev.sh` in dev, and by test fixtures —
never by `create_app`.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ENV_FILE = "env"


class DatabaseVersionError(RuntimeError):
    """The datastore was created by an incompatible (pre-squash) release."""


def default_data_dir(environ: MutableMapping[str, str] | None = None) -> Path:
    """Effective data directory (matches Settings.data_dir): `SA_DATA_DIR`
    when set, else the override-aware platform default."""
    from .core.config import resolve_data_dir

    env = os.environ if environ is None else environ
    if env.get("SA_DATA_DIR"):
        return Path(env["SA_DATA_DIR"]).expanduser()
    return resolve_data_dir()


def bootstrap_environment(
    data_dir: Path, environ: MutableMapping[str, str] | None = None
) -> MutableMapping[str, str]:
    """Set desktop defaults via setdefault — real env vars still win."""
    env = os.environ if environ is None else environ
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "blobs").mkdir(exist_ok=True)
    (data_dir / "logs").mkdir(exist_ok=True)

    env.setdefault("SA_DATA_DIR", str(data_dir))
    env.setdefault("SA_DATABASE_URL", f"sqlite:///{data_dir / 'study.sqlite3'}")
    env.setdefault("SA_ENV_FILE", str(data_dir / ENV_FILE))  # optional user overrides
    # Entrypoint half of the instance-mode matrix (identity-auth §4):
    # `python -m studyassistant` is the desktop entrypoint.
    env.setdefault("SA_IDENTITY_MODE", "desktop")
    # Per-instance keys (identity-auth §8) are NOT seeded here: the
    # auth-kit KeyRing persists a generated 0600 auth_keys.json in the
    # config dir (nx_auth.keys.KeyRing.load_for).
    return env


def find_alembic_ini() -> Path:
    """Locate alembic.ini in the checkout or a frozen bundle."""
    candidates = []
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidates.append(Path(bundled) / "alembic.ini")
    candidates.append(Path(__file__).resolve().parents[1] / "alembic.ini")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("alembic.ini not found; cannot run migrations")


def _config() -> Any:
    from alembic.config import Config

    ini = find_alembic_ini()
    config = Config(str(ini))
    config.set_main_option("script_location", str(ini.parent / "alembic"))
    return config


def _known_revisions(config: Any) -> frozenset[str]:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    return frozenset(revision.revision for revision in script.walk_revisions())


def known_revisions() -> frozenset[str]:
    """Every revision id in this release's chain (for restore/upgrade guards)."""
    return _known_revisions(_config())


def head_revision() -> str:
    """The single head this release expects."""
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(_config()).get_current_head()
    if head is None:
        raise RuntimeError("alembic chain has no head")
    return head


def _current_revision(engine: Any | None) -> str | None:
    from sqlalchemy import text

    if engine is not None:
        try:
            with engine.connect() as connection:
                row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
        except Exception:
            return None
        return str(row[0]) if row else None

    from sqlalchemy import create_engine

    from .core.config import get_settings

    created = create_engine(get_settings().db_url)
    try:
        return _current_revision(created)
    except Exception:
        return None
    finally:
        created.dispose()


def _incompatible_message(current: str, head: str) -> str:
    from .core.config import get_settings

    settings = get_settings()
    return (
        "This study database was created by an earlier release and cannot be upgraded.\n"
        f"  datastore revision: {current}\n"
        f"  this release needs: {head}\n\n"
        "The 0.13 schema is a deliberate break: there is no migration path.\n"
        "Your data is still on disk. To start fresh, move the old datastore aside or run\n"
        "  python -m studyassistant reset --all\n"
        "(packaged app: StudyAssistant reset; add --all to remove backups too),\n"
        f"then relaunch. Datastore: {settings.db_path}"
    )


def ensure_compatible_database(engine: Any | None = None) -> None:
    """Refuse a datastore whose stamped revision is not in this chain."""
    config = _config()
    current = _current_revision(engine)
    if current is None:
        return
    known = _known_revisions(config)
    if current not in known:
        raise DatabaseVersionError(_incompatible_message(current, head_revision()))


def run_migrations(engine: Any | None = None) -> None:
    """Apply pending migrations (D6: entrypoint/ops-owned, never `create_app`).

    With `engine`, the upgrade runs connection-scoped against that
    engine's database (restore flows, test fixtures); without, alembic
    resolves the URL from `Settings` (entrypoint boots).
    """

    from alembic import command

    config = _config()
    ensure_compatible_database(engine)
    if engine is not None:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    else:
        command.upgrade(config, "head")
    logger.info("Migrations applied (%s)", find_alembic_ini())
