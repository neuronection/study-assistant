# Problem Desk

**Solve** in the sidebar opens the Problem Desk: one place for a single math
problem, with verified steps and a short practice set. It is course-less by
default — scratchpad notes keep anything you want to save.

## Three inputs

- **Type** — MathLive equation input with LaTeX support.
- **Paste** — paste LaTeX, a plain expression or an equation.
- **Photo** — take or choose a picture; the OCR text appears in the editor and
  can be corrected before solving. Photo recognition needs a connected vision
  model; typed and pasted solves work offline.

`Ctrl/Cmd+Enter` solves. The recognized problem is classified as simplify,
evaluate, solve, differentiate, integrate, factor or expand. Limits, definite integrals, graphs and
systems are outside this first set; they get an honest “can't verify this one”
message instead of a made-up answer.

## Verified steps

The solver is deterministic (SymPy), not an LLM. Every displayed step carries a
machine check:

- **equivalence** — the rewrite is algebraically equivalent;
- **derivative** — differentiating the result gives the input expression;
- **antiderivative** — differentiating the result gives the integrand;
- **substitution** — every computed root satisfies the original equation.

A step that fails its check is removed. If the final answer fails, the card says
so and shows no answer — it never puts a green check on unverified math. The
answer card also shows assumptions (for example the arbitrary integration
constant).

## Practise this

**Practise this** creates three similar problems from the same verified intent.
The variants are generated deterministically and graded on the server; the
answer is not sent to the page before you check. Answers accept expressions and
solution lists (for example `4, 5` or `x = 4, x = 5`). Variants are available
for the closed deterministic set; an unsupported intent says so.

## Save and history

- **Keep as note** writes the problem, answer and verified steps to a note in
  the hidden scratchpad. Deleting the solve entry leaves the note intact;
  deleting the note does not remove the entry.
- The right-hand **Recent solves** list keeps the last 20 solves with their
  input, intent and verification state.

Graphing/exploration, handwriting input and a full photo crop editor are still
planned. No Problem Desk result is written to a course question bank.
