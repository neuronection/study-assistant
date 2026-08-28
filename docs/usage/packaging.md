# Packaging & release

Study Assistant ships as a desktop app in three formats, produced by tag-driven
CI (and reproducible locally):

| Format | Target | Self-contained? |
|---|---|---|
| `StudyAssistant-<ver>-windows-x64.exe` | Windows 10/11 | Yes (one-file; uses the system WebView2 runtime) |
| `studyassistant-<ver>_amd64.deb` | Debian 12 / Ubuntu 22.04+ / Mint 21+ (glibc ≥ 2.35) | Mostly (system GTK/WebKit/GLib via `Depends`; the GLib stack is stripped from the bundle so the system copies always win) |
| `StudyAssistant-<ver>-x86_64.AppImage` | Any x86_64 Linux with glibc ≥ 2.35 | Yes (bundles WebKitGTK) |

macOS artifacts are not produced yet (the PyInstaller spec has a macOS branch, but
there is no CI job and it has never been exercised).

## Release (CI)

Push a version tag matching the app version (currently `backend/app/__init__.py`,
`0.1.0`):

```bash
git tag v0.1.0 && git push origin v0.1.0
```

`.github/workflows/release.yml` then:

1. Runs the full test gate (backend ruff/mypy/pytest + frontend lint/typecheck/test/build).
2. On `ubuntu-22.04`: builds the onedir bundle, the `.deb`, and the `.AppImage`, and
   smoke-tests the bundle in headless web mode (`/api/v1/health`) plus a real desktop
   launch of the stripped deb stage under `xvfb` (survives 30 s = pass) — on the oldest
   supported glibc (2.35), so artifacts run everywhere newer (build-old, run-new).
   The job pins the interpreter to the distro Python 3.12 (deadsnakes) via
   `UV_PYTHON=3.12`, `UV_PYTHON_DOWNLOADS=never`, `UV_PYTHON_PREFERENCE=only-system`:
   without that, uv's discovery would pick the newest runner Python, and a libpython
   built on a newer toolchain drags its glibc floor into the bundle (this is exactly
   how the first releases ended up requiring GLIBC_2.38 from Ubuntu 24.04's
   `libpython3.12`). PyGObject is pinned `<3.51` for the same reason — 3.51+ needs
   glib ≥ 2.80, which Ubuntu 22.04 doesn't ship.
3. On `windows-latest`: builds the one-file `.exe` and smoke-tests it the same way.
4. Publishes a GitHub release (draft) with all three artifacts and generated notes.

The tag/version check fails the build if the tag does not match `app.__version__`.

## First release checklist

The version lives in one place: `backend/app/__init__.py` (`__version__`, read by
hatch, the frozen binary, the `.deb`, and the release workflow's tag check).
`scripts/version_manager.py` automates everything around it (same CLI as
Health-Assistant's manager: `show` / `set` / `bump` / `release`, `--git` /
`--push`).

1. **Bump, commit, and tag** in one step (the script refuses to run with
   unrelated dirty files):

   ```bash
   python3 scripts/version_manager.py bump minor --git --push
   # or: set 0.2.0 --git --push, or bump patch --git now and release --push later
   ```

2. **Watch the "Release" workflow** (Actions tab): test gate → `linux` job →
   `windows` job → `release` job. A failed job means no release; fix, delete
   the tag (`git push origin :v0.2.0 && git tag -d v0.2.0`), and re-run
   `release --push`.
3. **Verify the draft release**: three assets with the expected names
   (`…-windows-x64.exe`, `…_amd64.deb`, `…-x86_64.AppImage`), generated notes.
4. **Install-test on a clean machine** (or VM): `sudo apt install ./….deb` →
   launcher in the app menu; `chmod +x …AppImage && ./….AppImage`; run the
   `.exe`. Verify data dir creation on first launch and the window state
   feature.
5. **Publish the release** (edit the draft on GitHub, add known issues, publish).

## Expected build warnings

```
WARNING: Failed to query GI module Gio 2.0: … ValueError: Namespace GIRepository not available
```

This (and the same for GObject/cairo/Pango/GLib/Gtk/Gdk) is expected when
building with the pygobject manylinux wheel: the wheel's girepository only sees
its own typelibs, so PyInstaller's GI namespace hooks cannot introspect and
no-op. The spec compensates explicitly — `gi.overrides` submodules as
hiddenimports, system typelibs into `gi_typelibs/`, schemas into
`share/glib-2.0/schemas/`, custom `hook-gi.repository.WebKit2.py` — so these
warnings are harmless. Sanity checks for a good build: the log shows
`Analyzing hidden import 'gi.overrides.GLib'` (and the other overrides), and
the finished bundle contains `gi_typelibs/`. Do not "fix" the warning by
pointing `GI_TYPELIB_PATH` at the system during the build — that wakes the
hooks up and pulls a full system GTK stack into the bundle.

## Known gaps

- **Windows path has never run** — the `.exe` job was authored but only a tag
  push exercises it; expect the first run to surface bundling issues
  (pythonnet/WebView2 hooks). The job's smoke test exists to catch exactly that.
- **No code signing** — Windows SmartScreen will warn on unsigned binaries;
  macOS Gatekeeper would too (no macOS artifacts exist yet).
- **No auto-update** — releases are manual downloads; no update channel
  configured.
- **Linux artifacts are glibc-floor-bound by the build runner** — built on
  `ubuntu-22.04` (glibc 2.35) with the distro Python 3.12, so the `.deb` and the
  `.AppImage` need glibc ≥ 2.35 (Ubuntu 22.04+/Mint 21+/Debian 12+); WebKitGTK
  itself is bundled in the AppImage, GL/driver stacks are not. Keep the build
  runner the *oldest* supported distro — bumping it silently raises the floor
  (uv + PyInstaller bundle whatever `libpython` the build environment provides).
  If GitHub retires the `ubuntu-22.04` runner image, switch the job to a pinned
  `container: ubuntu:22.04` instead of a newer image.
- **PyGObject is pinned `>=3.50,<3.51`** — 3.51.0 switched to girepository-2.0
  and requires glib ≥ 2.80 (Ubuntu 24.04+), which would force the Linux build
  floor up to glibc 2.39. Revisit only together with the runner (both must move
  at once), and update `docs/usage/packaging.md` + the workflow assertions in
  `backend/tests/test_packaging_assets.py` in the same commit.
- **Draft releases are manual** — the workflow creates a draft; publishing is a
  human step.
- **Version bump is a manual command** — the workflow verifies tag/version
  agreement but never bumps anything itself; `scripts/version_manager.py bump
  … --git --push` is the intended driver.


## Local builds (Linux)

Prerequisites: `pnpm`, `uv`, `dpkg-deb`, and optionally `appimagetool` on `PATH`
(download from https://github.com/AppImage/appimagetool/releases and make it
executable, or point `APPIMAGETOOL=` at it). Linux dependency setup also needs
the GTK/GI build headers (PyGObject compiles from source, pinned `<3.51`):

```bash
sudo apt install -y libgirepository1.0-dev libcairo2-dev pkg-config
```

```bash
# from repo root
packaging/build-linux.sh all      # bundle + .deb + .AppImage
packaging/build-linux.sh bundle   # only backend/dist/studyassistant (onedir)
packaging/build-linux.sh deb      # bundle + .deb
packaging/build-linux.sh appimage # bundle + .AppImage
packaging/build-linux.sh deb 0.2.0   # explicit version (defaults to app.__version__)
```

The script builds `frontend/dist` if missing, runs PyInstaller with
`packaging/studyassistant.spec`, then assembles the target. Outputs land in
`packaging/` (gitignored). The flow is two-stage: PyInstaller writes the raw
bundle to `backend/dist/` (an intermediate input), and the installers assembled
from it are written to `packaging/` — only those are release artifacts.

## Windows builds

The `.exe` is built in CI only (no Windows machine required):

```bash
SA_ONEFILE=1 uv run --directory backend pyinstaller --clean --noconfirm ../packaging/studyassistant.spec
```

(The spec path is relative to `backend/` because `--directory` changes the
working directory.) One-file binaries unpack to a temp dir at every launch, so
first start is noticeably slower than the Linux onedir builds; the tradeoff is
a single portable file.

`SA_CONSOLE=1` keeps a console attached for debugging (all platforms).

## How it works

- `packaging/studyassistant.spec` bundles the Python app (entry:
  `studyassistant/__main__.py`, so `web`/`reset`/`mcp` modes work in frozen
  builds), the built SPA (`frontend/dist`), the Alembic migrations, sqlite-vec's
  native `vec0.so`, and the pywebview backend for the build platform. Linux builds
  additionally bundle the full gobject-introspection typelib set and compiled glib
  schemas.
- `packaging/runtime_hook.py` runs first in frozen builds: it redirects the
  windowed-mode stdout/stderr to a temp log (`$TMPDIR/studyassistant.log`),
  points `GI_TYPELIB_PATH` at the bundled typelibs (`gi_typelibs`) and
  `GSETTINGS_SCHEMA_DIR` at the bundled schemas (`share/glib-2.0/schemas`).
- `packaging/studyassistant.spec` also bundles `gi.overrides.*` explicitly —
  PyInstaller misses them (nothing imports them statically) and without them
  the frozen app uses raw GI bindings, which broke pywebview's opacity fade-in
  (`TypeError: Must be number, not method` → permanent white window). A custom
  hook (`packaging/hooks/hook-gi.repository.WebKit2.py`) plus explicit
  `gi.repository.*` hiddenimports keep the GI stack intact; PyInstaller's own
  namespace hooks no-op in wheel-only build environments.
- The `.deb` installs to `/usr/lib/studyassistant` with a `/usr/bin/studyassistant`
  launcher, a `.desktop` file, and an icon. Target systems need GTK3, WebKitGTK 4.1
  and the GLib runtime (`Depends: libgtk-3-0, libwebkit2gtk-4.1-0, libglib2.0-0,
  libgirepository-1.0-1`). PyInstaller collects the builder's whole GTK stack into
  the onedir tree; the deb stage **strips the GLib core** (`libglib-2.0`,
  `libgobject-2.0`, `libgio-2.0`, `libgmodule-2.0`, `libgirepository-1.0`) so the
  system copies always win — a bundled stale glib shadows the system one (PyInstaller
  prepends `_internal` to `LD_LIBRARY_PATH`) and then system libraries built against
  a newer glib fail to load (Mint 22: `libgudev … undefined symbol:
  g_once_init_enter_pointer` → WebKitGTK dlopen fails at launch).
- The `.AppImage` is fully self-contained: `build-linux.sh` copies the ldd closure
  of every bundled `.so` plus WebKitGTK/GTK (which are only dlopened, so they are
  seeded explicitly), gdk-pixbuf loaders with a rebuilt cache, and an `AppRun` that
  wires the env vars.

## Notes

- **Desktop shell picks the WebKitGTK render path at runtime** — before pywebview
  starts, a ~50 ms ctypes probe (`eglGetDisplay` + `eglInitialize`) decides: EGL
  healthy → GPU/DMABUF compositing stays on (accelerated drawing, battery-friendly);
  probe fails → `WEBKIT_DISABLE_DMABUF_RENDERER=1` +
  `WEBKIT_DISABLE_COMPOSITING_MODE=1` are set (software rasterizer) before the
  window opens. The probe can pass while WebKit's DMABUF/GBM path still fails, and
  on some stacks the disable vars don't prevent a dead GPU process — so a
  **painted-frame sentinel** is the ground truth in *every* mode: after the SPA's
  first rendered frame it fires a double-`requestAnimationFrame` beacon to `POST
  /api/v1/shell/rendered` (rAF never fires when the compositor is dead). No beacon
  within 10 s → bounded fallback ladder: relaunch once in software mode; still no
  beacon → relaunch into `web` browser mode (system browser, always renders).
  Startup logs `webkit_render_mode` so remote diagnosis reads the chosen path.
  `SA_WEBKIT_GPU=1` forces the GPU path with no probe and no sentinel
  (expert/debug).
- The app finds its bundled SPA under `sys._MEIPASS/frontend/dist` when frozen; it
  never writes user data into the install location. Data dirs are platform-aware:
  Linux `~/.local/share/StudyAssistant` (or `$XDG_DATA_HOME`), Windows
  `%APPDATA%\StudyAssistant`, macOS `~/Library/Application Support/StudyAssistant`.
- The desktop shell is pywebview over the system WebView (WebKitGTK / WebView2 /
  WKWebView) — no bundled browser. `python -m studyassistant web` remains the
  browser-first fallback on systems with broken WebKitGTK.
- The bundle respects the `mcp` and `reset` subcommands of `python -m
  studyassistant` (`StudyAssistant.exe mcp`, `studyassistant reset`).
