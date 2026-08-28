import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGING = REPO_ROOT / "packaging"


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_spec_bundles_spa_alembic_and_entry() -> None:
    spec = _read("packaging/studyassistant.spec")
    for needle in (
        '"frontend/dist"',
        '"alembic"',
        "alembic.ini",
        "studyassistant",
        "__main__.py",
        "runtime_hook.py",
        "sqlite_vec",
        "webview.platforms",
    ):
        assert needle in spec, f"spec missing {needle}"


def test_spec_referenced_paths_exist() -> None:
    assert (REPO_ROOT / "backend" / "studyassistant" / "__main__.py").is_file()
    assert (REPO_ROOT / "backend" / "alembic.ini").is_file()
    assert (REPO_ROOT / "backend" / "alembic" / "env.py").is_file()
    assert (REPO_ROOT / "backend" / "alembic" / "versions").is_dir()
    assert (PACKAGING / "runtime_hook.py").is_file()
    assert (PACKAGING / "icon.svg").is_file()


def test_runtime_hook_handles_frozen_paths() -> None:
    hook = _read("packaging/runtime_hook.py")
    for needle in ("_MEIPASS", "typelibs", "schemas", "GI_TYPELIB_PATH"):
        assert needle in hook, f"runtime hook missing {needle}"


def test_build_script_syntax_and_targets() -> None:
    script = PACKAGING / "build-linux.sh"
    assert script.is_file()
    bash = shutil.which("bash")
    assert bash is not None
    result = subprocess.run([bash, "-n", str(script)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    source = script.read_text(encoding="utf-8")
    for needle in (
        "dpkg-deb",
        "appimagetool",
        "libwebkit2gtk-4.1",
        "pyinstaller",
        "libglib2.0-0",
        "libgirepository-1.0-1",
        "Stripping bundled GLib stack",
    ):
        assert needle in source, f"build script missing {needle}"


def test_release_workflow_covers_tag_and_artifacts() -> None:
    workflow = _read(".github/workflows/release.yml")
    for needle in (
        'tags: ["v*"]',
        "ubuntu-22.04",
        "ppa:deadsnakes/ppa",
        "UV_PYTHON_DOWNLOADS",
        "UV_PYTHON_PREFERENCE",
        "libgirepository1.0-dev",
        "windows-latest",
        "build-linux.sh",
        "SA_ONEFILE",
        "*.deb",
        "*.AppImage",
        "-windows-x64.exe",
        "generate_release_notes",
        "xvfb-run",
        "WEBKIT_DISABLE_COMPOSITING_MODE",
    ):
        assert needle in workflow, f"release workflow missing {needle}"


def test_ci_workflow_installs_girepository_1_0_dev() -> None:
    workflow = _read(".github/workflows/ci.yml")
    assert "libgirepository1.0-dev" in workflow, "ci workflow missing libgirepository1.0-dev"
    assert (
        "libgirepository-2.0-dev" not in workflow
    ), "ci workflow installs girepository-2.0; pygobject 3.50 needs gobject-introspection-1.0"
    assert "uv sync --frozen" in workflow
