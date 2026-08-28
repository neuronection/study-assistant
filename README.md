# Study Assistant

[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

AI-powered, local-first desktop study workbench (Python backend + React SPA in a pywebview
window). Math-first, subject-agnostic by design. Status: see `docs/STATUS.md`.

User guides live in [`docs/usage/`](docs/usage/) — start with
[getting started](docs/usage/getting-started.md).

## System prerequisites (Linux)

The desktop shell uses pywebview with GTK + WebKitGTK, which needs PyGObject compiled
from source inside the venv:

```bash
sudo apt install libgirepository-2.0-dev libcairo2-dev
```

WebKitGTK itself ships with most desktops (`gir1.2-webkit2-4.1` — install it if missing).
On Windows/macOS no extra packages are needed (WebView2/WKWebView are used).

## Development setup

```bash
uv sync                                   # backend venv (repo root)
corepack enable pnpm && pnpm install      # frontend (node >= 20)
```

## Running the app

```bash
pnpm webapp        # webapp mode: serve the built SPA, open it in your browser
pnpm dev           # dev mode: uvicorn (reload) + Vite dev server (localhost:5173)
pnpm app           # app mode: desktop shell (pywebview/WebKitGTK) over the built SPA
```

All modes live in `scripts/` (`webapp.sh`, `dev.sh`, `app.sh`); `webapp.sh`/`app.sh`
accept `--rebuild` to force a frontend build, and `webapp.sh`/`dev.sh` accept
`--force` to kill whatever still holds the port (a leftover uvicorn from an old
session fails with "Address already in use" otherwise — the scripts name the
holder pid/commandline and tell you). `webapp` is the recommended mode — the
desktop shell currently has a rendering issue on some setups. The webapp port defaults
to 8000 (`SA_PORT` to override).

## Verification suite

```bash
pnpm verify:backend                       # ruff + mypy + pytest
pnpm verify:frontend                      # eslint + tsc + vitest + build
```

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
