"""Copy study's legacy blob tree into the configured object store.

Family tooling for plan 55 P4 (see ``docs/dev/storage.md``). Study's keys are
already content-addressed (``<aa>/<bb>/<sha256>``), so the migration is a
straight copy of ``settings.blobs_dir`` with the relative path as the object
key. There is no database backfill: the ``blobs`` table indexes sha256, not a
path.

Usage (run from ``backend/`` with the project environment active):

    python scripts/migrate_objects.py --dry-run
    python scripts/migrate_objects.py --apply
    python scripts/migrate_objects.py --verify
    python scripts/migrate_objects.py --backfill-db

The manifest defaults to ``<data_dir>/migrations/object-storage-manifest.json``
and is written atomically after every entry, so an interrupted run resumes.
The target prefix must be empty unless ``--force`` is passed. Desktop never
runs this tool: a desktop entrypoint is local-only and has no target.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.storage.bootstrap import resolve_storage_config, storage_entrypoint
from app.storage.object_storage import (
    BACKEND_LOCAL,
    ENTRYPOINT_DESKTOP,
    build_store,
    normalize_key,
)
from app.storage.object_storage_migrate import (
    STATUS_UNREADABLE,
    Manifest,
    ManifestError,
    ManifestTargetMismatch,
    MigrationEntry,
    TargetNotEmpty,
    VerifyRequired,
    bind_target,
    check_binding,
    load_manifest,
    merge_entries,
    new_manifest,
    plan_entries,
    rebind_manifest,
    require_verified,
    save_manifest,
    target_descriptor,
)
from app.storage.object_storage_migrate import (
    apply as apply_entries,
)
from app.storage.object_storage_migrate import (
    verify as verify_entries,
)

HOST = "study-assistant"
_LEGACY_KEY = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}$")
_PROBLEM_STATUSES = {
    "failed",
    "missing",
    "unreadable",
    "collision",
    "skipped",
}
_BLOCKING_STATUSES = {"failed", "missing", "unreadable", "collision"}


def default_manifest_path(settings: Settings) -> Path:
    return Path(settings.data_dir) / "migrations" / "object-storage-manifest.json"


def legacy_key(relative: str) -> str | None:
    """A legacy study blob key, or ``None`` for anything else in the root."""
    if not _LEGACY_KEY.match(relative):
        return None
    try:
        return normalize_key(relative)
    except ValueError:
        return None


def _checked_entries(settings: Settings) -> list[MigrationEntry]:
    """Plan the blob root and quarantine content that does not match its key."""
    entries = plan_entries(Path(settings.blobs_dir), legacy_key)
    for entry in entries:
        if entry.key and entry.sha256 and Path(entry.source).name != entry.sha256:
            entry.status = STATUS_UNREADABLE
            entry.error = (
                "content does not match its content-addressed sha256; "
                "refusing to copy a corrupt blob"
            )
            entry.key = ""
    return entries


def _report(manifest: Manifest, label: str) -> None:
    counts = manifest.counts()
    print(
        f"{label}: {counts['total']} entries — "
        f"copied {counts['copied']}, verified {counts['verified']}, "
        f"pending {counts['pending']}, failed {counts['failed']}, "
        f"missing {counts['missing']}, unreadable {counts['unreadable']}, "
        f"collision {counts['collision']}, skipped {counts['skipped']}"
    )
    problems = [entry for entry in manifest.entries if entry.status in _PROBLEM_STATUSES]
    for entry in problems[:20]:
        print(f"  {entry.status}: {entry.source} — {entry.error}")
    if len(problems) > 20:
        print(f"  … {len(problems) - 20} more")


def _load_or_plan(
    settings: Settings,
    manifest_path: Path,
    *,
    force: bool,
    store: Any,
    rebind: bool,
) -> Manifest:
    source = Path(settings.blobs_dir)
    if manifest_path.exists():
        try:
            manifest = load_manifest(manifest_path)
        except ManifestError as exc:
            if not force:
                raise SystemExit(
                    f"corrupt manifest {manifest_path}: {exc}. "
                    "Move it aside or pass --force to start a fresh ledger."
                ) from exc
            print(f"ignoring corrupt manifest (--force): {exc}")
            manifest = new_manifest(HOST, source, path=manifest_path)
            bind_target(manifest, store)
        else:
            if rebind:
                rebind_manifest(manifest, store, host=HOST, source_root=source)
                print(f"rebound manifest to {manifest.target.label() if manifest.target else '-'}")
            else:
                check_binding(manifest, store, host=HOST, source_root=source)
    else:
        manifest = new_manifest(HOST, source, path=manifest_path)
        bind_target(manifest, store)
    merge_entries(manifest, _checked_entries(settings))
    manifest.path = str(manifest_path)
    return manifest


def _refuse_self_copy(settings: Settings, store: Any) -> None:
    if store.backend != BACKEND_LOCAL:
        return
    source = Path(settings.blobs_dir).resolve()
    target = Path(getattr(store, "root", source)).resolve()
    if source == target:
        raise SystemExit(
            f"source and target are the same local root ({source}); "
            "nothing to copy. Set SA_OBJECT_STORAGE_LOCAL_ROOT to a different "
            "directory or configure an object backend."
        )
    if source in target.parents or target in source.parents:
        raise SystemExit(
            f"source ({source}) and target ({target}) roots are nested; use "
            "separate directory trees so a copy can never read its own output."
        )


def run(args: argparse.Namespace, settings: Settings) -> int:
    if storage_entrypoint(settings) == ENTRYPOINT_DESKTOP:
        raise SystemExit(
            "desktop is local-only: there is no bucket to migrate to. "
            "migrate-objects never runs on a desktop build."
        )
    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(settings)
    config = resolve_storage_config(settings)
    store = build_store(config)
    print(f"target: {target_descriptor(store).label()}")
    try:
        source = Path(settings.blobs_dir)
        if args.backfill_db:
            try:
                manifest = load_manifest(manifest_path)
            except FileNotFoundError:
                raise SystemExit(
                    f"no manifest at {manifest_path}; run --apply and --verify first"
                ) from None
            except ManifestError as exc:
                raise SystemExit(f"corrupt manifest {manifest_path}: {exc}") from exc
            try:
                if args.rebind:
                    rebind_manifest(manifest, store, host=HOST, source_root=source)
                    save_manifest(manifest_path, manifest)
                else:
                    check_binding(manifest, store, host=HOST, source_root=source)
                require_verified(manifest)
            except (ManifestTargetMismatch, VerifyRequired) as exc:
                raise SystemExit(str(exc)) from exc
            print(
                "study has no database backfill: the blobs table is keyed by "
                "sha256, not by a filesystem path."
            )
            return 0

        if args.verify:
            try:
                manifest = load_manifest(manifest_path)
            except FileNotFoundError:
                raise SystemExit(f"no manifest at {manifest_path}; run --apply first") from None
            except ManifestError as exc:
                raise SystemExit(f"corrupt manifest {manifest_path}: {exc}") from exc
            try:
                if args.rebind:
                    rebind_manifest(manifest, store, host=HOST, source_root=source)
                    save_manifest(manifest_path, manifest)
                else:
                    check_binding(manifest, store, host=HOST, source_root=source)
            except ManifestTargetMismatch as exc:
                raise SystemExit(str(exc)) from exc
            summary = verify_entries(store, manifest, host=HOST, source_root=source)
            _report(manifest, "verify")
            if summary["blocking"]:
                print(
                    f"blocking: {summary['blocking']} entry/entries — {summary['blocking_entries']}"
                )
            return 0 if summary["blocking"] == 0 else 1

        _refuse_self_copy(settings, store)
        try:
            manifest = _load_or_plan(
                settings, manifest_path, force=args.force, store=store, rebind=args.rebind
            )
        except ManifestTargetMismatch as exc:
            raise SystemExit(str(exc)) from exc
        if not args.dry_run:
            save_manifest(manifest_path, manifest)
        try:
            summary = apply_entries(
                store,
                manifest,
                dry_run=args.dry_run,
                force=args.force,
                host=HOST,
                source_root=source,
            )
        except (TargetNotEmpty, ManifestTargetMismatch) as exc:
            raise SystemExit(str(exc)) from exc
        _report(manifest, "dry run" if args.dry_run else "apply")
        print(
            f"this run: copied {summary['copied']}, remaining {summary['remaining']}, "
            f"pending {summary['pending']}, foreign {summary['foreign']}"
        )
        print(f"manifest: {manifest_path}")
        if args.dry_run:
            print(f"would copy {summary['planned']} object(s)")
            if summary["foreign"]:
                print(
                    f"warning: target prefix has {summary['foreign']} foreign object(s); "
                    "--apply will require --force"
                )
            blocked = any(entry.status in _BLOCKING_STATUSES for entry in manifest.entries)
            return 1 if blocked else 0
        blocked = any(entry.status in _BLOCKING_STATUSES for entry in manifest.entries)
        return 1 if summary["failed"] or blocked else 0
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate study's local blob tree into the configured object store."
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--dry-run", action="store_true", help="plan and report only")
    action.add_argument("--apply", action="store_true", help="copy into the target store")
    action.add_argument("--verify", action="store_true", help="re-read the target and compare")
    action.add_argument(
        "--backfill-db",
        action="store_true",
        help="study has no path backfill; reports the no-op",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="manifest path (default: <data_dir>/migrations/object-storage-manifest.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow a non-empty target prefix or replace a corrupt manifest",
    )
    parser.add_argument(
        "--rebind",
        action="store_true",
        help="adopt the current target; resets transferred entries to pending",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.dry_run or args.apply or args.verify or args.backfill_db):
        args.dry_run = True
    return run(args, get_settings())


if __name__ == "__main__":
    sys.exit(main())
