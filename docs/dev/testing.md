# Testing

Study Assistant has three test layers: **pytest** for the backend, **vitest**
for the frontend, and **Playwright** for a small end-to-end smoke suite against
a real backend. A golden-eval directory covers the AI quiz generator. This page
describes how each layer is set up and the isolation rules that keep tests fast
and offline. The gate itself is listed in [development.md](development.md).

## Backend — pytest

Configuration lives in `backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-n auto"
```

Tests run in parallel with `pytest-xdist`. Run them with
`pnpm verify:backend` (or `uv run --directory backend pytest`).

### Isolation guarantees (`tests/conftest.py`)

These are load-bearing — do not weaken them:

- **In-memory keyring.** `conftest.py` installs a `TestKeyring` backend before
  any test imports the app, so tests never touch the real OS keyring. New secret
  reads/writes must go through `app/core/secrets.py`, which this isolates.
- **No network.** A session-scoped autouse fixture replaces
  `socket.connect`/`create_connection` with a function that raises. Any test that
  needs HTTP must inject an `httpx` transport (a mock or `ASGITransport`); a
  real connection is a hard failure.
- **Fast migrations.** A session fixture builds a migrated SQLite template once
  (`migrated_db_template`), and an autouse fixture copies it for each fresh test
  database instead of re-running Alembic. The real migration path still runs
  when a database already exists.
- **Structlog to stdlib** at `WARNING` so test output stays readable.
- **Native-tools degradation reset** between tests (chat function-calling
  fallback state is process-global).

### Fixtures

| Fixture | Gives you |
|---|---|
| `client` | A `fastapi.testclient.TestClient` over `create_app` with a `tmp_path` data dir and no SPA — the normal way to test API endpoints |
| `db_session` | A `Session` over a fresh migrated database copied from the template — for service-level tests |
| `migrated_db_template` | The shared migrated database file (session-scoped) |

### Layout

`backend/tests/` holds one `test_<area>.py` per feature area (chat, proposals,
courses, materials, grading, migrations, packaging assets, …), plus:

- `tests/evals/` — the golden quiz-generation eval (`test_quizgen_golden.py`
  with fixtures under `golden/`). These pin generator output shape and quality
  signals; run them when touching `pipelines/quizgen`.
- `tests/fixtures/` — sample documents and binaries used by ingestion tests.

Migration changes come with a round-trip test (upgrade → downgrade) — see
[migrations.md](migrations.md).

## Frontend — vitest

`pnpm --filter frontend test` runs vitest in a jsdom environment. Component and
store tests live beside their source as `*.test.ts(x)`. Shared helpers live in
`frontend/src/test/`. `pnpm verify:frontend` chains `lint`, `typecheck`, `test`
and `build`.

Two frontend checks are separate on purpose:

- **i18n:** `pnpm --filter frontend i18n` runs
  `scripts/translations/check_translations.py` and fails on missing or unused
  keys. An ESLint rule also errors on hardcoded user-facing strings.
- **Types:** `pnpm --filter frontend typecheck` runs `tsc --noEmit`; the API
  schema drift is a separate `api:types` step (see [frontend.md](frontend.md)).

## End-to-end — Playwright

`pnpm --filter frontend e2e` runs the specs under `frontend/e2e/` against a
real backend booted by the suite:

- `global-setup.ts` / `global-teardown.ts` and `run_backend.py` start and stop
  the app; `mock_provider.py` stands in for an AI provider so no external call
  is made; `state.ts` holds shared helpers.
- Specs are numbered by flow (`01-boot`, `02-chat`, `03-material`, `04-quiz`,
  `05-ask`, `06-tree-sidebar`). They exist to catch real-browser regressions
  that jsdom cannot see — for example the unlayered-CSS bug where a sidebar had
  zero computed size in a real build while unit tests stayed green.

Add a spec when a bug can only be reproduced in a real browser (layout, CSS
cascade, real WebSocket streaming).

## What to mock

- **AI calls** — inject a fake `httpx` transport or a stub gateway; never hit a
  provider. The chat and provider contract tests use this pattern.
- **Time** — use injected clocks/`monkeypatch`, not sleeps.
- **Filesystem** — use `tmp_path` and the `client` fixture's isolated data dir.
- **Network** — always; the session fixture forbids it.

## Honesty rule

Tests assert real behavior, not intent. A test that passes only because it mocks
the thing under test is a finding. When you fix a bug, add the regression test
in the same commit — the plan and STATUS conventions call this out explicitly.
