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
| unsupported type | — | `config` (fails safe) |

Error classification for tutor steps: parse failure → `misread`, else
`procedural`/`conceptual` by the question's skill axis.
