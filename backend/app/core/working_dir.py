from pathlib import Path

import structlog

logger = structlog.get_logger()

POINTER_FILENAME = "working-dir.txt"


def read_override(config_dir: Path) -> Path | None:
    try:
        raw = (config_dir / POINTER_FILENAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        logger.warning("working_dir.override_ignored", path=raw)
        return None
    return path


def write_override(config_dir: Path, target: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / POINTER_FILENAME).write_text(f"{target}\n", encoding="utf-8")


def clear_override(config_dir: Path) -> bool:
    try:
        (config_dir / POINTER_FILENAME).unlink()
        return True
    except FileNotFoundError:
        return False
