# Plan 55 — Code quality & typed contracts: vocabulary enums, OpenAPI-generated TS, typed service boundaries, component adoption (user request 2026-08-31)

Status: **in progress — slices A, B, D done; C tranche 1 done (2026-08-31, ADR-128…130 recorded; backend 782 · frontend 815 green)** · Phase: post-1.0 · **Runs after 54, before the 47–53 feature rounds** · Remaining: C tranches 2–5 (courses/tree → quiz/exercises → chat/context → metrics/bundle), E (component adoption)

## Context

The user asked for a best-practices pass: enums instead of string matching, maximum
component reuse, and other clean-code methods — and whether further restructure is
needed. Audit (2026-08-31, hard numbers):

- **String-matching is pervasive.** Only **2 StrEnum classes** exist in the whole
  backend (`ContextScope`, `agui.EventType`) against **573 `dict[str, Any]`**
  occurrences and bare literals everywhere: job statuses (`"queued"/"running"/
  "done"` — plan 54 adds `"cancelled"` to the same pattern), material kinds,
  question types, compose kinds, attempt modes, capabilities, WS topics (f-strings
  scattered: `f"jobs:{id}"`, `f"chat:{id}"`, …), event names, localStorage keys.
  The pattern to copy already exists twice — it just never got applied.
- **The frontend hand-maintains the contract.** `lib/api.ts` carries **145
  hand-written interfaces/types** mirroring the backend (3584 lines, split comes in
  54-B) — every backend change risks silent drift that only runtime tests catch.
- **Three verified component duplications of library modules:** local
  `components/ErrorBanner.tsx` (library `error-banner`), `UndoDeleteNotice.tsx`
  (library `undo-notice`), and an inline copy-button implementation inside
  `BlockRenderer` (library `copy-button`) — all three violate the
  `sa-assistant-ui` skill's "check the library first" rule as unintentional local
  copies. Inline spinner/empty-state patterns across pages are the softer version
  of the same issue.
- **Restructure verdict: no — beyond plan 54.** The three structural seams
  (`lib/api.ts`, `domain/models.py`, `services/` flatness) are exactly what 54
  splits; components/ and features/ are well-factored; what remains is
  *typing/vocabulary discipline*, which is this round — orthogonal to structure.

**User decisions (2026-08-31):** clean-code interpretation confirmed; the
**no-comments rule stays as-is** (AGENTS.md §5 unchanged — quality comes from
naming/types/tests, not narration); TypeScript types are **generated from
OpenAPI**, not hand-maintained.

**ADRs recorded as slices start:**

| # | Decision |
|---|---|
| 128 | **Closed vocabularies are `StrEnum`s (or `Literal`s derived from them), never bare literals**; DB columns stay strings (SQLite, zero churn — `StrEnum` compares equal to its value); open registries (exercise `card_*` kinds) keep their registry object with typed keys — enums for closed sets, registries for open ones |
| 129 | **The frontend's request/response types are generated from FastAPI's OpenAPI schema** (`openapi-typescript`), committed and CI-drift-guarded; hand-written TS types survive only for client-side-only shapes (form state, option tuples) |
| 130 | **Service/API boundaries return typed models** — pydantic response models on every endpoint, typed dataclasses/pydantic models from services; `dict[str, Any]` survives only inside stable-shape JSON columns, which get `TypedDict`s |

## A — Backend vocabulary: enums for every closed set (ADR-128)

**Problem.** `== "queued"`, `kind == "pdf"`, `mode == "exam"` and scattered
f-string WS topics are one typo away from silent bugs mypy can't see.

**Design.**

- New `app/core/vocab.py` (single import point) defining the `StrEnum`s:
  `JobStatus` (queued/running/failed/done/**cancelled** — defined *here* so plan
  54-A consumes it instead of inventing another literal), `MaterialKind`
  (pdf/image/md/txt/docx/pptx/epub/html/audio/video — plan 47-A consumes),
  `QuestionType`, `ComposeKind`, `AttemptMode`, `Capability`, `TaskName`,
  `ProvenanceKind`, `ChatRole`, `StudySessionKind`/`Source`, `PlanItemKind`,
  `ReviewOrigin`, plus `WSTopic` as **factory functions** (`ws_jobs(job_id)`,
  `ws_chat(session_id)`, …) and `WsEvent` for event names. Exercise kinds stay a
  registry (open set) but gain typed keys + a `Literal` for the closed subset.
- Pydantic schemas use the enum types directly (FastAPI then emits `enum: […]` in
  OpenAPI → slice B's codegen picks them up for free). Boundary parsing:
  `JobStatus(value)` in a shared `parse_vocab` helper → `ValueError` → 422 with
  the allowed set in the message (replaces hand-rolled 422 checks).
- Mechanical sweep: every comparison/assignment/construction on these
  vocabularies switches to the enum (`Job.status == JobStatus.QUEUED` — legal and
  SQL-translating because `StrEnum` *is* a str). `rg`-verified zero remaining
  bare-literal comparisons per vocabulary; mypy catches straggler sites.
- WS topic/event strings: all publishers/subscribers go through the factories —
  the frontend mirror comes in slice D.

**Accept.** `rg '"queued"|== "pdf"|f"jobs:' backend/app` finds only
`vocab.py`/enum definitions; renaming a vocabulary value is a one-file change
that mypy + tests verify everywhere else.

**Tests.** No behavior change (same strings hit the DB) — suite invariance is the
test; new unit tests for `parse_vocab` 422s and `WSTopic` factories.

## B — OpenAPI-generated frontend contract types (ADR-129)

**Problem.** 145 hand-written interfaces mirror the backend by hand; drift is
caught by runtime tests at best.

**Design.**

- Tooling: `openapi-typescript` — `pnpm api:types` regenerates
  `src/lib/api-schema.d.ts` from `GET /openapi.json` (backend running or a
  committed schema snapshot; prefer: a pytest fixture exports `openapi.json` to
  `frontend/openapi.json` so the frontend build never needs a live backend).
  Committed file + **CI drift guard** (regenerate and `git diff --exit-code`).
- Consumption: after 54-B's split, each `lib/api/*` domain module types its
  request payloads and return values from the generated `paths`/`components`
  (`operations['listMaterials']['responses'][200]['content'][application/json]`-style
  helpers in one `lib/api/types.ts`). Hand-written types remain only for
  client-side-only shapes (COMPOSE_KINDS option tuples, form state, UI flags).
- Migration order: all **new endpoints from plans 47–53 are born generated**
  (hard rule); the ~20 highest-traffic existing types (materials, courses, chat,
  quiz payloads) migrate in this slice; the long tail migrates opportunistically
  per domain touch — the drift guard makes partial migration safe.
- A's enums make the generated unions carry real value
  (`status: "queued" | "running" | …` arrives from the backend schema, not a
  hand-typed mirror).

**Accept.** Change a backend response field → `pnpm api:types` produces a diff →
frontend compile errors point at every affected call site (currently: nothing
points at anything until runtime).

**Tests.** Codegen drift guard (CI); the compile gate is the migration test;
existing suites stay green.

## C — Typed service/API boundaries (ADR-130)

**Problem.** 573 `dict[str, Any]` — the biggest offenders are exactly the
highest-traffic paths: `api/courses.py` (36), `course_bundle.py` (31),
`services/chat.py` (30), `api/quiz.py` (21), `context.py` (20), `metrics.py` (19),
`tree.py` (14).

**Design.**

- Every FastAPI endpoint declares a pydantic **response model** (many return bare
  dicts today — `schemas.py` grows per domain; OpenAPI then documents them and
  slice B's codegen inherits the shapes).
- Services that feed those endpoints return the same pydantic models (or frozen
  dataclasses for internal-only data) instead of building dicts.
- Legitimate remainder: dynamic-shape **JSON columns** (`Job.payload`,
  `ChatMessage.trace/blocks/tool_calls`, preferences) keep `dict[str, Any]` at
  the column but gain `TypedDict`s for their stable shapes (`JobPayload`,
  `TurnTrace` — the trace already has a documented schema), so
  `payload["material_id"]` becomes a checked access.
- Split per domain to keep slices reviewable: C1 courses/tree, C2 quiz/exercises,
  C3 chat/context, C4 metrics/bundle — each independently shippable, suite green
  between.

**Accept.** `rg -c 'dict\[str, Any\]' backend/app/services backend/app/api` drops
from ~200 in the seven offender files to the JSON-column remainder; mypy strict
stays clean.

**Tests.** Response-model round-trip tests per domain (serialize/validate the
documented shapes); existing API tests already pin behavior.

## D — Shared constants, single source per side

**Problem.** WS topics/events (backend f-strings, frontend string literals),
`ca-*` localStorage keys, job-type mirrors — duplicated knowledge.

**Design.**

- Backend: covered by slice A (`WSTopic` factories, `WsEvent`).
- Frontend: `lib/constants.ts` — topic builders mirroring the backend factories,
  WS event names, `storage-keys.ts` merged in (every `ca-*` key as a named
  constant), job/material-kind unions imported from the generated schema (B)
  instead of redeclared.
- One cross-check test: the frontend topic builders are exercised against a
  snapshot of backend-published topics (the WS plumbing tests already publish;
  assert the strings round-trip).

**Accept.** `rg '"ca-' frontend/src` finds only `storage-keys.ts`;
`rg 'jobs:' frontend/src` finds only the builder.

**Tests.** The cross-check test above; suites otherwise invariant.

## E — Component reuse: library adoption round 2

**Problem.** Three verified local duplicates of library modules, plus inline
spinner/empty-state patterns that keep multiplying per page.

**Design.**

- Replace the verified copies (per the `sa-assistant-ui` skill — shim first,
  change the library when its API doesn't fit, `verify-in-app.mjs` to confirm):
  - `components/ErrorBanner.tsx` → library `error-banner` (new shim `ui/error-banner.tsx`).
  - `UndoDeleteNotice.tsx` → library `undo-notice` (shim `ui/undo-notice.tsx`).
  - `BlockRenderer`'s inline copy button → library `copy-button` (shim `ui/copy-button.tsx`).
- Sweep pass: count inline `animate-spin` loaders and ad-hoc empty-state blocks;
  adopt library `Spinner` / `EmptyState` where a page rolls its own (target: the
  big surfaces — Library, Practice, Jobs, Scores — not a pixel-tax on every
  tooltip).
- Rule for plans 47–53 (recorded here, enforced by the skill): new surfaces
  (print templates, session pill, review queue, genesis dialog, planner) check
  the library first — `Wizard` for the genesis/promote dialogs, `DatePicker` for
  exam_date/planner dates, `ChipList`/`ChipInput` for tags, `Table` where tabular
  data renders.

**Accept.** `components/ErrorBanner.tsx`, `UndoDeleteNotice.tsx` are shims (or
deleted); drift-audit stays clean; the weekly audit workflow in the library repo
reports no study-assistant regressions.

**Tests.** Existing component tests re-pointed at the library implementations
(behavior-preserving); visual check via the library's Ladle stories.

## Non-goals (this round)

- Comments/docstrings policy change — **the no-comments rule stays** (user
  decision 2026-08-31; AGENTS.md §5 and sa-dev unchanged).
- Repository/DTO pattern layers, dependency-injection frameworks, or CQRS-style
  restructuring — the service/endpoint split is healthy; this round only types
  its boundaries.
- OpenAPI client *generation* of the fetch functions themselves (only types are
  generated; the client stays hand-written for control over errors/auth/WS).
- Runtime Zod/valibot validation of backend payloads in the frontend (types are
  compile-time; the backend is the same trust boundary it has always been).
- Replacing open registries (exercise kinds, compose skill kinds) with enums —
  registries with typed keys are the correct tool for open sets (ADR-128 rule).
- mypy plugin work / new strictness flags beyond what the enum migration needs.

## Dependencies & suggested order

**After 54** (A/B consume 54-B's `lib/api/` package and 54-C's models package;
54-A consumes this plan's `JobStatus`). A → B → D (enums flow into codegen into
the constants mirror). C is independent of B but its response models make B's
generated types richer — run C1–C4 after B. E independent; land before the
feature rounds so 47–53 build on library primitives.

## Verification per slice

Backend: `ruff check . && mypy . && pytest` · Frontend: `pnpm lint && pnpm
typecheck && pnpm test && pnpm build` · plus slice-specific gates: A's
zero-bare-literal greps, B's codegen drift guard in CI, C's dict-count delta
recorded in STATUS, E's drift-audit clean. Docs duty: `docs/STATUS.md` changelog +
module rows, `docs/architecture.md` (typing conventions section), AGENTS.md gets
one line under conventions pointing at `app/core/vocab.py` + generated types as
the house rule (skills `sa-dev` §3 updated same commit).
