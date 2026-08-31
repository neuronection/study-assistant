# 32 — Unified Practice section & the Practice Builder (ADR-069)

**Status:** IN PROGRESS 2026-08-22 → 2026-08-23 (32A–32C implemented in the first
pass; **32D's generate-dialog context picker shipped 2026-08-23** — material
chips + Add/Exclude pickers + searchable NotePickerDialog replace the checkbox
lists; the unified Ctrl+N creation palette is still documented-only) · **Phase:**
post-1.0 (plan 32) · user-requested

The Practice section stops being "quizzes *and* exercises as two parallel lists" and
becomes **one practice surface with one builder**. Quizzes and exercises share a list
(union of the two queries), a unified selection/menu/placement grammar, and a single
primary **New practice** action. That action opens a reworked **Practice Builder** — the
former `GenerateDialog` in a new `practice` task mode — where the student picks the
*format* from one grid that spans **quiz question types** (`single`, `multi`,
`truefalse`, `text`, `numeric`, `equation`) **and exercise kinds** (`multi_step`,
`matching`, `ordering`, `categorize`, `fill_blank`, `explain`, `error_spot`,
`correct_solution`), mixes them freely (a quiz of chosen types **plus** one exercise
per chosen kind), and can flip a **shuffle** toggle. The engines underneath are
untouched (ADR-045: quizzes and exercises remain separate assessment entities); only
the entry point and the surface merge.

## Context

Honest findings that motivate the round:

1. **The Practice tab is already a merged *tab* but two parallel *sections*.**
   `PracticeTab` (NodeWorkspace.tsx:1612) renders quizzes and exercises as two
   `EntityItems` lists with duplicated selection/move/delete/menu wiring and **two
   primary generate buttons** (`quiz.generate`, `exercises.generate`). The student sees
   "Quizzes" and "Exercises" as different kinds of thing and must choose a button
   before knowing what they want — the exact artifact the roadmap's unbuilt H12
   "variety engine" was meant to dissolve.
2. **Quiz generation has no format control.** `GenerateIn` (api/quiz.py:45) accepts
   only `count`/`difficulty`/`topic`/`skill`; `quizgen._default_blueprint`
   (pipelines/quizgen.py:25) hard-codes a fixed type cycle. A student cannot ask for "a
   quiz of only numeric + equation" or "no true/false". The exercise side already has a
   kind selector — the quiz side does not. The merge exposes this asymmetry.
3. **No shuffle exists for quizzes.** `exercise_structs.py:182` shuffles
   options/order for structural exercise kinds at generate time; quizzes have no order
   shuffle, no option shuffle, no per-attempt re-order. "Maybe shuffle" is a real,
   cheap gap.
4. **The context machinery is reusable as-is.** `GenerateDialog`
   (features/ai/GenerateDialog.tsx) already implements scope + material opt-in/out +
   notes + concepts + one-time hint + live context preview through `ContextResolver`.
   A new `practice` task mode reuses that whole section unchanged; the only new UI is
   the format picker above it. The Phase-10 machinery (`GenerateContext`, `TaskRunner`,
   audit) is untouched — no new AI plumbing.
5. **The requested materials/notes display + creation-form work is a separate, larger
   surface.** It is scoped as slice 32D below (documented, not yet implemented) so the
   practice unification ships as a coherent unit first.

## Slices

### 32A — Unified practice surface (frontend)

One list, one builder button, one grammar.

- `PracticeTab` merges the two `useQuery`s into one item array: each item carries a
  discriminator (`quiz` | `exercise`), the shared `EntityItemEntry` fields, and
  kind-specific meta. Quiz rows keep `questionCount`, exercise rows keep step count +
  difficulty badge + "similar" affordance.
- One `useSelection` over the combined key space (`quiz-{id}` / `exercise-{id}`), one
  `SelectionBar` (Move to node / Delete acting per-kind on the selected ids), one
  context menu that branches on the discriminator (quiz: open/export/.qpkg/print/
  rename/delete; exercise: open/similar/rename/delete).
- One primary **New practice** action (opens the builder, 32B) + secondary **Import**
  (quiz caq/.qpkg). `DrillsCard` stays.
- Empty states become a single practice-scoped message ("no quizzes or exercises yet —
  generate a practice set").

### 32B — Practice builder + quizgen versatility (backend + frontend)

- **Backend — quiz question-type allowlist + shuffle.** `quiz.generate` `GenerateIn`
  gains `question_types: list[str] | None` (each must be a valid `QUESTION_TYPES`
  member, else 422) and `shuffle: bool = False`. `quizgen._default_blueprint` cycles
  only through the allowlisted types (fallback to the current cycle when None) and
  `_build_prompt` states the mix; the repair-loop validator rejects drafts whose `type`
  is outside the allowlist. When `shuffle` is on, generated questions are persisted in
  randomized order (and, where legal, option order is shuffled with answers remapped).
- **Frontend — `GenerateDialog` gains a `practice` task mode.** A format picker grid
  above the existing context section: a Quiz group (question-type chips + count +
  shuffle toggle) and an Exercise group (kind chips + step count + difficulty).
  Selecting quiz types → one quiz with `question_types` (+ `shuffle`); selecting
  exercise kinds → one exercise per kind (each through its existing `exgen` pipeline).
  Mixing is free (e.g. 2 quiz types + 1 exercise kind). The context/scope/hint/preview
  section is unchanged. `GenerateResult` widens to a list of created items; the
  Practice tab navigates to the first quiz if any (runner), else closes.
- Task selectors elsewhere (`StudyLauncherDialog`, `CardsTab`) keep their single-task
  behavior unchanged.

### 32C — Runner-level shuffle (frontend)

- `QuizRunner` gains a **Shuffle** toggle (header control, persisted per activity via
  localStorage, default off). When on, question order is randomized for the attempt;
  for single/multi/truefalse, option order is randomized and the submitted choice is
  mapped back to the stored option index. Exercises already shuffle structurally at
  generate (32B/ADR-045), no player change.

### 32D — Materials/notes display + creation form

Shipped 2026-08-23 (user request): the **generate/practice dialog's context picker**
is modernized. Materials: in-scope materials stay implicitly included; only excluded
and added materials render as removable chips; **Add material…** and **Exclude from
context…** open the existing `MaterialPickerDialog` in select mode (new optional
`confirmLabel`/`lockedLabel` props). Notes: **Add note…** opens a new feature-rich
`NotePickerDialog` (fuzzy search, tag filter, multi-select check indicators, select
all shown, load-more, selected count); attached notes are removable chips. Native
checkboxes are gone from the flow (shared `CheckIndicator` replaces the MaterialRow
checkbox). Context semantics unchanged (`exclude_material_ids` /
`include_material_ids` / `note_ids`).

- Preview surfaces: grid cards gain a thumbnail of the first extraction block / first
  note block (lazy, content-addressed PNG where available).
- One **New…** creation palette (Ctrl+N) reusing the `StudyLauncherDialog` grid
  pattern so "new note / new material / new practice set / compose" is one mental
  action.
- Modernized create forms for materials/notes if the preview work leaves budget.
  **Not implemented in this round.**

## Acceptance

- One Practice list mixes quizzes + exercises with kind badges; bulk verbs and context
  menus work per kind on the union.
- One **New practice** action opens the builder; a student can generate a quiz
  restricted to chosen question types, one exercise per chosen kind, or a mix, with
  shuffle.
- A shuffled quiz re-orders questions (and legal options) per attempt without changing
  stored answers or analytics.
- Backend suite green (`ruff`, `mypy`, `pytest`); frontend suite green (`lint`,
  `typecheck`, `test`, `build`); docs synced (`ca-docs-sync`).

## Risks / non-goals

- **No table merge** (ADR-045 stands). Engines, exports (`.qpkg`/`caq/v1`), analytics,
  mistake notebook, and both runners are untouched.
- `shuffle` affects presentation only — grading/equivalence-chain logic is untouched
  (options are remapped to stored indices before submit).
- 32D is deliberately deferred; it does not block 32A–32C.

## Alternatives rejected

- A brand-new `practice_sets` container table (weeks of migration across engines,
  exports, analytics — for zero student-visible gain; ADR-045 already keeps the two
  assessment models).
- Rebuilding the builder as a separate dialog instead of a `GenerateDialog` task mode
  (would duplicate the entire context section; ADR-044 already rejected reimplementing
  GenerateDialog's scope/source/preview logic).
- Backend option-shuffle at persist time in all cases (runner-level remap is more
  flexible and keeps stored answer indices canonical).