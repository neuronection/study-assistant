# Exercises and the tutor

Exercises are multi-step guided problems — the tutor helps you *through* them without
handing over answers. They live in their course: open a course workspace
(**Courses → a course**) and switch to the **Practice** tab — that's the exercise
list, generator and drills surface, sharing one list with quizzes (kind badges
distinguish them). The old global Exercises page is gone; working
an exercise is a focused full-screen player.

## Generating exercises

**Practice tab → New practice** opens the practice builder. The **Exercises** group
of the format picker lets you pick one or more exercise kinds (guided multi-step,
matching, ordering, categorize, fill-in-the-blanks, explain-in-your-own-words,
spot-the-error, fix-the-flawed-line) — a selected kind generates one exercise of
that kind. You can mix quiz question types into the same run. Below the format
picker sit the context controls — scope (*this node only / this node and
children / whole course*), material opt-in/out chips, context notes (added via a
searchable note picker), focus concepts, a one-time instruction field and a live
**context preview** of what the AI will see. Exercises always belong to the course you have open. Generated
exercises are validated before you ever see them: every step's expected answer
must parse with the math engine — an exercise that fails is rejected, not
silently accepted.

## Similar exercises

Every exercise in the practice list has a **↻** button that generates an isomorphic
variant — the same skills and step structure with different numbers or functions.
The variant is checked to actually differ: its answers are proven non-equivalent to
the original.

## Error-pattern drills

The **Error-pattern drills** card on the practice tab lists recurring mistakes for
the course you have open — patterns come from the course type's taxonomy (math
courses seed the classic calculus patterns: missing chain-rule factor, missing
+C, sign slips, …) plus any you've approved from the AI's suggestions. Patterns
you've actually made in quizzes show a mistake count from your mistake notebook,
scoped to this course. **Drill** generates a short exercise that targets that
exact error, in the course you have open.

Two kinds of pattern are shown:

- **Seeded** — the built-in taxonomy for the course type (empty for subjects the
  app ships no taxonomy for yet).
- **Discovered for this course type** — patterns the AI found in your recent
  wrong answers and you approved.

**Find more patterns** asks the AI to look at your latest wrong answers and
propose new recurring errors. Review each suggestion and **Approve** (it joins
the card immediately) or **Dismiss** it. Only patterns you approve are added —
the AI never changes your study data on its own.

Sign-slip and dropped-factor mistakes are detected by the app's math engine as
they happen, so their counts are exact rather than guesses.

## Exercise kinds

Three kinds ask for **free-form answers graded against a rubric**:

- **Explain in your own words** — write a short explanation; the AI grades it
  against the rubric the generator built and shows the per-criterion
  rationale. Verdicts are marked *AI-graded*.
- **Spot the error** — a worked solution with exactly one flawed line; pick
  the line (checked instantly — no AI involved in the pick).
- **Fix the flawed line** — type the corrected line; an exact match is
  checked deterministically, anything else goes to the rubric grader.

Most exercises are **multi-step guided problems** (type an answer per step,
checked with the math equivalence engine). The AI can also generate four
**structural** kinds — matching pairs, ordering shuffled items, sorting items
into categories, and fill-in-the-blanks — all checked deterministically:

- When generating from the workspace or study launcher, pick the **kind**.
- Structural exercises show their own input (dropdowns, move-up/down buttons,
  category chips, or inline blank fields); **Check** enables once every part
  is filled and reports partial credit ("2/4 pairs correct") when you miss.

## Working an exercise

From the practice list, pick one. Each step shows its prompt and a math editor for
your answer. Press **Check** — the answer is verified with the same equivalence
engine as quizzes (`x + x` passes for `2x`). If you're wrong you'll see an error
class hint like *conceptual slip* or *check your notation*.

The player header shows course ▸ node and the exercise title, with **Details**
(step count, difficulty, guided/socratic mode); a step progress bar sits under it.
Closing (✕ or finishing) returns you to where you opened the exercise from, or to
its node workspace when deep-linked.

## The hint ladder

Instead of one big hint, there are five levels:

1. **Clarify** — restates the problem
2. **Nudge** — names the relevant rule or property
3. **Strategy** — an outline of the approach
4. **Partial solution** — the setup and first move
5. **Full worked solution**

Levels unlock one at a time — you can't jump to the solution without walking the
ladder.

## Ask the tutor

Next to the hint button, **Ask the tutor** opens a tutor chat about the step
you're on. It always sees the live state: your **current typed answer** (synced
every time you click the button — type, ask, refine, ask again), the step
prompt, how many attempts you've submitted and how they went. While the step
is unsolved the chat runs under a **no-answer-reveal guard** — same
deterministic check as the hint ladder — so you can ask "is my approach
right?" freely; once you solve the step (or finish the exercise) the guard
lifts.

**The hint button cannot leak the answer.** Every hint below level 5 is checked by
code: any math it contains is tested for equivalence with the step's answer, and a
hint that matches is rejected and regenerated before you ever see it. This guarantee
is deterministic (the same math engine that grades you), not a polite request to the
model.

## Independence score

When you finish an exercise you get an independence score — the fewer hints (and the
lower their levels), the higher. Every help event is recorded, so the score reflects
real self-reliance.

## Socratic mode

Start a session with Socratic mode to have the tutor respond with guiding questions
rather than statements.

## Session summary

When you finish an exercise, you can save a **session summary** — a note
recapping which steps went wrong and how many hints you needed. It's created
in the exercise's course, tagged, and linked from the completion screen.
