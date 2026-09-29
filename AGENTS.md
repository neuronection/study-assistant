# Study Assistant — Agent Instructions

AI-powered, local-first study workbench (Python backend + React SPA) that runs
as a desktop app (pywebview window, `pnpm app`) or in the browser
(`pnpm webapp`) — both modes first-class.
Math-first (calculus), subject-agnostic by design. **`docs/STATUS.md` is the
single source of truth for what exists and what phase we are in.** Longer-range
planning documents (plans, roadmap, ADR register) live outside this
repository and are not part of it — there is no repo-root `dev/` directory.

**Identity class D** (family ADR-0013): web/server mode is always
authenticated with user management; desktop initializes `auth_mode=open`
(implicit local owner + Default profile, zero auth UI) unless explicitly
initialized as `authenticated`. Study spaces are **profiles** — 1:N per user,
owned via `users`; `X-Profile-Id` is validated against the session user (403
on mismatch, 400 when absent in web mode). Datastore (family ADR-0022):
SQLite for desktop, **PostgreSQL 16 for web/server** — supersedes
SQLite-in-Docker; the FTS5/sqlite-vec stack gains Postgres dialect twins.

## Non-negotiable rules

1. **Never commit untested code.** Run the verification suite (below) before every commit.
   If a command doesn't exist yet, that's a finding — surface it, don't skip it.
2. **Every unit of work updates documentation.** Code changes that alter behavior,
   architecture, schema, or APIs require same-commit doc updates (`docs/STATUS.md` at
   minimum). A PR that changes code but not docs is incomplete — CI enforces the
   CHANGELOG half of this on PRs (`scripts/check-changelog.sh`).
3. **Scope discipline.** Work only on the current phase (see `docs/STATUS.md`).
   Features outside the current phase need explicit approval first.
4. **Decisions before implementation.** Architecture decisions are recorded before
   they are built (see `docs/dev/architecture.md`); if a recorded decision must
   change, propose the change explicitly — don't silently contradict it.
5. **No comments in code** unless requested. Conventions: mimic existing style, ruff +
   mypy strict (backend), eslint + vitest (frontend). Typed vocabularies:
   closed sets come from `backend/app/core/vocab.py` StrEnums (never new bare-string
   vocabularies); frontend request/response types are generated from OpenAPI
   (`frontend/openapi.json` + `src/lib/api-schema.d.ts` via `pnpm api:types`, CI
   drift-guarded — new endpoints' types are born in the schema, hand types only for
   client-side shapes); placement: API-client functions in `frontend/src/lib/api/<domain>.ts`,
   services in `backend/app/services/<group>/`, models in `backend/app/domain/models/<domain>.py`.
6. **Never commit secrets.** API keys live only in the OS keyring, never in files, env
   blocks, or the DB. Tests must never touch the real OS keyring — `backend/tests/conftest.py`
   installs an in-memory keyring backend for the whole suite; keep it that way (new secret
   reads/writes go through `app/core/secrets.py`, which is isolated by that conftest).

## Verification suite (all must pass before commit)

Backend (`backend/`): `ruff check . && mypy . && pytest`
Frontend (`frontend/`): `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
(CI mirrors these.)

If any suite is red, fix it before committing. If tests are missing for new behavior,
write them first or in the same commit.

## Where things are

| Path | Contents |
|---|---|
| `docs/` | All product docs, tracked and audience-split: `STATUS.md` (source of truth), `docs-tree.json` (nav source of truth), `user/` (end-user guides), `dev/` (developer & operator guides) — see `docs/README.md` |
| `backend/app/` | FastAPI, services, pipelines, ai, ocr, storage, jobs |
| `frontend/src/` | React app (features/, components/, lib/) |

## Shared UI library (assistant-ui)

`@neuronection/assistant-ui` is our first-party React component library
(published on npm). Core rules:

- **Check the library first.** No local copies of library components.
- `frontend/src/components/ui/*` are re-export shims (import path + exit
  hatch). Never re-implement inside a shim; new adoptions add a shim.
- If the library's API doesn't fit, **change the library** — propose the
  change upstream, then adopt the new release here.
- Styling via `--as-*` tokens and `data-as-*` only; app identity in
  `frontend/src/theme.css`.
- **Dev-link hygiene:** never commit manifest edits while wired to a
  local checkout (`link:` in `pnpm-workspace.yaml`). Guarded by
  `scripts/check-dev-link.sh` in CI and as a pre-commit hook — enable
  once per clone: `git config core.hooksPath scripts/githooks`.

## Standing workflow

Read `docs/STATUS.md` → confirm scope → implement → verify (suite above) →
update docs → commit. Schema/Alembic changes are model-first with a tested
downgrade and a single linear revision chain (see the Migration notes section
of `docs/dev/data-model.md`). When multiple agent sessions run concurrently,
each works in its own git worktree; branches merge back fast-forward only.
