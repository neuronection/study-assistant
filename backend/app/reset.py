import shutil
from pathlib import Path

from .core.config import Settings, get_settings
from .storage.bootstrap import resolve_storage_config
from .storage.object_storage import StorageConfigError


def collect_targets(
    settings: Settings, *, include_backups: bool, blobs_dir: Path | None = None
) -> list[Path]:
    db = settings.db_path
    targets = [
        db,
        Path(f"{db}-wal"),
        Path(f"{db}-shm"),
        blobs_dir or settings.blobs_dir,
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
    try:
        config = resolve_storage_config(settings)
    except StorageConfigError as error:
        print(
            "Reset is a desktop/local-filesystem feature and cannot run under a "
            f"cloud/object-storage profile ({error}). Fix SA_* storage config or "
            "use a local profile."
        )
        return False
    if config.is_object:
        print(
            "Reset is a desktop/local-filesystem feature; object storage owns "
            "durability and is not deleted by this command."
        )
        return False
    targets = collect_targets(
        settings,
        include_backups=include_backups,
        blobs_dir=config.local_root or settings.blobs_dir,
    )
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
