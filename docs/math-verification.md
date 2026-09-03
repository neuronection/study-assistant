# Math verification (the trust layer)

Deterministic math correctness is the app's backbone. Everything that compares two
mathematical answers, hints, or distractors goes through the same chain.

## The equivalence chain (G9)

`app/math/equivalence.py` — used by quiz grading, exercise steps, quizgen distractor
validation, and the hint-leak guard. A student answer is *correct* if **any** stage
proves equivalence with the expected answer:

```
1. parse        LaTeX normalization (\frac, \sqrt[n], \cdot, \times, \left/\right,
                \lvert/\rvert, \, \quad) → |…| → SymPy Abs; `A=b` equations parsed as
                `A−b`; `,`/`;`-separated systems → SymPy FiniteSet; implicit
                multiplication; bare `e` → Euler's e, bare `i` → imaginary unit;
                `\{a, b, …\}` set literals → SymPy FiniteSet (comma lists split at
                top level)
2. simplify     symbolic: simplify(student − expected) == 0; sets compare via
                simplify(a) == simplify(b) or empty symmetric difference
3. sampling     seeded random complex points (12 points, magnitude-bounded);
                both sides evaluated at every point, all must match (expressions
                only — sets short-circuit to the symbolic stage)
4. solveset     equations only (input must contain `=`): same real solution set
```

Why multiple stages: `simplify()` alone misses many equivalent calculus forms;
sampling alone can miss domain edge cases; solveset catches equation-form rewrites
but is wrong for plain expressions (any two expressions sharing root {0} would
"match" — a real bug we caught and fixed by restricting stage 4 to equation inputs).

Consequences you can rely on:

- Typing `2x` when the expected answer is `x*2` is **correct**.
- `x^2 cos(x) + 2x sin(x)` grades correct against `2*x*sin(x) + x**2*cos(x)`.
- `sin(x)` vs `cos(x)` is **wrong** (sampling separates them).
- `C + x^2` vs `x^2` is **wrong** (integration constants must be part of the key).
- Set answers are **order-insensitive**: `\{1, -1, i, -i\}` matches
  `\{-i, i, -1, 1\}` but not `\{1, i\}` — the case that used to crash exgen
  validation (found 2026-08-21, fixed in parse + symbolic stage).
- `|…|` (incl. `\left|…\right|`) parses to SymPy `Abs`, and `\ln…` maps to
  `log`, so integral answers like `\frac{1}{2}\ln|x-1|-\frac{1}{2}\ln|x+1|+C`
  validate and grade.
- `A=1/2,\;B=-1/2` (a coefficient system) parses as a FiniteSet of `A−1/2,
  B+1/2` and grades **order-insensitively** — the partial-fractions "solve for
  A and B" step now passes exgen validation (found 2026-08-23).

Numeric questions use an explicit tolerance instead (absolute or relative).

## Hint-leak guard (G11)

`app/math/leak_guard.py` + the `no_answer_reveal` contract. The guarantee: **a hint
below ladder level 5 can never contain the answer.**

1. Extract every piece of math from the hint text: `$$…$$`, `$…$`, and bare numbers.
2. Small integers (≤10) are ignored — "take the 2 functions" is not a leak.
3. Every other expression is run through the equivalence chain against the expected
   answer (multiple candidates supported — e.g. the correct option of a choice
   question); non-trivial tokens are additionally substring-checked; verbatim
   quoting of a forbidden answer text (≥8 chars) is a violation too.
4. Any match = violation → the hint is regenerated with the violation explained
   (max 2 repair rounds) before the student ever sees it.

The guard covers exercise hints, quiz-question hints (P5b practice mode), and chat
sessions bound to an open quiz attempt. Level 5 (full worked solution) is the
designed reveal point — there the guard lifts.

This is deterministic code — the same engine that grades the student checks the
tutor. It is not a prompt-level request.

## Grading paths (`app/services/grading.py`)

| Question/step type | Checker | `graded_by` |
|---|---|---|
| single, truefalse, multi (partial credit), text (normalized match) | direct | `deterministic` |
| numeric | absolute/relative tolerance | `deterministic` |
| equation (incl. MathLive input, exercise steps) | equivalence chain | `symPy` |
| numberline (quiz type + exercise step kind) | region grading (`app/math/regions.py`, below) | `deterministic` |
| table_fill | per-cell checkers (`app/math/tables.py`) | `deterministic` |
| composite (follow-through) | per-part checkers + SymPy relation recompute (`app/math/composite.py`) | `deterministic` |
| graph_read | computed-value tolerance / nearest-point match (`app/math/graphs.py`) | `deterministic` |
| code | in-page Pyodide run; backend re-verifies each captured output against the stored test (`app/math/code.py`) | `deterministic` |
| unsupported type | — | `config` (fails safe) |

Error classification for tutor steps: parse failure → `misread`, else
`procedural`/`conceptual` by the question's skill axis.

## Region grading — number-line answers (`app/math/regions.py`)

The `numberline` question type (plan 51-A, ADR-112) accepts an interactive
payload of placed points and shaded intervals:
`{points: [{value}], intervals: [{lo, hi, lo_closed, hi_closed}]}`. Grading is
pure geometry — no LLM anywhere in the verify path:

- **Points** match by nearest-within-tolerance (greedy, one-to-one).
- **Intervals** match exactly when both ends are within tolerance *and* both
  boundary kinds (open/closed) are equal; boundary-kind strictness is part of
  the concept (open vs closed endpoints of a solution set).
- **Partial credit** is the Dice coefficient of the shaded mass:
  `2 × (interval-overlap + exact-interval length + matched points) / (expected
  mass + actual mass)` — a positionally-correct interval with the wrong
  boundary type earns nothing (the strictness above), extras drag the score
  down, and disjoint regions score 0.
- **Tolerance** comes from the question (`tolerance` field) and defaults to
  0.5% of the displayed range — wide enough that every snapped click/drag on
  the number-line widget always grades, still fully deterministic. Generators
  may tighten it.
- **Error tags** (`boundary_kind`, `missed_region`, `extra_region`,
  `missed_point`, `extra_point`) flow into the mistake notebook like any other
  graded answer; the attempt report carries the exact payload for replay.

## Error-spot flaw proofing (`error_spot`, plan 51-C, ADR-114)

Finding someone else's mistake is graded without an LLM, and the flaw itself is
proven before the exercise is ever banked:

- **Proof of wrongness (generation-time)**: the generator returns both solution
  versions with per-line math answers; validators require every answer to parse
  (`parse_math`), the flawed line's answer to be **non-equivalent** to the
  correct one (equivalence chain), and every other line's answer to be
  **equivalent** between the versions — exactly one provable flaw or the draft
  is rejected into repair.
- **Detector-seeded flaws (deterministic-first)**: for patterns with a code
  detector, the flawed answer must additionally *equal the detector's
  transformation* of the correct one — `sign_slip` → `-(correct)`,
  `dropped_factor` → `<seeded factor>*(correct)` — proven by the chain at
  generation time, so the drill exercises exactly the tagged misconception.
- **Grading (student side)**: picking the flawed line is exact (deterministic);
  when the exercise requires a correction (`requires_fix`), the typed fix is
  graded by the equivalence chain against the true line's answer — right pick
  with a missing or non-equivalent fix is incorrect with feedback naming which
  half failed. Legacy pick-only responses stay deterministic. The rubric LLM
  path remains only as the fallback for malformed responses.

## Table-fill per-cell grading (`app/math/tables.py`, plan 51-F)

The `table_fill` question type grades a grid cell by cell, reusing the flat
kinds' checkers per cell — no LLM anywhere:

- Cell kinds: `text` (normalized match, optional `accept` alternatives),
  `numeric` (float match with per-cell `tolerance`, default 1e-6),
  `equation` (equivalence chain), `locked` (pre-filled display text, never
  graded — the value is public in `QuestionOut.input`).
- Partial credit = `correct fillable cells / fillable cells` (exact match →
  1.0); wrong cells tag `wrong_cell`, malformed payloads score 0 with
  `malformed`.
- Validators (generation + caq import): headers/rows non-empty and aligned
  (≤8 columns, ≤10 rows), every fillable value parses for its kind, ≥1
  fillable cell; drafts failing these go to the standard repair loop.

## Composite follow-through (`app/math/composite.py`, plan 51-E)

Multi-part questions grade per part with the flat checkers, plus one
determinism-first trick — **follow-through credit**:

- A part may declare `follow_through`: a SymPy expression over the prior
  parts' answers (symbols `a`, `b`, `c` = parts 1, 2, 3).
- **Generation-time proofs**: the relation must parse, reference only prior
  parts, reproduce the part's declared value when the declared prior answers
  are substituted, and still evaluate from a perturbed prior answer — any
  failure sends the draft to repair.
- **Grading**: a part whose prior parts were answered wrong is re-checked
  against the relation recomputed from the *student's* prior values — a correct
  derivation from a wrong value earns the part, flagged `follow_through`
  (overall correctness still requires every part). Grading itself never calls
  an LLM: text = normalized match, numeric = tolerance, equation = equivalence
  chain (on both the declared and the recomputed expectation).

## Graph-reading answers (`app/math/graphs.py`, plan 51-G)

The `graph_read` type inverts the usual trust model — the model proposes only
the *stimulus* (an expression of x, the plotted domain and the target x), and
every graded number is computed in code:

- **Data + chart**: `build_graph_data` evaluates the expression (SymPy →
  lambdify) over an evenly spaced grid (20–400 samples) and refuses
  non-finite values; the curve rides the stem as a standard plotly `chart`
  block.
- **Expected answers are computed, never authored**: value mode stores
  `value = f(point_x)` (SymPy evalf, 6 decimals) and a tolerance (declared or
  2% of the curve's y-span); point mode stores the nearest-sample index to
  `point_x`.
- **Validators**: expression parses and is finite over the whole grid,
  domain sane, target inside the domain; a *declared* value/index (e.g. from
  caq import) must match the recomputed computation — mismatch → repair.
- **Grading**: value mode = numeric tolerance against the computed value;
  point mode = exact nearest-sample index from the plotly click. No LLM in any
  grading path; image-region hotspot/label variants (arbitrary diagrams) are
  deferred until an image-authoring surface exists (plan as-built note).
