# -*- mode: python ; coding: utf-8 -*-
# PyInstaller >= 6 spec. Build from repo root:
#   pnpm --filter frontend build
#   uv run --directory backend pyinstaller --clean --noconfirm packaging/studyassistant.spec
#
# Env overrides:
#   SA_ONEFILE=1|0  single-file exe (default: 1 on Windows/macOS, 0 on Linux)
#   SA_CONSOLE=1    keep a console attached (debugging)
import glob
import os
import platform
import re

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

SPEC_DIR = SPECPATH
ROOT = os.path.dirname(SPEC_DIR)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
ONEFILE = os.environ.get("SA_ONEFILE", "1" if (IS_WINDOWS or IS_MACOS) else "0") == "1"
CONSOLE = os.environ.get("SA_CONSOLE", "0") == "1"

with open(os.path.join(ROOT, "backend", "app", "__init__.py"), encoding="utf-8") as fh:
    APP_VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', fh.read()).group(1)

FRONTEND_DIST = os.path.join(ROOT, "frontend", "dist")
if not os.path.isfile(os.path.join(FRONTEND_DIST, "index.html")):
    raise SystemExit("frontend/dist/index.html missing — run `pnpm --filter frontend build` first")

ENTRY = os.path.join(ROOT, "backend", "studyassistant", "__main__.py")
RUNTIME_HOOK = os.path.join(SPEC_DIR, "runtime_hook.py")

hiddenimports = [
    "fitz",
    "pymupdf",
    *collect_submodules("sqlite_vec"),
]
GI_REPOSITORIES = ["GLib", "GObject", "Gio", "Gdk", "Gtk", "Pango", "cairo", "WebKit2"]
if IS_LINUX:
    hiddenimports += [
        "webview.platforms.gtk",
        *[f"gi.repository.{ns}" for ns in GI_REPOSITORIES],
    ]
elif IS_WINDOWS:
    hiddenimports += [
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "webview.platforms.win32",
    ]
elif IS_MACOS:
    hiddenimports += ["webview.platforms.cocoa"]

datas = [
    (FRONTEND_DIST, "frontend/dist"),
    (os.path.join(ROOT, "backend", "alembic"), "alembic"),
    (os.path.join(ROOT, "backend", "alembic.ini"), "."),
]
datas += collect_data_files("webview")
binaries = collect_dynamic_libs("sqlite_vec")

if IS_LINUX:
    hiddenimports += collect_submodules("gi.overrides")
    typelib_dirs = [
        d
        for d in os.environ.get("GI_TYPELIB_PATH", "").split(":")
        if d and os.path.isdir(d)
    ]
    for pattern in ("/usr/lib/*/girepository-1.0", "/usr/lib64/girepository-1.0", "/usr/lib/girepository-1.0"):
        typelib_dirs += [d for d in glob.glob(pattern) if os.path.isdir(d)]
    seen = set()
    for d in typelib_dirs:
        for name in sorted(os.listdir(d)):
            if name.endswith(".typelib") and name not in seen:
                seen.add(name)
                datas.append((os.path.join(d, name), "gi_typelibs"))
    schema_dir = "/usr/share/glib-2.0/schemas"
    if os.path.isdir(schema_dir):
        for name in sorted(os.listdir(schema_dir)):
            if name.endswith(".compiled"):
                datas.append((os.path.join(schema_dir, name), "share/glib-2.0/schemas"))

a = Analysis(
    [ENTRY],
    pathex=[os.path.join(ROOT, "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[os.path.join(SPEC_DIR, "hooks")],
    runtime_hooks=[RUNTIME_HOOK],
    excludes=["tkinter", "test", "pytest", "IPython", "matplotlib", "pandas", "numpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe_kwargs = dict(
    name="StudyAssistant" if (IS_WINDOWS or IS_MACOS) else "studyassistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
    disable_windowed_traceback=False,
)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        **exe_kwargs,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        **exe_kwargs,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="studyassistant",
    )
