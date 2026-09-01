import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "version_manager.py"

spec = importlib.util.spec_from_file_location("version_manager", SCRIPT)
assert spec is not None and spec.loader is not None
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

TEST_CONFIG = """\
[project]
name = "Test App"

[version]
file = "backend/app/__init__.py"
pattern = '__version__\\s*=\\s*"(?P<version>[^"]+)"'

[release]
tag_prefix = "v"
commit_message = "chore(release): {version}"
"""


def _make_repo(tmp_path: Path, init_git: bool = False) -> Path:
    repo = tmp_path / "repo"
    version_dir = repo / "backend" / "app"
    version_dir.mkdir(parents=True)
    (version_dir / "__init__.py").write_text(
        '__version__ = "0.1.1"\n', encoding="utf-8"
    )
    (repo / "version_manager.toml").write_text(TEST_CONFIG, encoding="utf-8")
    if init_git:
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test")
        _git(repo, "config", "commit.gpgsign", "false")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "init")
    return repo


def _patch_vm(monkeypatch: pytest.MonkeyPatch, repo: Path) -> None:
    monkeypatch.setattr(vm, "ROOT", repo)
    monkeypatch.setattr(vm, "CONFIG_PATH", repo / "version_manager.toml")


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


def test_set_command_rewrites_version_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _make_repo(tmp_path)
    _patch_vm(monkeypatch, repo)
    monkeypatch.setattr(sys, "argv", ["version_manager.py", "set", "9.8.7-rc.1"])
    vm.main()
    version_file = repo / "backend" / "app" / "__init__.py"
    assert version_file.read_text(encoding="utf-8") == '__version__ = "9.8.7-rc.1"\n'
    assert vm.read_version(vm.load_config()) == "9.8.7-rc.1"
    assert capsys.readouterr().out.count("9.8.7-rc.1") >= 1


def test_cli_show_prints_repo_version() -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT), "show"], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert result.returncode == 0
    assert result.stdout.strip() == vm.read_version(vm.load_config())


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_release_commits_dirty_version_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path, init_git=True)
    (repo / "backend" / "app" / "__init__.py").write_text(
        '__version__ = "0.1.2"\n', encoding="utf-8"
    )
    _patch_vm(monkeypatch, repo)
    cfg = vm.load_config()
    vm.git_release(cfg, "0.1.2", push=False)
    assert _git(repo, "log", "-1", "--pretty=%s").strip() == "chore(release): 0.1.2"
    assert _git(repo, "tag").split() == ["v0.1.2"]
    assert _git(repo, "status", "--porcelain") == ""


def test_set_rejects_invalid_version_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    _patch_vm(monkeypatch, repo)
    monkeypatch.setattr(sys, "argv", ["version_manager.py", "set", "not-semver"])
    with pytest.raises(SystemExit):
        vm.main()
    version_file = repo / "backend" / "app" / "__init__.py"
    assert version_file.read_text(encoding="utf-8") == '__version__ = "0.1.1"\n'
