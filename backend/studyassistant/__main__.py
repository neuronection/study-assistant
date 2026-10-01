import sys

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


def _bootstrap() -> None:
    """Desktop profile bootstrap (app/local.py; plan 20 Phase 4): data
    dir + env defaults, then migrations — before any `Settings` is built.
    Migrations are an entrypoint responsibility (D6), never `create_app`'s.
    """
    from app.local import bootstrap_environment, default_data_dir, run_migrations

    bootstrap_environment(default_data_dir())
    run_migrations()


if __name__ == "__main__":
    mode = resolve_mode(sys.argv)
    if mode == "mcp":
        _bootstrap()
        from app.mcp_resources import run_mcp_stdio

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
