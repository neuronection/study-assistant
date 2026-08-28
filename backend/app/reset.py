import shutil
from pathlib import Path

from .core.config import Settings, get_settings


def collect_targets(settings: Settings, *, include_backups: bool) -> list[Path]:
    db = settings.db_path
    targets = [
        db,
        Path(f"{db}-wal"),
        Path(f"{db}-shm"),
        settings.blobs_dir,
        settings.cache_dir,
        settings.thumbnails_dir,
        settings.inbox_dir,
    ]
    if include_backups:
        targets.append(settings.backups_dir)
    return [target for target in targets if target.exists()]


def delete_targets(targets: list[Path]) -> None:
    for target in targets:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()


def run_reset(*, include_backups: bool, assume_yes: bool) -> bool:
    settings = get_settings()
    targets = collect_targets(settings, include_backups=include_backups)
    if not targets:
        print(f"Nothing to reset — no data found under {settings.data_dir}")
        return True
    print(f"Resetting Study Assistant data under {settings.data_dir}:")
    for target in targets:
        print(f"  - {target}")
    if not assume_yes:
        answer = input("Delete the above? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return False
    delete_targets(targets)
    print("Reset complete.")
    return True
