"""migrate-objects for study: copy the legacy blob tree through the store.

No cloud credentials are involved: every test builds a local store in a temp
root, exactly like a self-host maintenance window. The CLI must be idempotent
and resumable, refuse a live target prefix without ``--force``, and never
print an absolute source path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from settings_factory import settings_from_env_file

from app.core.config import Settings

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_objects.py"


def _load_cli() -> Any:
    spec = importlib.util.spec_from_file_location("study_migrate_objects", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


def _settings(tmp_path: Path) -> Settings:
    return settings_from_env_file(
        None,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        identity_mode=None,
        object_storage_local_root=tmp_path / "target",
    )


def _blob(root: Path, data: bytes) -> str:
    sha = hashlib.sha256(data).hexdigest()
    path = root / sha[:2] / sha[2:4] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha


def _args(
    manifest: Path,
    *,
    dry_run: bool = False,
    apply: bool = False,
    verify: bool = False,
    backfill: bool = False,
    force: bool = False,
    rebind: bool = False,
) -> argparse.Namespace:
    parsed: argparse.Namespace = cli.build_parser().parse_args(
        [
            *(["--dry-run"] if dry_run else []),
            *(["--apply"] if apply else []),
            *(["--verify"] if verify else []),
            *(["--backfill-db"] if backfill else []),
            *(["--force"] if force else []),
            *(["--rebind"] if rebind else []),
            "--manifest",
            str(manifest),
        ]
    )
    return parsed


def test_dry_run_reports_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings(tmp_path)
    sha = _blob(Path(settings.blobs_dir), b"hello blob")
    manifest = tmp_path / "manifest.json"

    assert cli.run(_args(manifest, dry_run=True), settings) == 0
    output = capsys.readouterr().out
    assert "would copy 1 object" in output
    assert not manifest.exists()
    assert not (tmp_path / "target" / sha[:2]).exists()
    assert str(settings.blobs_dir) not in output


def test_apply_verify_and_resume(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sha = _blob(Path(settings.blobs_dir), b"hello blob")
    other = _blob(Path(settings.blobs_dir), b"second blob")
    manifest = tmp_path / "manifest.json"

    assert cli.run(_args(manifest, apply=True), settings) == 0
    for digest, payload in ((sha, b"hello blob"), (other, b"second blob")):
        assert (tmp_path / "target" / digest[:2] / digest[2:4] / digest).read_bytes() == payload

    saved = json.loads(manifest.read_text())
    assert saved["host"] == "study-assistant"
    assert {entry["status"] for entry in saved["entries"]} == {"copied"}

    assert cli.run(_args(manifest, apply=True), settings) == 0
    assert cli.run(_args(manifest, verify=True), settings) == 0
    assert {entry["status"] for entry in json.loads(manifest.read_text())["entries"]} == {
        "verified"
    }


def test_content_addressed_mismatch_is_not_copied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings(tmp_path)
    root = Path(settings.blobs_dir)
    wrong = root / "aa" / "bb" / ("0" * 64)
    wrong.parent.mkdir(parents=True, exist_ok=True)
    wrong.write_bytes(b"not the digest in its key")
    manifest = tmp_path / "manifest.json"

    assert cli.run(_args(manifest, apply=True), settings) == 1
    output = capsys.readouterr().out
    assert "unreadable" in output
    assert "content-addressed" in output
    assert not (tmp_path / "target" / "aa").exists()


def test_non_empty_target_refuses_until_forced(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _blob(Path(settings.blobs_dir), b"payload")
    target = tmp_path / "target"
    target.mkdir(parents=True)
    (target / "foreign.bin").write_bytes(b"live data")
    manifest = tmp_path / "manifest.json"

    with pytest.raises(SystemExit, match="Refusing"):
        cli.run(_args(manifest, apply=True), settings)
    assert cli.run(_args(manifest, apply=True, force=True), settings) == 0


def test_corrupt_manifest_fails_loud_until_forced(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _blob(Path(settings.blobs_dir), b"payload")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{broken", encoding="utf-8")

    with pytest.raises(SystemExit, match="corrupt manifest"):
        cli.run(_args(manifest, apply=True), settings)
    assert cli.run(_args(manifest, apply=True, force=True), settings) == 0
    assert json.loads(manifest.read_text())["version"] == "object-storage-migration/1"


def test_backfill_is_a_noop_but_requires_verify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings(tmp_path)
    _blob(Path(settings.blobs_dir), b"payload")
    manifest = tmp_path / "manifest.json"

    with pytest.raises(SystemExit, match="no manifest"):
        cli.run(_args(manifest, backfill=True), settings)
    assert cli.run(_args(manifest, apply=True), settings) == 0
    with pytest.raises(SystemExit, match="Run --verify first"):
        cli.run(_args(manifest, backfill=True), settings)
    assert cli.run(_args(manifest, verify=True), settings) == 0
    assert cli.run(_args(manifest, backfill=True), settings) == 0
    assert "no database backfill" in capsys.readouterr().out


def test_dry_run_warns_but_does_not_block_on_non_empty_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings(tmp_path)
    _blob(Path(settings.blobs_dir), b"payload")
    target = tmp_path / "target"
    target.mkdir(parents=True)
    (target / "foreign.bin").write_bytes(b"live data")

    assert cli.run(_args(tmp_path / "manifest.json", dry_run=True), settings) == 0
    output = capsys.readouterr().out
    assert "warning: target prefix has 1 foreign" in output
    assert "--force" in output


def test_wrong_target_is_refused_and_rebind_recovers(tmp_path: Path) -> None:
    settings_a = _settings(tmp_path)
    _blob(Path(settings_a.blobs_dir), b"payload")
    manifest = tmp_path / "manifest.json"
    assert cli.run(_args(manifest, apply=True), settings_a) == 0

    settings_b = settings_a.model_copy(update={"object_storage_local_root": tmp_path / "target-b"})
    with pytest.raises(SystemExit, match="manifest target does not match"):
        cli.run(_args(manifest, apply=True), settings_b)
    with pytest.raises(SystemExit, match="manifest target does not match"):
        cli.run(_args(manifest, backfill=True), settings_b)
    with pytest.raises(SystemExit, match="manifest target does not match"):
        cli.run(_args(manifest, verify=True), settings_b)
    assert cli.run(_args(manifest, apply=True, rebind=True), settings_b) == 0
    assert (tmp_path / "target-b").exists()
    assert cli.run(_args(manifest, verify=True), settings_b) == 0


def test_nested_source_and_target_roots_are_refused(tmp_path: Path) -> None:
    settings = settings_from_env_file(
        None,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        identity_mode=None,
        object_storage_local_root=tmp_path / "data" / "blobs" / "nested",
    )
    _blob(Path(settings.blobs_dir), b"payload")
    with pytest.raises(SystemExit, match="nested"):
        cli.run(_args(tmp_path / "manifest.json", apply=True), settings)


def test_verify_blocks_a_missing_target_object(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = _blob(Path(settings.blobs_dir), b"first")
    _blob(Path(settings.blobs_dir), b"second")
    manifest = tmp_path / "manifest.json"
    assert cli.run(_args(manifest, apply=True), settings) == 0
    (tmp_path / "target" / first[:2] / first[2:4] / first).unlink()
    assert cli.run(_args(manifest, verify=True), settings) == 1


def test_symlinks_are_never_copied(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    root = Path(settings.blobs_dir)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    sha = hashlib.sha256(outside.read_bytes()).hexdigest()
    link = root / sha[:2] / sha[2:4] / sha
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)
    manifest = tmp_path / "manifest.json"

    assert cli.run(_args(manifest, apply=True), settings) == 1
    assert not (tmp_path / "target" / sha[:2] / sha[2:4] / sha).exists()


def test_desktop_refuses_to_migrate(tmp_path: Path) -> None:
    settings = settings_from_env_file(
        None,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        identity_mode="desktop",
    )
    with pytest.raises(SystemExit, match="desktop is local-only"):
        cli.run(_args(tmp_path / "manifest.json", dry_run=True), settings)


def test_same_local_root_is_refused(tmp_path: Path) -> None:
    settings = settings_from_env_file(
        None,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        identity_mode=None,
        object_storage_local_root=tmp_path / "data" / "blobs",
    )
    _blob(Path(settings.blobs_dir), b"payload")
    with pytest.raises(SystemExit, match="same local root"):
        cli.run(_args(tmp_path / "manifest.json", apply=True), settings)
