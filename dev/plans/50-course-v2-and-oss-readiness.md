# Plan 50 — ca-course/v2 bundles, skill packs, e2e smoke, OSS readiness (user request 2026-08-31)

Status: **COMPLETE (2026-09-02, worktree `feat/plan50-course-v2-oss`, 4 commits
1a7e122/d0ffda5/adee278/e22492d)** · Phase: post-1.0 · Suggested order: A → B → C → D (as built)

## As-built (2026-09-02)

- **A (1a7e122)**: v2 exporter + dual v1/v2 importer; `cards.json` (FSRS
  schedules + review log behind `include_history`), `patterns.json`
  (discovered only), `history.json` (attempts/answers/sessions/step_attempts/
  help events), `note-versions.json`, `exam_date`, question ids; import
  enqueues postprocess per material (job ids in response); validation covers
  the new sections; round-trip byte-stability pinned across fresh machines
  (same-DB re-imports drift by ids — test mirrors real sharing).
- **B (d0ffda5)**: `ca-skills/v1` export (system-scope versions only) + staged
  import preview/commit with replace/rename/skip; new service
  `services/platform/skill_packs.py`, endpoints `POST /skills/export` +
  `POST /skills/packs/import`; SkillsTab per-row Export + Import pack dialog.
  Gotcha recorded: httpx drops a URL query string when `params=` is passed —
  test clients must pass all query args via `params`.
- **C (adee278)**: Playwright harness (`frontend/e2e/`) — global setup builds
  SPA, spawns real backend (temp data dir) + mock OpenAI-compatible provider
  (quiz JSON / CALC tool line / embeddings); specs S1 boot+wizard, S2
  upload+search, S3 quiz run+score, S4 chat turn with prompt-grammar tool
  card; CI `e2e` job + release-gate step. Hard-won harness rules: spawn
  children `detached` with stdio to log FILES (inherit keeps pipes open and
  hangs the runner), teardown kills the process GROUP (`kill -TERM -pid`;
  plain pid kill orphans uv's python child; `/bin/sh` kill has no `--`),
  vitest `exclude` + eslint `ignores` cover `e2e/`, chat spec runs before the
  course specs (no course bound → no citation-repair path).
- **D (e22492d)**: SECURITY.md, issue/PR templates, About family links,
  enriched sample course (3-question quiz, 6 cards/2 due, exam_date, concept
  coverage), getting-started docs; README badges were already dynamic.
- Gates: backend ruff/mypy clean · 829 tests; frontend lint/typecheck/829
  tests/build · e2e 4/4 green.

## Context

The study assistant is now public (`github.com/neuronection/study-assistant`, Apache-2.0,
advertised on neuronection.com) but several *sharing* and *open-source project* pieces
are missing or stale:

- **The course bundle undersells the sharing story.** `ca-course/v1`
  (`services/course_bundle.py`) omits **flashcards + FSRS state**, `courses.exam_date`,
  error patterns, and note version history; imported materials never get a
  `postprocess` job, so **an imported course silently degrades to FTS-only RAG** (no
  vectors) until the user manually re-ingests. Sharing a course is the family's
  "free open source assistants that make a difference" story made real — it should be
  complete and self-healing. No users exist → clean **v2** break, importer still
  accepts v1.
- **Skills are locked in the app.** The skills system (J1–J6) is complete; J7 skill
  packs (export/import JSON) never shipped — the community can't share prompt
  customizations even though everything else (qpkg quizzes, caq files, course bundles)
  already travels.
- **No e2e smoke anywhere.** 769 backend + 815 frontend unit/integration tests, zero
  Playwright; the release gate has caught real races that single suites missed, but
  nothing exercises the *composed* app (boot → upload → study).
- **OSS housekeeping drift**: README badges hardcode `v0.1.0` / "in development"
  (actual: 0.1.2-rc.x, pre-release); the About page doesn't link the family hub;
  no SECURITY.md; the sample course stops short of the full loop (no flashcards/quiz
  pre-seeded for the review/demo surfaces).

**ADRs recorded as slices start:**

| # | Decision |
|---|---|
| 109 | `ca-course/v2`: breaking additive-complete bundle (flashcards + FSRS, exam_date, error patterns, optional note versions + attempt history), **import enqueues postprocess (re-embed) for imported materials**; exporter emits v2 only, importer accepts v1 + v2 |
| 110 | Skill packs = JSON export/import of skill definitions + versions through the existing validators; staged preview, name-collision policy explicit |
| 111 | E2E smoke = Playwright against the real backend in webapp mode with a **mock OpenAI-compatible provider**; smoke set stays small (boot/onboarding, material round-trip, quiz run, chat turn) and gates releases |

## A — ca-course/v2 (ADR-109)

**Problem.** Bundles drop flashcards/FSRS/exam_date/patterns; imported courses lose
semantic search.

**Design.**

- `manifest.version: 2`; exporter emits v2 only (breaking, no users). Importer
  detects `version` and accepts both (v1 → v2 defaults: no flashcards, no
  exam_date).
- Added to v2: flashcards (with node placement, kind, front/back/tags) + their
  `fsrs_states` (and `review_log` behind an explicit `include_history: false` default
  — schedules travel, history is opt-in); `courses.exam_date`; course-scoped
  `error_patterns` (seeded rows are re-seeded, not exported — only `discovered`
  rows travel); note **versions** behind `include_note_versions: false` (current
  body only by default).
- Optional `include_history` top-level flag also carries quiz/exercise **attempts**
  (default off — bundles are content, not surveillance).
- **Import self-healing**: after writing materials + extractions, import enqueues a
  `postprocess` job per material (embeddings + index card) exactly like upload does —
  closing the FTS-only degradation. Progress rides the existing `jobs:{id}` WS topic;
  the import response returns the job ids.
- Round-trip identity: export → import → export is byte-stable for v2 (id remap
  deterministic), pinning the format.

**Accept.** Export a fully loaded course (materials, notes, quizzes, exercises,
flashcards with schedule state, exam date, a discovered error pattern) → import into
a fresh profile → everything is there, semantic search works immediately (postprocess
jobs complete), exam countdown shows on Home.

**Tests.** Backend: v2 round-trips per entity class, v1 import compatibility,
postprocess-enqueued-on-import, include-history flags both ways, deterministic
re-export. No frontend change beyond import/export dialogs' copy (v2 label).

## B — Skill packs (J7) (ADR-110)

**Problem.** Custom skills (behavior contracts, prompt templates, course-type
overrides) can't leave the machine.

**Design.**

- `POST /skills/export` `{ids}` → one JSON (`ca-skills/v1`): skill defs + all
  versions + activation/course-type metadata + the constraints doc. Secrets don't
  exist in skills (prompts only) — state that in the schema card.
- `POST /skills/import` staged: preview = parsed pack + per-skill validation results
  (the same validators the editor uses) + collision report (same name →
  `replace` | `rename` | `skip` per skill, chosen in the confirm dialog); commit
  inserts as **new versions on existing skills** when replacing (history preserved),
  fresh skills start at v1.
- Settings → Skills: **Export…** (multi-select or per-row) and **Import…** (file
  picker → preview dialog → commit) riding the existing SkillsPage.

**Accept.** Export the two customized skills, edit the JSON's prompt text by hand in
an editor, import into a fresh profile → both skills exist with the edited text, one
as a new version on the replaced skill.

**Tests.** Backend: export shape, import validation failures (bad contract fields),
collision paths (replace-as-new-version / rename / skip), round-trip identity.
Frontend: export/import dialogs + preview rendering.

## C — Playwright e2e smoke (ADR-111)

**Problem.** Nothing tests the composed app; release gates have no user-flow signal.

**Design.**

- `frontend/e2e/` + `playwright.config.ts` (project `e2e`, not part of `pnpm test`):
  a global-setup spawns the real backend — `python -m studyassistant web` with
  `SA_DATA_DIR` pointed at a temp dir and `SA_PORT` picked free — waits on
  `/api/v1/health`, tears down after. Webserver = the SPA dev server or the backend's
  served SPA (prefer backend-served: exercises the real mount).
- **Mock provider**: tests spin a tiny FastAPI stub exposing
  `/v1/chat/completions` (streaming), `/v1/embeddings`, and an OpenAI-compatible
  transcription route, returning deterministic payloads (a fixed quiz JSON, a fixed
  answer stream); onboarding creates a provider pointing at it **with a blank API
  key — legal per plan 48-A's blank-key support — so CI needs no secret service
  (headless Linux has no SecretService; the keyring path is never exercised in
  e2e)**. No real network (the backend session keeps its socket guard out of e2e;
  CI allows localhost only).
- Spec set (keep it smoke-sized): **S1** boot → wizard visible → skip → shell
  renders; **S2** create course → upload a markdown fixture → extraction ready →
  search finds it; **S3** generate quiz from the mock → answer one question → score
  recorded; **S4** chat turn streams a fixed answer with a tool card. Each spec is
  independent (fresh temp data dir per worker).
- CI: a new `e2e` job (ubuntu, `pnpm exec playwright install --with-deps chromium`,
  runs after unit jobs) — added to the release gate so a tag build proves the flows.

**Accept.** `pnpm e2e` locally and in CI runs the four specs green against the real
backend; a deliberately broken ingest (fixture mutate) fails S2.

**Tests.** The specs are the tests; no unit coverage of the harness itself.

## D — OSS readiness polish

**Problem.** Public repo has stale badges, no security policy, an About page with no
family links, and a sample course that doesn't demo the study loop.

**Design.**

- README: version badge → dynamic release badge
  (`img.shields.io/github/v/release/neuronection/study-assistant`), status badge →
  "pre-release", and the Quick Start gains the local-AI guide link (plan 48).
- `SECURITY.md` (report path + supported scope: local app, keyring, no network
  listeners beyond localhost by default) — mirroring the assistant-ui repo.
- About page: family links (neuronection.com, sibling assistants), version +
  license + repo links (it's the app's self-identification surface).
- Sample course (`POST /onboarding/sample`) enriches to demo the loop: keep the
  existing materials/notes, add a small generated-looking quiz (deterministic
  content, validators-passing), 6 flashcards (2 already due so Review/Today light up
  honestly), an exam_date ~14 days out, and one concept with coverage — so first-run
  users see every major surface with content. Still one click, still deletable.
- `.github/`: issue templates (bug/feature) + PR template checklist (verification
  suite + docs duty) — matching the repo's actual workflow.

**Accept.** A fresh visitor can see current version, report a security issue, and
after the sample course lands on a Home screen with streak/review/exam signals and a
runnable quiz.

**Tests.** Sample-course service tests updated for the new fixtures (validators must
pass); badge/About assertions in existing page tests if any pin them.

## Non-goals (this round)

- Selective/partial backup restore (all-or-nothing backup stays; course bundles are
  the selective path).
- Sharing *between profiles on one machine* via bundles (export/import covers it).
- A public "community packs" index (neuronection hub could host links later; the
  formats here are the prerequisite).
- Greek/German UI locales (i18n plumbing ready; 1,700+ keys is its own round —
  revisit after the feature surface stabilizes).
- Telemetry/opt-in analytics (I12 says strictly opt-in; nothing to build until asked).

## Dependencies & suggested order

A and B independent. C independent but land **early** — its harness de-risks A's
import flow and everything after. D last (links to C's CI badge, README references
48/49 features).

## Verification per slice

Backend: `ruff check . && mypy . && pytest` · Frontend: `pnpm lint && pnpm typecheck &&
pnpm test && pnpm build` · plus `pnpm e2e` from slice C onward. Docs duty:
`docs/import-export.md` (v2 format + skill packs), `docs/STATUS.md` changelog +
module rows, `docs/usage/getting-started.md` (sample course contents).
