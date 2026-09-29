# Development workflow

This page is the local setup and day-to-day loop for working on Study
Assistant: prerequisites, the three run modes, the commands you will use, the
git-worktree protocol for concurrent agent sessions, and the verification gate
every commit must pass. For what the code is made of, read
[architecture.md](architecture.md); for the test suite itself, read
[testing.md](testing.md).

## Prerequisites

- **Python 3.12+** with [uv](https://docs.astral.sh/uv/).
- **Node 20+** with pnpm (`corepack enable pnpm`).
- On Linux the desktop shell needs GTK/WebKit build headers:

```bash
sudo apt install libgirepository-2.0-dev libcairo2-dev
```

## Bootstrap

```bash
git clone https://github.com/neuronection/study-assistant.git
cd study-assistant
uv sync                                   # backend venv (repo root)
corepack enable pnpm && pnpm install      # frontend workspace
```

`uv sync` resolves the `backend` workspace member; `pnpm install` installs the
`frontend` package plus the shared `@neuronection/assistant-ui` library.

## Run modes

| Mode | Command | What it does |
|---|---|---|
| Dev (hot reload) | `pnpm dev` | honcho runs uvicorn `--reload` (default port 8200) and the Vite dev server (default 3200) as one process group under `Procfile.dev`; Ctrl+C stops both |
| Desktop app | `pnpm app` | Builds the SPA if missing, then launches the pywebview window over it (`scripts/app.sh`) |
| Webapp | `pnpm webapp` | Builds the SPA, serves it from the backend, opens the browser (`scripts/webapp.sh`) |
| Docker | `scripts/run-docker.sh` | Self-hosted web stack — see [deployment.md](deployment.md) |

Ports are family-band slot 2: `SA_PORT` defaults to `8200`, `VITE_PORT` to
`3200`. The dev entrypoint accepts `--force` (kill port holders first),
`--force-stop`, `--reset` (wipe the local database and storage; `--yes` skips
the prompt, `--all` includes backups) and `--no-bootstrap`.

**Dev modes are `pnpm dev`-shaped** (identity-auth ADR-0022): the default
`./scripts/run-dev.sh` run is **desktop mode** — SQLite
(`<data dir>/study.sqlite3`), no login surface, the shell/exchange flow.
Add **`--web`** for **server mode**: `SA_IDENTITY_MODE=server` against
PostgreSQL 16 (`docker/docker-compose.dev-db.yml` — `neuro_study` +
`neuro_study_test` on 127.0.0.1:5434, auto-started when unreachable;
override with `SA_DATABASE_URL`). The SPA then shows the login/register
UI and the first registered user becomes admin. `--reset` is desktop-only
in web mode; reset by recreating the dev-db volume.

## Commands

| Command | Purpose |
|---|---|
| `pnpm dev:backend` | uvicorn `--reload` alone |
| `pnpm dev:frontend` | Vite dev server alone |
| `pnpm verify:backend` | `ruff check . && mypy . && pytest` in `backend/` |
| `pnpm verify:frontend` | `pnpm lint && pnpm typecheck && pnpm test && pnpm build` in `frontend/` |
| `pnpm api:types` | Regenerate `frontend/openapi.json` from the app and `src/lib/api-schema.d.ts` from it |
| `pnpm --filter frontend i18n` | Translation completeness check |
| `pnpm --filter frontend e2e` | Playwright end-to-end suite |

## The verification gate

Every commit must pass the full suite; CI mirrors it (see
[testing.md](testing.md)):

```bash
pnpm verify:backend     # ruff + mypy strict + pytest (xdist -n auto)
pnpm verify:frontend    # eslint + tsc --noEmit + vitest + vite build
```

If a suite is red, fix it before committing. New behavior needs tests in the
same commit. `scripts/check-changelog.sh` additionally fails a PR when
`backend/app` or `frontend/src` changed without a `CHANGELOG.md` entry.

## Generated artifacts

Two files are generated, never hand-edited, and drift-guarded in CI:

- `frontend/openapi.json` — the OpenAPI schema exported by
  `scripts/export-openapi.py`.
- `frontend/src/lib/api-schema.d.ts` — TypeScript types produced from that
  schema by `openapi-typescript`.

Add or change an endpoint, then run `pnpm api:types` and commit both. Hand-write
types only for client-side-only shapes.

## Conventions

- **Placement.** API-client functions in `frontend/src/lib/api/<domain>.ts`,
  backend services in `backend/app/services/<group>/`, models in
  `backend/app/domain/models/<domain>.py`. See [architecture.md](architecture.md).
- **Typed vocabularies.** Closed sets come from `backend/app/core/vocab.py`
  StrEnums; frontend mirrors them in `frontend/src/lib/constants.ts`.
- **No comments** unless they explain a non-obvious decision; mimic existing
  style.
- **Never commit secrets.** API keys live only in the OS keyring via
  `backend/app/core/secrets.py` — see [security.md](security.md).
- **Schema changes** are model-first with a tested downgrade and one linear
  Alembic chain — see [migrations.md](migrations.md).

## Concurrent sessions (git worktrees)

When multiple agent sessions or developers work in parallel, each works in its
own git worktree and branches merge back **fast-forward only**:

```bash
git worktree add ../study-assistant-<task> -b <task>
cd ../study-assistant-<task>
# bootstrap deps in the new worktree (uv sync && pnpm install)
```

Alembic revisions created on a later branch are renumbered onto the single
linear chain before merge (see [migrations.md](migrations.md)). Never commit
while wired to a local `assistant-ui` checkout (`link:` in
`pnpm-workspace.yaml`) — `scripts/check-dev-link.sh` guards this.

## Housekeeping

- `python -m studyassistant reset [--yes] [--all]` wipes the local database and
  storage (used by the `--reset` flags above).
- The data directory is `~/.local/share/StudyAssistant/` on Linux (see
  [architecture.md](architecture.md) for per-platform paths); `SA_DATA_DIR` and
  the working-directory setting can point elsewhere.
- The tracked `docs/` directory is the documentation surface; plans,
  roadmap, and the ADR register live outside this repository (there is no
  repo-root `dev/` directory).
