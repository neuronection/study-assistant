# Contributing to Study Assistant

Thanks for your interest in contributing! Study Assistant is a local-first,
AI-powered study workbench: Python (FastAPI) backend + React SPA, desktop
(pywebview) and browser modes.

## Setting up a development environment

Prerequisites: **Python 3.12+** with [uv](https://docs.astral.sh/uv/),
**Node 20+** with pnpm (`corepack enable pnpm`). On Linux, the desktop shell
needs GTK build headers:

```bash
sudo apt install libgirepository-2.0-dev libcairo2-dev
```

```bash
git clone https://github.com/neuronection/study-assistant.git
cd study-assistant
uv sync                                   # backend venv (repo root)
corepack enable pnpm && pnpm install      # frontend
pnpm webapp                               # build + serve + open http://127.0.0.1:8000
```

See the [Quick start](README.md#quick-start) section of the README for all
run modes (desktop, browser, Docker).

## The verification suite

Every commit must pass the full gate — CI mirrors it:

```bash
pnpm verify:backend                       # ruff + mypy + pytest   (backend/)
pnpm verify:frontend                      # eslint + tsc + vitest + build (frontend/)
```

If a suite is red, fix it before committing. If tests are missing for new
behavior, add them in the same commit.

## House rules

- **Docs are part of the change.** Code changes that alter behavior,
  architecture, schema, or APIs update `docs/STATUS.md` (and the relevant
  doc under `docs/`) in the same commit. CI enforces the CHANGELOG half via
  `scripts/check-changelog.sh`: user-visible changes need a
  `## [Unreleased]` entry.
- **Typed vocabularies.** Closed sets of values come from the StrEnums in
  `backend/app/core/vocab.py` — never introduce new bare-string
  vocabularies. Frontend request/response types are generated from the
  OpenAPI schema (`pnpm api:types`); hand-write types only for
  client-side-only shapes.
- **Placement conventions.** API-client functions in
  `frontend/src/lib/api/<domain>.ts`, backend services in
  `backend/app/services/<group>/`, models in
  `backend/app/domain/models/<domain>.py`.
- **No comments in code** unless the change truly needs one; mimic the
  existing style.
- **Never commit secrets.** API keys live in the OS keyring (configured in
  the app's Settings UI), never in files, env blocks, or the database.
- **Schema changes** (SQLAlchemy/Alembic) are model-first with a tested
  downgrade and a single linear revision chain — see the Migration notes in
  [`docs/data-model.md`](docs/data-model.md).

## UI components

`@neuronection/assistant-ui` is the project's first-party React component
library (published on npm). `frontend/src/components/ui/*` are re-export
shims — don't re-implement library components locally; propose the change
upstream and adopt the new release.

## Pull requests

1. Fork / branch from `main`.
2. Make the change with tests and docs (above).
3. Run the full verification suite.
4. Add a `## [Unreleased]` CHANGELOG entry for user-visible changes.
5. Open the PR — CI runs the gate plus the changelog check.

## Reporting issues

Bug reports and feature requests use the issue templates
(`.github/ISSUE_TEMPLATE/`). Security issues: please follow
[`SECURITY.md`](SECURITY.md) and report privately.
