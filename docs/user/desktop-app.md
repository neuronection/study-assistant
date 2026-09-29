# Desktop app

Study Assistant ships as a native desktop application as well as a browser app.
The desktop app is a pywebview window (WebKitGTK on Linux, WebView2 on Windows)
wrapping the exact same local backend and SPA — no separate code path, no
separate data. This page explains how to launch it and how it differs from the
browser modes. For the underlying packaging and release process, see the
[developer packaging guide](../dev/desktop-packaging.md).

## Launching

- **From an installer** — install the Linux `.deb`/`.AppImage` or the Windows
  `.exe` from the
  [Releases](https://github.com/neuronection/study-assistant/releases) page and
  start it like any other app.
- **From source** — `pnpm app` builds the SPA if needed and opens the desktop
  window. `python -m studyassistant` does the same once the frontend is built.

The backend runs on a free loopback port chosen at launch; the window loads it
from `127.0.0.1`. Nothing is exposed to the network.

## What the desktop shell adds

- **A native window** that remembers its size, position and maximized state
  between launches (stored in the data directory).
- **Native file and folder picking.** WebKitGTK cannot pick directories through
  the browser's `<input webkitdirectory>`, so the shell exposes a small
  JavaScript bridge: the **Upload folder…** action opens the operating system's
  folder chooser and reads the files through a root-contained desktop API. On
  Windows the browser-style picker is used where it works.
- **Environment sanitization.** Launching from a sandboxed terminal (for
  example the VS Code snap) can pollute library paths; the shell strips those
  variables before starting so the app finds its own libraries.
- **A render-path safety net on Linux.** WebKitGTK's GPU/DMABUF path fails on
  some drivers, so the shell detects a blank render and retries with software
  rendering, remembering the choice. The **Developer** settings tab has a check
  for this engine.

## Browser-first fallback

The browser modes are the most exercised path and the recommended fallback if
the desktop window misbehaves on a particular machine:

```bash
pnpm webapp     # serve the built app and open your default browser
pnpm dev        # hot-reload dev servers
```

Both serve the same backend and data directory, so you can switch between the
desktop window and the browser freely. If the desktop window shows a blank
screen, use `pnpm webapp` and see [Troubleshooting](troubleshooting.md); the
[known-issues section of STATUS.md](../STATUS.md) records the current state.

## What is the same everywhere

- Your data directory, database, blobs and backups are identical across modes.
- API keys live in the operating system keyring, not in the app window.
- Backups, jobs and schedulers run in the backend regardless of which shell is
  displaying the UI.
