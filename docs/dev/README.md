# Study Assistant — developer guide

Study Assistant is a local-first, AI-powered study workbench: a FastAPI
(Python 3.12+) backend plus a React 19 SPA, shipped as a pywebview desktop app
and as a browser/Docker web app from the same codebase. Materials, extractions,
study data and the SQLite database stay on the machine; the only traffic that
leaves is the AI calls the user configures.

Read this page for the map, then jump into the page you need. The
[architecture overview](architecture.md) is the canonical deep dive, and the
[repository `AGENTS.md`](https://github.com/neuronection/study-assistant/blob/main/AGENTS.md)
is the authoritative rule list. If you only want to *use* the app, read the
[user guide](../user/README.md) instead.

## Where to start

| If you are… | Read |
|---|---|
| New to the codebase | [architecture.md](architecture.md), then [development.md](development.md) |
| Setting up and running it locally | [development.md](development.md) |
| Writing or fixing tests | [testing.md](testing.md) |
| Changing the database schema | [data-model.md](data-model.md) and [migrations.md](migrations.md) |
| Adding or changing an endpoint | [api.md](api.md) |
| Touching anything under `backend/app/ai/` | [ai.md](ai.md) |
| Working on grading or the math trust layer | [math-verification.md](math-verification.md) |
| Working on background work or schedulers | [jobs.md](jobs.md) |
| Building UI | [frontend.md](frontend.md) and [ui-conventions.md](ui-conventions.md) |
| Thinking about secrets or the trust boundary | [security.md](security.md) |
| Importing or exporting data | [import-export.md](import-export.md) |
| Deploying or packaging | [deployment.md](deployment.md), [desktop-packaging.md](desktop-packaging.md) |
| Adding a feature end-to-end | [adding-features.md](adding-features.md) |

## The pages

| Page | Covers |
|---|---|
| [architecture.md](architecture.md) | Runtime topology, backend and frontend layout, startup, storage, security posture |
| [development.md](development.md) | Prerequisites, bootstrap, run modes, commands, worktrees, verification gates |
| [testing.md](testing.md) | pytest (xdist, fixtures, isolated keyring), vitest, Playwright e2e, golden evals |
| [visual-tour.md](visual-tour.md) | Regenerating the README GIF, screenshot gallery and tour manifest from the demo instance |
| [data-model.md](data-model.md) | SQLite schema as built: entity map, scoping, tables, derived structures, migration notes |
| [api.md](api.md) | The `/api/v1` REST surface, profile scoping, errors, pagination, WebSocket, OpenAPI |
| [ai.md](ai.md) | Gateway-only model access, tasks and capabilities, providers, chat engine, tools, skills, MCP |
| [math-verification.md](math-verification.md) | The deterministic equivalence chain and the hint-leak guard |
| [import-export.md](import-export.md) | The `saq/v1`, `sa-course/v2` and `sa-skills/v1` interchange formats |
| [jobs.md](jobs.md) | The durable job runner, job types, retries, cancellation and the schedulers |
| [frontend.md](frontend.md) | React 19 + Vite SPA: routing, state, the typed API client, assistant-ui, i18n |
| [ui-conventions.md](ui-conventions.md) | Component placement, design tokens, the workspace pattern, motion, a11y, testability |
| [security.md](security.md) | Keyring secrets, the AI trust boundary, upload and blob guards, test isolation |
| [migrations.md](migrations.md) | Alembic discipline: sequential ids, model-first changes, tested downgrades |
| [deployment.md](deployment.md) | The standalone Docker stack, nginx, TLS, volumes, upgrades and backups |
| [desktop-packaging.md](desktop-packaging.md) | The PyInstaller build, deb/AppImage/Windows packaging and the release workflow |
| [adding-features.md](adding-features.md) | End-to-end recipes for the common change types |

## Ground rules (short version)

1. **Docs ship with the code.** A behavior, schema, API or UI change updates its
   page under `docs/` and `docs/STATUS.md` in the same commit; user-visible
   changes add a `## [Unreleased]` entry to
   [`CHANGELOG.md`](https://github.com/neuronection/study-assistant/blob/main/CHANGELOG.md)
   (CI-enforced by `scripts/check-changelog.sh`).
2. **Typed vocabularies.** Closed sets come from the StrEnums in
   `backend/app/core/vocab.py`; frontend request/response types are generated
   from the OpenAPI schema (`pnpm api:types`). Never introduce a new
   bare-string vocabulary.
3. **AI only through the gateway.** Every model call goes through the LangChain
   gateway in `backend/app/ai/` — no provider SDKs in app code. Model output is
   untrusted until validated. See [ai.md](ai.md).
4. **Keep both modes working.** Desktop (pywebview) and browser/Docker serve the
   same backend and SPA. The backend must not assume a window exists.
5. **Local-first, honest states.** SQLite is the source of truth; nothing is
   documented as shipped until it is. Prefer an honest empty/error state over a
   guessed one.
6. **No comments in code** unless they explain a non-obvious decision; mimic the
   existing style. Ruff + mypy strict (backend), ESLint + vitest (frontend).

The tracked [`CONTRIBUTING.md`](https://github.com/neuronection/study-assistant/blob/main/CONTRIBUTING.md)
covers the contributor-facing setup and PR flow. Planning docs (plans,
roadmap, ADRs) live outside this repository — there is no repo-root `dev/`
directory, so `docs/dev/` is the only `dev/` here.
