# Plan 54 — Consolidation & hardening: module splits, delete-during-ingest, flake hygiene (user request 2026-08-31)

Status: **COMPLETE (2026-08-31 — A, E, B, C, D all landed; ADR-126/127 recorded; suite green: backend 776 · frontend 813)** · Phase: post-1.0 · **Executed before the 47–53 feature rounds** · As-built: A first, then E, then B → C → D (per plan)

## Context

The 2026-08-31 follow-up verification found that plans 47–53 complete the *feature*
surface but leave three honest debts:

1. **One deferred durability fix.** Delete-during-ingest no longer corrupts data
   (`passive_deletes`, 2026-08-28), but the in-flight job still isn't cancelled or
   re-validated — STATUS Open issues has deferred it as "worth a small dedicated
   round" since the v0.1.1 release-gate flake. None of plans 47–53 touches it.
2. **Three structural seams the new scopes will worsen** (verified sizes):
   `frontend/src/lib/api.ts` is **3,584 lines** (every endpoint in one file; plans
   47–53 add ~15 more), `backend/app/domain/models.py` is **976 lines** (every
   model; migrations 0048–0051 add four more tables/columns), and
   `backend/app/services/` is **31 flat files** (→ ~40 after planner/genesis/
   study-session/tts/search-provider services). All work today; all get worse if
   seven feature rounds land first and every new endpoint/model/service lands on
   the old seams.
3. **A named flake class.** Four flaky tests are documented in Open issues
   (LazyNoteEditor Suspense race, folder-cascade sqlite contention, two chat-turn
   event-then-assert races) plus the folders-delete tests that silently depend on
   `frontend/dist` existing. The house rule is already "fix determinism, never
   retry" — these are the remaining offenders.

This round is **pure consolidation**: every slice is either a bug fix with tests or
a zero-behavior mechanical refactor verified by unchanged test counts.

**ADRs recorded as slices start:**

| # | Decision |
|---|---|
| 126 | Job lifecycle gains a terminal **`cancelled` status** with cancel-on-purge (queued jobs for a purged entity are cancelled, running ones get a cooperative cancel flag checked at stage boundaries) + a **commit-time stale re-check** in every multi-stage handler — cancellation is explicit state, never a synthetic failure |
| 127 | **Consolidation policy:** oversized single-file modules split into packages behind stable import paths — public entry points keep a re-export shim (`lib/api`, `domain/models`), internal modules move one-shot with mechanical import updates (no shim forests); new code lands in the split layout from day one |

## A — Delete-during-ingest: cancel-on-purge + commit-time stale check (ADR-126)

**Problem.** Deleting a material/folder/course while its `ingest`/`postprocess`/
`drawing_ocr`/`image_ocr` job runs either fails the job on the FK (noise, confusing
"material x not found" errors) or — worst case — commits work into a replaced
entity.

**Design.**

- **No migration** — job `status` is a string column; `cancelled` joins the terminal
  set in the runner's type definitions and status filters.
- **Cancel-on-purge**: `purge_material` / folder cascade / `purge_course` mark all
  queued jobs whose payload references the purged entities as `cancelled` (error
  text "source deleted before start"), wake the pool so they're skipped, and set a
  **cancel flag on running ones** (in-memory registry keyed by job id — the same
  pattern as the chat stop event).
- **Cooperative stages**: the ingest/postprocess/drawing_ocr/image_ocr handlers
  check the cancel flag at each stage boundary (after OCR, after chunking, before
  embed, …) and raise `JobCancelled` — runner records `cancelled`, never `failed`.
- **Commit-time stale re-check** (belt to the suspenders): each handler's final
  write re-verifies the target row still exists **in the same transaction** as the
  commit — closing the delete-between-last-stage-and-commit race that flags alone
  can't cover.
- Runner/API semantics: `cancelled` is terminal (not retriable, excluded from
  retry-failed and from the failure badge count); `GET /jobs` filter and the
  summary gain a `cancelled` bucket; JobsPage/activity rows render a grey
  "cancelled" chip. `retriable_handlers()` and the stale-detection logic treat it
  as a quiet sibling of `done`.
- Chat turns keep their existing per-session stop machinery (plan 40D) — this
  slice adds nothing there.

**Accept.** Start ingesting a 40-page scanned PDF, delete the material halfway →
the job shows *cancelled* (not failed), no error badge, no retry affordance, and a
re-upload of the same file works normally.

**Tests.** Backend: cancel-on-purge for queued (batch) and running (flag) paths,
stage-boundary cancellation for each handler kind, commit-time stale check (delete
between stages races simulated deterministically), summary/filter accounting,
cancel-during-chat untouched.

## B — `lib/api.ts` → `lib/api/` package (ADR-127)

**Problem.** 3,584 lines, one module per app; every plan adds to the pile.

**Design.**

- Split into `lib/api/` domain modules — `client.ts` (fetch core, error helpers,
  `apiDetailMessage`), `materials.ts`, `courses.ts` (+nodes/sources/study-states),
  `chat.ts`, `quiz.ts` (+qpkg/inbox), `exercises.ts`, `notes.ts` (+drawings),
  `flashcards.ts`, `analytics.ts`, `settings.ts` (providers/models/tasks/skills/
  backup/config), `jobs.ts`, `system.ts` (health/desktop/onboarding/fs) — and an
  `index.ts` that **re-exports everything the old file did**.
- `lib/api.ts` itself becomes a one-line re-export of `./api` (or the import alias
  is kept on the directory) — **65+ import sites change nothing**.
- Zero logic edits: pure moves, `pnpm typecheck && pnpm test && pnpm build` green
  with **identical test counts**.
- Rule going forward (ADR-127): plans 47–53's new endpoints land in their domain
  module; a new domain gets a new module.

**Accept.** `rg "from '.*lib/api'"` finds the same import sites before and after;
bundle size unchanged; all suites green.

**Tests.** None new (moves only) — the unchanged 815-test suite **is** the test.

## C — `domain/models.py` → `domain/models/` package (ADR-127)

**Problem.** 976 lines, every table in one file; migrations 0048–0051 keep growing
it.

**Design.**

- Split by domain: `core.py` (Base/mixins, Profile, Course, TreeNode, CourseType),
  `content.py` (Material*, Blob, Chunk, Source, Note*, drawings incl.
  `material_images` when plan 47 lands), `study.py` (Quiz*, Exercise*, Flashcard*,
  FsrsState, review/error-pattern tables, `plan_items`/`study_sessions` when 49
  lands), `chat.py` (Chat*, proposals), `ops.py` (Job, analytics/rollup tables,
  trash snapshots, settings/preferences).
- `domain/models.py` remains as a **re-export shim** — alembic versions and the
  ~dozen app imports keep working unchanged; the shim is the public path (ADR-127).
- Zero behavior: same table names, same metadata ordering care (FK resolution
  across modules uses string-based `ForeignKey` targets already — verify no
  circular import at package init).

**Accept.** `alembic upgrade head` from a fresh DB and from a copy of a real data
dir both succeed; full suite green.

**Tests.** None new (moves only) — plus one import-order smoke (fresh-DB boot)
already covered by existing app-factory tests.

## D — `services/` → grouped subpackages (ADR-127)

**Problem.** 31 flat files with no domain grouping; plans 47–53 add ~8 more
(converters-adjacent, study sessions, review, planner, genesis, tts, search
provider).

**Design.**

- Group into four subpackages by cohesion (the mapping below is the proposal —
  adjust at implementation, the rule is domain-cohesion, not file-count):
  - `services/content/` — materials, folders, sources, drawings, course_bundle
  - `services/study/` — cards, grading, exercise_kinds, exercise_rubric,
    exercise_structs, patterns, tutor, inbox, organizer
  - `services/knowledge/` — courses, tree, concepts, context
  - `services/platform/` — backup, profiles, skills, scan_scheduler, trash,
    metrics, proposal_actions, chat, editor_ai
- **One-shot mechanical move** (ADR-127: internal modules get no shims — every
  import site updated in the same commit; ruff/mypy make this exhaustive and the
  suite proves it). `app.state` wiring, job-handler factories, and API imports are
  the main touch points.
- Test files keep their current names/locations (they mirror behavior, not module
  paths).

**Accept.** Full suite green with identical counts; `rg "from ..services import|from .services"` clean; no `services/*.py` left at top level except the four
package inits.

**Tests.** None new (moves only).

## E — Flake-class hygiene (no ADR — house rule application)

**Problem.** Four named flakes + one environment dependency, all documented in
Open issues, all in the "assert after event instead of polling" or "hidden env
dependency" class.

**Design.**

- `LazyNoteEditor.test.tsx` — wait on the editor's rendered marker (a `findBy*` on
  editor content, not the Suspense spinner's disappearance).
- `test_folders_api.py::test_delete_cascades_subtree` — the sqlite contention is a
  fixture-isolation problem: give the cascade test its own engine/connection setup
  (like the storage tests) instead of sharing the module-scoped one.
- `test_chat_branches.py::test_select_hidden_subtree_restores_later_turns` and
  `test_chat_turn_error.py::test_failed_turn_emits_turn_error_and_fails_job` —
  poll the DB with `expire_all` until the observable state (per the 2026-08-30
  `test_chat_lock` precedent) instead of asserting right after the WS event;
  extend the wait deadline to the runner's poll cadence.
- Folders-delete tests that require `frontend/dist` — make the assertion
  SPA-mount-independent (assert on the explicit 404/405 contract of the routers
  under test with the SPA mount absent) so a fresh worktree doesn't need a
  frontend build to run the backend suite.
- Policy line for the record: flakes are fixed by waiting on observables or
  removing hidden dependencies — never by retrying, sleeping longer, or marking
  xfail.

**Accept.** Ten consecutive full backend runs (parallel) + ten frontend runs with
zero flake reports; a fresh worktree runs the backend suite before `pnpm build`.

**Tests.** The fixes are tests.

## Non-goals (this round)

- Any behavior change in B/C/D (if a split accidentally changes behavior, the
  refactor is wrong — revert the piece, not the round).
- Restructuring `app/ai/`, `app/pipelines/`, `app/api/` (already packaged along
  sensible lines); `api/schemas.py` stays (249 lines, shared by design).
- Alembic history rewrites/squashes (the 47-file chain is append-only by policy).
- Golden OCR evals — **still blocked on the user's real scans** (~20 pages +
  ~10 handwriting photos into `backend/tests/fixtures/golden/`); the fixtures dir
  and README conventions are ready and waiting. User action, not plan work.
- Micro-optimizations to import cost / startup time (bundle split already done;
  revisit only with evidence).

## Dependencies & suggested order

A is independent (behavior fix) — **first**, it's the only non-mechanical slice.
E next (fixes the gate's own noise before seven rounds of feature work run
through it). B → C → D in any order after E; all four land **before** the 47–53
feature rounds so new endpoints/models/services are born into the split layout.

## Verification per slice

Backend: `ruff check . && mypy . && pytest` · Frontend: `pnpm lint && pnpm typecheck
&& pnpm test && pnpm build` · plus the explicit **test-count invariance check** for
B/C/D (moves only) and the ten-run flake soak for E. Docs duty: `docs/STATUS.md`
changelog + module rows (the splits are architecture-adjacent → a one-line note in
`docs/architecture.md`), `docs/usage/activity.md` for the cancelled status, Open
issues entries retired as each flake/hardening lands.
