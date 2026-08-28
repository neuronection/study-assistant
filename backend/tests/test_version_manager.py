import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "version_manager.py"

spec = importlib.util.spec_from_file_location("version_manager", SCRIPT)
assert spec is not None and spec.loader is not None
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


def test_parse_and_format_roundtrip() -> None:
    assert vm.parse_version("1.2.3") == (1, 2, 3, None)
    assert vm.parse_version("1.2.3-rc.4") == (1, 2, 3, "rc.4")
    assert vm.format_version(1, 2, 3) == "1.2.3"
    assert vm.format_version(1, 2, 3, "rc.4") == "1.2.3-rc.4"


def test_parse_rejects_invalid() -> None:
    for bad in ("", "1", "1.2", "v1.2.3", "1.2.3.4", "a.b.c"):
        with pytest.raises(ValueError):
            vm.parse_version(bad)


def test_bump_major_minor_patch() -> None:
    assert vm.bump_version("0.1.0", "major") == "1.0.0"
    assert vm.bump_version("0.1.0", "minor") == "0.2.0"
    assert vm.bump_version("0.1.3", "patch") == "0.1.4"


def test_bump_rc_increments_and_patch_promotes() -> None:
    assert vm.bump_version("0.2.0", "rc") == "0.2.1-rc.1"
    assert vm.bump_version("0.2.1-rc.1", "rc") == "0.2.1-rc.2"
    assert vm.bump_version("0.2.1-rc.2", "patch") == "0.2.1"
    assert vm.bump_version("0.2.1-rc.2", "minor") == "0.3.0"


def test_set_version_rewrites_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    version_file = tmp_path / "__init__.py"
    version_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    monkeypatch.setattr(vm, "VERSION_FILE", version_file)
    vm.set_version("9.8.7-rc.1")
    assert version_file.read_text(encoding="utf-8") == '__version__ = "9.8.7-rc.1"\n'
    assert vm.current_version() == "9.8.7-rc.1"


def test_cli_show_prints_repo_version() -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT), "show"], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "0.1.0"


def test_set_rejects_invalid_version_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version_file = tmp_path / "__init__.py"
    version_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    monkeypatch.setattr(vm, "VERSION_FILE", version_file)
    with pytest.raises(ValueError):
        vm.set_version("not-semver")
    assert version_file.read_text(encoding="utf-8") == '__version__ = "0.1.0"\n'
