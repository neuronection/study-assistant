# 18 — Focus-mode uniformity & the exercise type system

**Status:** Part A complete (A1–A5, 2026-08-20). Part B complete (2026-08-21) — B1 ADR-045/migration 0026/card mapping; B2 structural kinds; B3 AI-rubric kinds (explain/error_spot/correct_solution, deterministic-first) + the kind picker in GenerateDialog. Deferred from the original sketch: symbolic single-step kinds (simplify/solve/etc. — the multi_step runner already covers them), speed drills, and the interactive backlog (◇ rows).
**Inputs:** user review of the post-plan-17 app: runners are "too naked", back-navigation
loses context, materials opened from courses steal the path, and the practice model
should unify (flashcards = an exercise subtype; many exercise types needed).
**Phase:** post-1.0 backlog (follows plan 17).

**As-built notes (A1–A5):** origin turns out NOT to need manual encoding — the
router encodes search params, so `useCurrentOrigin` returns the raw href and
`parseOrigin` validates it (leading `/`, not `//`, decode-safe). Part A needed two
small backend reads after all (`GET /quiz/activities/{id}`, `GET /exercises/{id}`)
for the derived-placement fallback. A4: shared `MaterialDetailBody` extracted
(page + drawer); `MaterialDetailDrawer` on FocusShell overlay via `?material=`;
library rows pass `?from=` and the detail back button honors it. A5: FocusShell
`title` widened to ReactNode + optional `onClose`/`ariaLabel`/`contentClassName`;
NoteEditor renders through it (drawer = overlay variant, full page = page variant
without X); NoteBreadcrumb deleted in favor of `useFocusContext` (course ▸ node —
no intermediate ancestors, deliberate).

Two independent parts — A (UX/navigation) is pure frontend; B (exercise types) is a
model change needing its own ADR. Slices A1→A4 ship independently of B.

---

# Part A — One focus-mode chrome, origin-aware navigation

## Problems (as reported)

1. **Quiz runner is naked** — a running quiz shows a bare "back to Courses" link and
   a counter; no course/node context, no meta, no sense of *where this quiz lives*
   (quizzes always exist under a course/child node). Same for the exercise player.
2. **Closing a quiz dumps you on `/courses`** — it should return to *where it was
   opened from* (workspace Practice tab, Today screen, sidebar Study…, palette).
3. **Opening a material from a course navigates to `/library/$id`** — a different
   path with library chrome; closing goes to the library, not back to the course
   workspace you were in.
4. **Every focus surface hand-rolls its own chrome** — quiz runner, exercise player,
   material page, note drawer all do titles/close/back differently.

## Design

### A1 — `FocusShell` (shared component)

New `components/layout/FocusShell.tsx` — the single full-page/overlay chrome for
"you are now doing one thing" surfaces:

- Props: `{ title, subtitle?, context?: { courseId, courseTitle, nodeId?, nodeTitle?, accent }, meta?: ReactNode, onClose, children, overlay?: boolean }`.
- Renders: header row = **context breadcrumb** (course dot + course title ▸ node
  title, each a router Link — node link preserves the caller's tab where known),
  title (text-lg font-semibold), **close button (X)** calling `onClose`, and a
  collapsible **details strip** (chevron; collapsed by default = today's clean
  look, expanded = meta info). One visual language everywhere.
- `overlay` variant reuses `NoteEditorDrawer`'s fixed right-panel + backdrop +
  Escape behavior; page variant is the current centered column.

### A2 — Origin-return navigation ("close goes back")

One rule for quiz/exercise/material/note surfaces:

- **Origin = explicit `?from=` search param** written by every in-app entry point
  (workspace rows, sidebar Study…, study launcher, palette, Today, EntityActionMenu
  handlers — extend `useEntityActionHandlers`), URL-encoded full location
  (path + search) of the page that opened it.
- **Fallback = derived placement**: each object knows its `node_id`/`course_id` —
  closing returns to `/courses/{cid}/n/{nid}?tab=practice` (materials → Materials
  tab) even for deep links/refreshes where `?from` is absent.
- **Last resort** = `/courses` (today's behavior).
- Implement as `lib/origin.ts` (`buildFrom(location)`, `useOriginBack(fallback)`);
  no global store, everything survives refresh. Old `backToCourses` buttons and
  `window.location.reload()` "try similar" hack are replaced by router navigates.

### A3 — Runners get context + info (fixes "too naked")

- **QuizRunner** inside `FocusShell`: context breadcrumb (course ▸ node — fetched
  via the shared `['tree', cid]` query, scope-chip mapping already exists), meta
  strip (mode: practice/exam · difficulty · question count · concepts/tags when
  present · started-at/elapsed), progress: `index/total` becomes a slim progress
  bar + dot map of answered/flagged questions. Summary screen keeps X (origin
  return) + Retry, and gains "Open in workspace" (derived placement link).
- **Exercise Player** (A3b): same shell; meta = difficulty · step count · socratic
  toggle state · independence score after completion; step progress bar.

### A4 — Materials open in place from course context

- Workspace Materials tab (and sidebar/palette material links *from a course
  context*) stop navigating to `/library/$materialId`. They open a
  **`MaterialDetailDrawer`** over the workspace via a `?material=<id>` search param
  — exactly the `NoteEditorDrawer` / `openNote(id)` pattern (`tabSearch` gains
  `material?`; back button/X = param stripped; workspace stays mounted under it,
  tab preserved).
- The drawer reuses `MaterialDetailPage`'s tab content components (Extraction/
  Original/Side-by-side already extracted as shared views) inside `FocusShell`
  overlay; assigned-to chips already deep-link back into node workspaces.
- `/library/$materialId` remains the canonical standalone page for
  library-origin opens (rail, library lists); its back button uses `?from` →
  else `/library` with the material's course/folder search restored.

### A5 — Note drawer + chat panel alignment (small)

- `NoteEditorDrawer` and full-page `/note/$id` adopt `FocusShell` for their
  headers (title, breadcrumb, X) — delete their ad-hoc headers. ChatPanel keeps
  its sidebar anatomy (it is not a focus mode).

## Accept (A)

- Start a quiz from: workspace Practice tab, sidebar Study…, Today, palette —
  finish/close it → each returns to *that* page.
- Deep-link/refresh a running quiz → close lands on the quiz's node workspace.
- Runner header shows course ▸ node + expandable meta; progress bar visible.
- Open a material from a workspace → URL stays on the workspace route
  (`?material=`), close returns to the same tab; library open behaves as before
  but back-returns to the folder you were in.
- Quiz/exercise/material/note share one shell component (grep: no ad-hoc
  back-link rows left outside `FocusShell`).

## Tests (A)

- `FocusShell` render test (breadcrumb links, details collapse, onClose).
- `lib/origin` unit test (from-param precedence, fallbacks, encoding).
- QuizRunner: origin-return from param, derived fallback, context breadcrumb,
  progress bar; Player: same core set. MaterialDrawer: opens over workspace,
  param stripped on close, tab preserved.

---

# Part B — Exercise type system (flashcards = exercise subtype)

## Problems

1. "Exercise" today means exactly one thing: a multi-step derived/evaluated
   problem with a hint ladder. Flashcards live in a completely separate table +
  UI + session model, yet they *are* exercises (practice items with a response
   and a correctness/schedule outcome).
2. There is no vocabulary for *other* kinds of practice: matching, ordering,
   explain-in-your-own-words, error-spotting, … each currently has no home.

## Direction (user decision 2026-08-20)

- **Exercise = the generic practice item**, with a `kind` taxonomy (below).
  Flashcards migrate to exercise kinds `card_basic` / `card_reverse` /
  `card_cloze` (FSRS stays the scheduler for card kinds).
- **Quizzes stay separate** (assessment: attempts, scoring, exam mode, import/
  export) — the question types inside a quiz may mirror exercise kinds but the
  runner/attempt model is different. Not in this plan's scope to merge.
- Every kind declares an **assessment engine**: deterministic (equivalence chain /
  exact / structural) or AI-assessed (rubric + audit + repair loop) — the existing
  rule "determinism before LLM" applies; AI assessment is itself audited and
  cached on the attempt.

## Exercise kind catalog (the requested list)

Legend: Engine = D-chain (symbolic equivalence chain), D-exact (normalized exact
/ tolerance), D-struct (structural compare: sets/orders/pairs), FSRS (scheduler),
AI (rubric assessment), Hybrid (AI proposes, deterministic verifies).
Status: ● existing · ○ near (this plan) · ◇ later.

### Symbolic mathematics (D-chain)

| # | Kind | Task | Input UI |
|---|---|---|---|
| 1 | `simplify` ○ | simplify the expression | MathInput |
| 2 | `expand_factor` ○ | expand / factor as instructed | MathInput |
| 3 | `differentiate` ○ | compute the derivative | MathInput |
| 4 | `integrate` ○ | definite/indefinite integral | MathInput |
| 5 | `solve` ○ | solve equation/inequality (also systems) | MathInput |
| 6 | `transform` ◇ | rewrite in the required form (trig identities, substitution forms) | MathInput |
| 7 | `proof_steps` ◇ | prove identity line-by-line; each line chain-checked | multi-MathInput |

### Exact / numeric (D-exact)

| # | Kind | Task | Input UI |
|---|---|---|---|
| 8 | `numeric` ● | numeric answer with tolerance (quiz `numeric` twin) | text |
| 9 | `short_answer` ● | exact normalized text | text |
| 10 | `fill_blank` ○ | complete blanks inside a text/formula | inline inputs |
| 11 | `table_complete` ◇ | fill the missing table cells | grid inputs |
| 12 | `unit_convert` ◇ | quantity + unit conversion | text w/ unit field |
| 13 | `graph_read` ◇ | read values/properties off a rendered plot | choice/numeric |

### Structural (D-struct)

| # | Kind | Task | Input UI |
|---|---|---|---|
| 14 | `single_choice` / `multi_choice` / `true_false` ● | classic choice | choice chips |
| 15 | `matching` ○ | pair terms ↔ definitions (partial credit) | two-column connect |
| 16 | `ordering` ○ | order shuffled items (proof lines, algorithm steps, sorting) | drag list |
| 17 | `categorize` ○ | sort items into given categories | drag into bins |
| 18 | `label_diagram` ◇ | drag labels onto diagram hotspots | canvas drag |
| 19 | `mark_graph` ◇ | place points/interval on graph or number line | canvas click |
| 20 | `construct_geo` ◇ | dynamic-geometry construction meeting constraints | geo canvas |

### Timed / procedural (D-exact + timing)

| # | Kind | Task | Input UI |
|---|---|---|---|
| 21 | `speed_drill` ○ | rapid-fire mental-math chain, per-item timing | numpad |
| 22 | `procedure` ◇ | execute an algorithm by hand (long division, Gaussian elimination) step grid | grid inputs |

### Scheduler-based (FSRS — "flashcard" kinds)

| # | Kind | Task | Input UI |
|---|---|---|---|
| 23 | `card_basic` ●→○ | front → recall back, self-grade (Again…Easy) | reveal + 4 buttons |
| 24 | `card_reverse` ●→○ | back → recall front | same |
| 25 | `card_cloze` ●→○ | cloze deletion recall | same |

### AI-assessed (rubric)

| # | Kind | Task | Input UI |
|---|---|---|---|
| 26 | `explain` ○ | explain the concept/step in your own words | markdown |
| 27 | `error_spot` ○ | find the flawed line(s) in a worked solution (feeds mistake notebook taxonomy) | line select |
| 28 | `correct_solution` ○ | fix the flawed solution — fixes chain-checked where symbolic, AI otherwise | MathInput per line |
| 29 | `proof_free` ◇ | free-form proof against a rubric (AI + symbolic spot-checks) | markdown + MathInput |
| 30 | `essay` ◇ | long answer against a rubric | markdown |
| 31 | `critique` ◇ | critique a (possibly AI-written) solution | markdown |
| 32 | `estimate` ◇ | Fermi estimation with tolerance bands | numeric + reasoning |
| 33 | `translate` ◇ | translation practice (language courses) | text |
| 34 | `case_study` ◇ | multi-part applied problem mixing sub-kinds | mixed |

### Interactive / construction (◇, mostly post-1.0 backlog)

| # | Kind | Task | Input UI |
|---|---|---|---|
| 35 | `simulate` ◇ | steer a parameter playground to a target condition ("make the parabola touch the line") | sliders |
| 36 | `concept_map_complete` ◇ | fill the missing nodes/edges of a concept map | graph editor |
| 37 | `code_function` ◇ | implement a function passing visible unit tests (sandboxed runner) | code editor |

**MVP batch (this plan):** `matching`, `ordering`, `categorize`, `fill_blank`
(structural, zero marginal AI cost, huge coverage of non-math courses) +
card migration + `explain`, `error_spot`, `correct_solution` (AI-assessed, reuse
runner/audit). Symbolic singles (`simplify`…`solve`) are thin wrappers over the
existing chain — cheap win, do them with the structural batch if time allows.

## Design

### B1 — ADR-045 + schema (migration 0026) — DONE

As-built: FK re-points done with raw-DDL table rebuilds in the migration (sqlite
FKs are unnamed — `batch_alter` can't drop them); downgrade restores the
flashcards table and re-points back. Card create/list/due/review/delete/export
all run over exercises via `services/cards.py`; exercise list/get exclude
`card_%`. Card delete now explicitly clears `review_log` (no ORM relationship
on that side).

- `exercises.kind` (string, default `multi_step` for existing rows) + kind
  registry in `app/services/exercise_kinds.py`: per kind — assessment engine,
  input widget key, validator, (for card kinds) FSRS flag. Steps already carry
  `prompt`/`expected`/`rubric` JSON — kinds formalize the *shape* of those
  payloads (pydantic schemas per kind).
- **Flashcards fold in**: a card deck becomes an exercise (`kind` = deck's card
  kind; one exercise per card set, or per card — decided in the ADR; leaning:
  one exercise per card, grouped by a `deck_ref`, so Cards tab lists decks as
  exercise groups). `fsrs_states`/`review_log` re-point from `flashcards.id` to
  `exercise_steps.id` (or a generalized owner). `flashcards` table dropped after
  migration; Anki import/export + `flashcards` generation task + FSRS engine
  keep working against the new shape. **This is the ADR-worthy decision** —
  write ADR-045 before touching the schema; quiz↔exercise boundary stays.
- `POST /exercises/generate` accepts `kinds[]`; exgen prompt per kind family;
  deterministic validators per kind (e.g. matching needs even term lists,
  ordering needs a canonical order, `error_spot` needs a flawed line index ≤
  line count). AI-assessed kinds get a rubric in `expected` + `assessment`
  written to `step_attempts.feedback` via one audited `grade.rubric` task call.

### B2 — Runner support

- Player renders per-kind input widgets behind a `ExerciseInput` dispatch
  (`kind → component`); structural widgets are new shared components
  (`MatchingPairs`, `OrderList`, `CategorizeBins`, `FillBlanks`) under
  `components/exercise-inputs/`.
- Grading: deterministic kinds extend the equivalence-chain endpoint family
  (structural compare server-side); AI kinds call the rubric task and store
  `{verdict, per-criterion, confidence}` — shown as feedback blocks; AI verdicts
  are always marked with `AiBadge`.
- Card kinds render the existing due-queue UI on top of exercise sessions
  (a "card review" = an exercise session over N scheduled cards).

### B3 — UI consolidation

- Practice tab shows one rolled-up list of exercises incl. card decks (kind
  chip + engine icon: Σ deterministic / ✦ AI / ⏱ scheduled); Cards tab becomes
  a filtered view of the same list (kind = card_*); Today due-reviews link into
  card sessions. Study launcher + GenerateDialog grow the kind picker
  (multi-select for generate).

## Slices & order

A1 FocusShell → A2 origin lib → A3 runners → A4 material drawer → A5 note/page
adoption (each shippable; A2 before A3/A4 so close-behavior lands once).
B1 ADR-045 + migration → B2 player/grading (structural batch + cards) →
B3 AI-assessed batch → B4 generate + launcher UI. A and B independent; B2's
runner work builds on A3's shell.

## Non-goals

- Merging quizzes into exercises (assessment stays separate).
- Voice/audio, `code_function` sandbox, geo/simulation canvases (◇ backlog).
- No new AI providers; rubric assessment reuses the gateway + audit trail.
- Part A does not change any backend.

## Verification per slice

Frontend `pnpm lint && pnpm typecheck && pnpm test && pnpm build`; backend
`ruff check . && mypy . && pytest` for B slices (migration round-trip fixture:
flashcards → exercises with FSRS history preserved; Anki import/export
round-trip stays green). Docs per ca-docs-sync: B changes `docs/data-model.md`,
`docs/ai.md` (rubric task), `docs/usage/exercises.md` + `flashcards.md` merge;
A changes usage docs for courses/library/quiz/exercises.
