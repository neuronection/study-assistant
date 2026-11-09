import sys
from pathlib import Path

MODES = ("app", "web", "mcp", "reset")


def resolve_mode(argv: list[str]) -> str:
    if len(argv) < 2:
        return "app"
    mode = argv[1]
    if mode not in MODES:
        raise SystemExit(f"unknown mode: {mode} (expected {'/'.join(MODES)})")
    return mode


def _reset_flags(argv: list[str]) -> tuple[bool, bool]:
    args = argv[2:]
    return "--all" in args or "-a" in args, "--yes" in args or "-y" in args


def _report_startup_error(data_dir: Path, error: Exception) -> None:
    error_path = data_dir / "STARTUP-ERROR.txt"
    try:
        error_path.write_text(str(error) + "\n", encoding="utf-8")
        written = True
    except OSError:
        written = False
    sys.stderr.write(f"\n{error}\n")
    if written:
        sys.stderr.write(f"\nThis message was written to {error_path}\n")


def _bootstrap() -> None:
    """Desktop profile bootstrap (app/local.py; plan 20 Phase 4): data
    dir + env defaults, then migrations — before any `Settings` is built.
    Migrations are an entrypoint responsibility (D6), never `create_app`'s.
    """
    from app.core.config import get_settings
    from app.local import (
        DatabaseVersionError,
        bootstrap_environment,
        default_data_dir,
        run_migrations,
    )
    from app.storage.datastore_guard import DatastoreQuarantineError, guard_datastore

    data_dir = default_data_dir()
    bootstrap_environment(data_dir)
    try:
        guard_datastore(get_settings())
        run_migrations()
    except (DatabaseVersionError, DatastoreQuarantineError) as error:
        _report_startup_error(data_dir, error)
        raise


if __name__ == "__main__":
    mode = resolve_mode(sys.argv)
    if mode == "mcp":
        _bootstrap()
        from app.ai.mcp_resources import run_mcp_stdio

        run_mcp_stdio()
    elif mode == "web":
        _bootstrap()
        from app.shell import run_browser

        run_browser()
    elif mode == "reset":
        from app.reset import run_reset

        include_backups, assume_yes = _reset_flags(sys.argv)
        if not run_reset(include_backups=include_backups, assume_yes=assume_yes):
            raise SystemExit(1)
    else:
        _bootstrap()
        from app.shell import run

        run()
