# Study Assistant — Agent Instructions

AI-powered, local-first desktop study workbench (Python backend + React SPA in pywebview).
Math-first (calculus), subject-agnostic by design. Full plans live in `dev/plans/` — read
them before changing architecture. **`docs/STATUS.md` is the single source of truth for
what exists and what phase we are in.** All of `dev/` is personal scratch space and
**gitignored — including `dev/plans/`** (plans are local-only; they are never committed,
so keep your own backups).

## Non-negotiable rules

1. **Never commit untested code.** Run the verification suite (below) before every commit.
   If a command doesn't exist yet, that's a finding — surface it, don't skip it.
2. **Every unit of work updates documentation.** Code changes that alter behavior,
   architecture, schema, or APIs require same-commit doc updates (`docs/STATUS.md` at
   minimum — see the `sa-docs-sync` skill). A PR that changes code but not docs is
   incomplete.
3. **Scope discipline.** Work only on the current phase (see `docs/STATUS.md` and
   `dev/plans/05-roadmap.md`). The v0.1 walking skeleton may not slip. Features outside
   the current phase need explicit user approval first.
4. **Follow the ADRs** (`dev/plans/06-decisions-and-risks.md`). If a decision must change,
   propose a new ADR in conversation — don't silently contradict one.
5. **No comments in code** unless requested. Conventions: mimic existing style, ruff +
   mypy strict (backend), eslint + vitest (frontend).
6. **Never commit secrets.** API keys live only in the OS keyring, never in files, env
   blocks, or the DB. Tests must never touch the real OS keyring — `backend/tests/conftest.py`
   installs an in-memory keyring backend for the whole suite; keep it that way (new secret
   reads/writes go through `app/core/secrets.py`, which is isolated by that conftest).

## Verification suite (all must pass before commit)

Backend (`backend/`): `ruff check . && mypy . && pytest`
Frontend (`frontend/`): `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
(CI mirrors these; golden-set evals run via `pytest tests/evals/` — never skip failures there.)

If any suite is red, fix it before committing. If tests are missing for new behavior,
write them first or in the same commit.

## Where things are

| Path | Contents |
|---|---|
| Path | Contents |
|---|---|
| `docs/` | All product docs, tracked: `STATUS.md` (source of truth), `architecture.md`, `features.md`, `ai.md`, `math-verification.md`, `data-model.md`, `import-export.md`, `usage/` (user guides) |
| `dev/plans/01…22` | Developer planning: vision/features, architecture, data model, AI pipelines, roadmap, ADRs, settings, skills/contracts, UX, analytics, import/export + later round plans 12–22 (scoping, nav, AI task layer, companion, launcher, consolidation, focus modes, cards, tab bars, settings popover, durability/sharing/study) (**gitignored, local-only**) |
| `backend/app/` | FastAPI, services, pipelines, ai, ocr, storage, jobs (layout in plans/02) |
| `frontend/src/` | React app (features/, components/, lib/) |

## Standing workflow

Read `docs/STATUS.md` → confirm phase scope → read the relevant plan doc → implement →
verify (suite above) → update docs (`sa-docs-sync`) → commit. Use the `sa-dev` skill for
feature work and bug fixes, `sa-migration` for any schema/Alembic change, and
`sa-plan` when authoring or revising a planning round. When multiple agent sessions run
concurrently, each works in its own git worktree per `sa-dev` §2 (env bootstrap,
merge-back via fast-forward only, Alembic renumbering for the later branch).
