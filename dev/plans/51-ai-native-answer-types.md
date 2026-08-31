# Plan 51 — AI-native answer types: number-line, graph-sketch, error-spotting, code execution, composite, table-fill, visual answers, adaptive difficulty (user request 2026-08-31)

Status: planned (2026-08-31, user-approved; widened same day — see Context) · Phase: post-1.0 · Suggested order: A → C → E → F → G (independent) → D → H last (needs telemetry volume)

## Context

The post-1.0 backlog's remaining *answer-type* items (C20/C21/C14 + G7) share one
thesis: assessment should accept richer student input than text, and grade it
deterministically wherever possible. Plan 34 (ADR-071…076) built the prerequisites —
the widget block grammar, the `components/widgets/` registry, the state patch channel
(34D), and exercise-step widget recording (34E) — and explicitly named
"graph-sketch/numberline *grading* (G7/C21)" as the natural follow-on. The display
side exists (a `numberline` widget, JsxGraph boards, Plotly charts); the **answer**
side is missing for all four.

Breaking changes fine (no users). Determinism-first house rule (AGENTS.md) governs
every slice: the LLM may *author* the stimulus; grading is code.

**Widened 2026-08-31 (follow-up verification, user-approved):** the audit's first
pass checked C20/C21/C14/G7 only; re-verifying the feature catalog found five more
unplanned assessment items — **C16 composite** (follow-through credit), **C19 table
completion**, **C4 hotspot/labeling**, **C5 graph-reading**, and **C11 adaptive
difficulty** (no Elo anywhere; `QUESTION_TYPES` today =
single/multi/truefalse/text/numeric/equation) — folded in as slices E–H so the
whole answer/assessment surface lives in one round.

**ADRs recorded as slices start:**

| # | Decision |
|---|---|
| 112 | C21 number-line/coordinate answers are interactive answer widgets graded by deterministic geometric checks (point tolerance, interval containment); widget state rides the plan-34 answer/state machinery |
| 113 | G7 graph-sketch grading is **feature-based on placed keypoints** (zeros/extrema/asymptote sides marked on a grid), compared against SymPy-extracted features of the target function — freehand-curve recognition is explicitly out (v1) |
| 114 | C20 error-spotting exercises seed flaws deterministically from `error_patterns` where a detector exists; LLM-proposed flaws are admitted only after equivalence-chain proof that the flawed step is *wrong* (non-equivalent) while every other step stays right |
| 115 | C14 code execution runs student code in **Pyodide (WASM) inside the webview** — no server-side execution, no subprocess sandboxing, works identically in web and desktop shells, offline-capable |
| 122 | C16 composite questions: one stem, ordered sub-questions, **follow-through credit** computed deterministically — SymPy recomputes a later part's expected answer from the student's earlier value where the question declares the relation |
| 123 | C19 table completion: per-cell graded grids (per-cell input kind declared in the question schema: text/numeric/equation), partial credit per cell |
| 124 | C4/C5 visual answers: hotspot/diagram-label selection and graph-reading over server-computed chart data — graded deterministically from the question schema, never by the model |
| 125 | C11 adaptive difficulty: item-level Elo on graded attempts (deterministic update, exam attempts excluded), consumed by generation targeting and bank quality flags |

## A — Number-line & region answers (C21, ADR-112)

**Problem.** Inequalities, intervals, solution sets and number-line reasoning can
only be answered by typing math; clicking/shading is how students actually think
about them.

**Design.**

- The existing `numberline` display widget grows an **interactive answer mode**
  (`components/widgets/` registry, mirroring ADR-075's exercise-widget pattern):
  click to place points, drag endpoints to shade intervals (open/closed toggle),
  multiple regions per answer. Answer payload = normalized JSON
  (`{points: [{value, kind}], intervals: [{lo, hi, kind}]}`) stored on the
  attempt/step answer like any other answer shape (quiz answers JSON column;
  `step_attempts` already record state — 34E).
- Quiz question type `numberline` + exercise step input kind `numberline`:
  - **Generation**: quizgen/exgen prompts may propose numberline questions; the
    deterministic validators check the expected answer parses into the payload
    schema (points/intervals within domain bounds) — invalid drafts go to repair.
  - **Grading** (`services/grading.py` or a new `math/regions.py`): pure
    deterministic — point match within `tolerance` (question field, default
    1e-6 of range), interval containment both directions with boundary-kind
    (open/closed) strictness, symmetric set difference scored for partial credit.
    No LLM in the grading path.
- Rendering in stems, runners, review/score pages via the existing widget renderer.

**Accept.** A generated quiz question "shade the solution set of |x−2| < 3" is
answered by dragging (−1, 5) open interval on a numberline; partial shading earns
partial credit; the score page replays the exact shaded answer.

**Tests.** Backend: payload schema validation, grading matrix (exact/partial/boundary
kind/tolerance edges), generator validator + repair loop with fake gateway. Frontend:
widget interaction → payload, runner + review rendering.

## B — Graph-sketch grading on placed keypoints (G7, ADR-113)

**Problem.** "Sketch f(x) = …" — the classic calculus task — has no answer path
today (G7, P2 since day one).

**Design.**

- Honest v1 (ADR-113): the student **places feature keypoints on a coordinate grid**
  — zeros (x-intercepts), local extrema (max/min), y-intercept, and asymptote
  designations (vertical x = c; horizontal y = L) — rather than drawing a freehand
  curve. Keypoint placement exercises the same skill discrimination with fully
  deterministic grading; freehand curve recognition (stroke → curve fitting →
  feature extraction) is a v2 with its own accuracy risks.
- JsxGraph board (already bundled) in an answer-widget mode: snap-to-grid, per-keypoint
  type selector, delete/move; payload = typed keypoints JSON.
- Grading: SymPy computes the target's true features (`solve(f=0)`, `f'` critical
  points + second-derivative classification, `limit`-based asymptotes) → compare
  placed vs true with tolerance (x-positions within tolerance, type must match,
  missing/extra features scored). All deterministic; a human-readable feature
  comparison renders in feedback ("you marked a minimum at x≈1 — f has a maximum
  there").
- Quiz type `graph_sketch` + exercise step kind; generator proposes target functions
  with validators (features must be finite in the displayed window, ≤6 keypoints,
  no degenerate all-zero function).
- Reuses 34E step-widget recording; attempts replay the placed sketch.

**Accept.** A generated "sketch x³−3x" question is answered by placing two extrema
and three zeros on the grid; grading marks the misplaced extremum type wrong with
the exact correct features shown; a wrong-function question (features unreachable)
is rejected by validators before it ever reaches a student.

**Tests.** Backend: SymPy feature extraction over a fixture function set
(incl. asymptote/edge cases), comparison scoring matrix, generator validators.
Frontend: board interaction, payload, replay.

## C — Error-spotting exercises (C20, ADR-114)

**Problem.** Finding *someone else's* mistake is a distinct, trainable skill; the
error-pattern taxonomy (plan 28, ADR-063) already knows the classic flaws but nothing
tests against them directly.

**Design.**

- New exercise kind `error_spot` (registry, ADR-045 pattern): the stimulus is a
  worked solution (3–6 steps) with exactly one flawed step; the student marks the
  faulty step and (optionally, per question flag) supplies the correction.
- **Deterministic-first seeding (ADR-114)**: when the pattern has a code detector
  (`sign_slip`, `dropped_factor` — both proven by the equivalence chain at grade
  time today), the generator *applies the transformation to a correct solution's
  step* and the graders know the detector: marking the right step is deterministic;
  the correction is graded by the equivalence chain against the true step. No LLM
  in the verify path.
- **LLM-proposed flaws** (patterns without detectors): the generator must return
  *both* solution versions; validators prove via the equivalence chain that (a)
  step_i^flawed ≢ step_i^correct, (b) all other steps are pairwise equivalent, (c)
  the flawed final answer is non-equivalent to the correct one — any failure goes to
  repair, then rejection. This is the G11-style guarantee, inverted: proof of
  *wrongness*.
- Grading: step choice deterministic (right/wrong); correction graded by the chain;
  partial credit when only the correction is missed. Attempts feed the same
  error-pattern stats (spotting your own vs others' mistakes tracked separately on
  the drill card).

**Accept.** Generate an error-spot exercise from the "dropped factor" pattern → the
flawed step is provably wrong; marking step 3 and typing the corrected factor
grades deterministically; the mistake notebook gains a "spotted in practice" tag
distinct from own mistakes.

**Tests.** Backend: seeded-flaw determinism per detector, LLM-flaw validator matrix
(a/b/c proofs), grading paths, kind registry wiring, generation with fake gateway.

## D — Code-execution questions in Pyodide (C14, ADR-115)

**Problem.** Programming courses (subject-agnostic by design) need "write code that
does X" questions; the obvious implementation — server subprocess — is a sandboxing
liability in a local app that also runs in browsers via webapp mode.

**Design.**

- ADR-115: student code executes in **Pyodide (CPython → WASM) in the webview**,
  lazy-loaded (~10 MB chunk, loaded only when a code question opens). No server
  execution path exists at all; the backend never sees code, only the graded
  outcome payload. Works identically in desktop shell, webapp, and (future) pure
  browser hosting; fully offline.
- Question type `code`: prompt + optional starter code + test cases (stdin/args →
  expected stdout/return, or pytest-style asserts run in-page). Runner: mount
  Pyodide, apply per-case execution with timeout (Pyodide interrupt buffer), capture
  stdout/return, compare with normalization (trailing whitespace, float format
  tolerance field). Payload = per-case pass/fail + captured output; grading is
  deterministic matching, no LLM.
- Generators may propose `code` questions for `programming`-type courses; validators
  run the reference solution against the tests **once at generation review time**
  (in the same in-page runner via a "test this question" affordance — the generator
  pipeline stores the reference solution; validation happens when the author
  previews, keeping the backend out of execution).
- Honest limits recorded in docs: no third-party wheels beyond the Pyodide stdlib +
  bundled set v1 (numpy available in the standard Pyodide distribution — decide at
  implementation; document whatever ships), execution timeout fixed (no infinite
  loops), no filesystem/network access (Pyodide defaults).

**Accept.** A programming course generates a "write `is_palindrome(s)`" question
with 4 test cases; the answer runs in-page with a 5-second cap, three cases pass
with visible stdout diff on the failing one; nothing ever executes on the backend.

**Tests.** Backend: question schema + payload storage + deterministic matcher unit
tests (normalization, tolerance), generator validators. Frontend: Pyodide runner
harness (mocked wheel load in unit tests; the real runtime exercised in the slice's
manual verification + optionally one Playwright e2e spec once plan 50C lands),
timeout path, output rendering.

## E — Composite questions with follow-through credit (C16, ADR-122)

**Problem.** Multi-part problems ("(a) differentiate, (b) find the maximum using
(a)") are the standard exam format; today each part would be a separate question
and a wrong (a) unfairly sinks (b).

**Design.**

- Question kind `composite`: one stem + 2–4 ordered sub-questions, each with its
  own input kind (from the existing type registry) and expected answer. The schema
  carries an optional per-part `follow_through` relation — a SymPy-parseable
  expression over prior parts' symbols (e.g. part (b)'s expected = f(part_a_value)).
- **Deterministic follow-through (ADR-122):** when part (a) is answered wrong, part
  (b)'s expected is recomputed by substituting the *student's* (a) value into the
  relation and re-running the equivalence chain — a correct derivation from a wrong
  value earns credit, flagged `follow_through` in the verdict (and in analytics as
  its own skill signal, distinct from blind correctness).
- Validators: relation must be parseable; recomputation from a perturbed prior
  answer must succeed at generation-review time (the generator's draft is rejected
  into repair if the relation doesn't evaluate).
- Runner UI: parts on one question screen with per-part inputs and per-part
  verdicts; score page + History show the per-part breakdown and follow-through
  flags.

**Accept.** A wrong (a) answer still earns (b) when (b) is computed correctly from
the wrong value, visibly flagged "follow-through"; the score page shows
(a) ✗ · (b) ✓(follow-through).

**Tests.** Backend: per-part grading matrix, relation substitution + chain
recompute, validator repair path, partial-credit accounting, analytics write.
Frontend: composite runner screen, per-part review rendering.

## F — Table / matrix completion (C19, ADR-123)

**Problem.** Truth tables, value tables and matrices can't be answered today.

**Design.**

- Question kind `table_fill`: schema declares the grid (headers, locked cells,
  fillable cells with per-cell input kind text/numeric/equation + per-cell
  tolerance where numeric). Answer payload = cell-value map; grading is per-cell
  through the same checkers as the flat kinds (exact / chain / tolerance), partial
  credit = fraction of correct cells.
- quizgen/exgen support with validators (≥1 fillable cell; every expected value
  parses per its declared kind).
- Runner renders an HTML table with inputs in the fillable cells; review/score
  replays the filled grid with per-cell verdicts; plan 53-F's print templates get
  the empty grid (paper) and filled grid (key) variants for free.

**Accept.** A generated truth-table question is answered cell by cell, graded
per-cell with partial credit, and prints as a worksheet.

**Tests.** Backend: schema validation, per-cell grading matrix, partial credit,
generator validators. Frontend: grid interaction, replay, print variants.

## G — Visual answers: hotspot, labeling, graph-reading (C4/C5, ADR-124)

**Problem.** "Click the local maximum on this graph", "label the diagram",
"read the value off this chart" — the stimulus-visual answer surface is missing.

**Design.**

- **C4 hotspot / diagram-label**: the question schema references an image blob
  (material/original) + normalized-coordinate regions (points or rectangles).
  Two answer modes: *select* (click the region(s) — grading = exact set match) and
  *label* (drag the given labels onto marked hotspots — grading = correct
  assignment per hotspot). Region definitions may be authored by a vision-capable
  model at generation time; validators check bounds/overlap/min-count, and the
  author previews/adjusts them (the reviewer confirms regions before the question
  banks — no invisible auto-generated geometry).
- **C5 graph-reading**: the stem embeds a `chart` block whose plotly data is
  **server-computed** (the plan-34 PLOT machinery / deterministic data, never
  model-authored numbers). Answer forms: read-a-value (numeric with tolerance),
  multiple-choice trend/shape, or click-a-point on the chart (widget answer
  payload → nearest-data-point match within tolerance). Grading comes from the
  underlying data table, not the pixels.
- Both ride slice A's answer-payload machinery (attempt storage, review replay).

**Accept.** A generated "click where f′(x)=0" hotspot question and a "read f(2)
from the chart" question both grade deterministically; mislabeled hotspots show
the correct assignment in review.

**Tests.** Backend: region/label schema validation + grading matrices, chart-data
answer tolerance matching, vision-proposal validators (bounds/overlap). Frontend:
click/select/label interactions on image and chart widgets, replay.

## H — Adaptive difficulty via item-level Elo (C11, ADR-125)

**Problem.** Quizzes are static difficulty; the bank knows question metadata but
nothing adapts to the student.

**Design.**

- **Item-level Elo** (ADR-125): every graded answer updates the question's rating
  and (per concept×skill cell) the student's rating — deterministic Elo update
  (expected score from rating difference, K declining with the question's attempt
  count; seeded at generation-difficulty prior). Stored additively on `item_stats`
  (migration 0051's neighbor — `rating`, `rating_count` columns) and on the
  concept-skill stats row. Exam attempts excluded (house rule); quiz-me and drill
  answers count like any graded answer.
- Consumers: quizgen **difficulty targeting** (blueprints prefer bank questions
  near the student's cell rating ± band when a concept/skill focus is set), the
  session variety engine's difficulty ramps (H12 adjacency), and enriched bank
  flags (the item-analysis `review` flag gains an Elo-outlier reason: too-hard /
  too-easy vs its declared difficulty).
- New questions still dominate early (low attempt count = wide uncertainty shown
  in the bank UI as "estimating").

**Accept.** A student strong in derivatives gets progressively harder derivative
questions in focused sessions without any config; a question whose Elo diverges
wildly from its declared difficulty gets flagged in the bank.

**Tests.** Backend: Elo update math (fixtures), exam exclusion, targeting selection
boundaries, flag thresholds. Frontend: none beyond bank flag display.

## Non-goals (this round)

- Freehand-curve sketch grading (ADR-113 v1 is keypoint-based; stroke recognition is
  its own plan with its own evals).
- Server-side or Docker-based code execution (ADR-115: none, ever, in this app).
- Multi-file/IDE-style code questions (single-snippet v1).
- Non-Python languages (Pyodide is Python; JS execution could reuse the webview
  itself but is a separate decision).
- Grading *code style* with LLMs (deterministic tests only; rubric kind already
  covers prose-style feedback elsewhere).
- Full CAT (computerized-adaptive testing) selection theory — ADR-125 is Elo
  targeting over the existing bank, not item-response-theory exposure control.

## Dependencies & suggested order

A, C, E, F, G independent — A/C cheapest, land first. G rides A's answer-payload
machinery. B builds on A's grid/widget groundwork (largest lift). D independent;
benefits from plan 50C's Playwright harness for one e2e spec (soft dependency, not
blocking). **H last** — it needs graded-attempt telemetry volume to mean anything.

## Verification per slice

Backend: `ruff check . && mypy . && pytest` · Frontend: `pnpm lint && pnpm typecheck &&
pnpm test && pnpm build` · golden evals (`pytest tests/evals/`) for any generator
prompt change in A/B/C/D. Docs duty: `docs/features.md` (C14/C20/C21/G7 rows),
`docs/math-verification.md` (region/feature grading + flaw-proofing), `docs/ai.md`
(generator contracts), `docs/STATUS.md` changelog + module rows each slice.
