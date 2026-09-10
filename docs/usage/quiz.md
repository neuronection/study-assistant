# Quizzes

Quizzes live in their course: open a course workspace (**Courses → a course**) and
switch to the **Practice** tab — that's where quizzes and exercises share one list
(kind badges tell them apart), with a single **New practice** generator and the quiz
import surface. The old global Quiz page is gone. Running a quiz is a focused
full-screen runner.

## Generating

**Practice tab → New practice** opens the practice builder. The **Quiz** group of the
format picker lets you choose exactly which question types you want (single choice,
multiple select, true/false, typed answer, numeric, equation — any subset, all by
default), a question count, and a **Shuffle** toggle (randomizes question order and
answer options). Below the format picker you control exactly **what the AI sees**:

- **Scope** — *this node only*, *this node and children* (default), or *whole
  course*.
- **Materials** — every in-scope material is included by default; *Exclude from
  context…* lets you opt specific ones out, *Add material…* pulls an out-of-scope
  one in. Excluded and added materials show as chips you can remove with ✕.
- **Notes as context** — *Add note…* opens a note picker (search, tag filter,
  load more) and each attached note is a removable chip.
- **Focus concepts** — tag course concepts the questions should target.
- **One-time instructions** — free text for this generation only.
- **Context preview** — a live summary (materials · excerpts · notes · concepts
  · instructions) with *show exactly what will be sent*.

You can also pick exercise kinds in the same builder — a mix generates a quiz of
your chosen question types *and* one exercise per chosen kind. The workspace
overview also has an **AI instructions for this node** card: text
saved there is applied to every AI task in that subtree automatically (the
course root's card applies to the whole course).

The generator jumps straight into the runner when it finishes. Every generated
question carries metadata (concepts, skill, Bloom level, difficulty, expected
time) — questions that fail validation are flagged *review* rather than
silently accepted. Imports (caq paste, .qpkg files, import inbox) are filed
into this course too — no course picker needed inside the workspace.

## Taking a quiz

One question per screen. Keyboard: letters A–E choose options, Enter submits.

The runner header shows where the quiz lives — course ▸ node (both clickable) and
the quiz title, with a **Details** toggle for the question count, mode and elapsed
time. Below it, a progress bar and a per-question dot strip show how far along you
are (a dot turns red when that answer was wrong). Closing (✕, or finishing the
quiz) returns you to **where you opened it from** — the practice tab, the sidebar,
Today, the palette — or, if you deep-linked straight in, to the quiz's own node
workspace.

- **Multiple choice / multi-select / true-false** — graded instantly.
- **Type-in text / numeric** — numbers accept a tolerance.
- **Equation** — a proper math editor (MathLive). Equivalence is checked with a
  computer-algebra chain: `2x`, `x*2`, `2·x` are all the same answer. Answers verified
  this way carry a *verified with SymPy* badge.
- **Write instead** (text, numeric, equation) — handwrite the answer on the canvas and
  press **Recognize**. You'll see *interpreted as* chips with what the OCR read —
  pick the right one (or fix the typed field). **Your confirmation is what gets
  graded** — the OCR only proposes; your strokes are stored with the answer.

After submitting you get the verdict plus the explanation; wrong multiple-choice
answers are tagged with the misconception they represent (you'll see these again in
the mistake notebook).

## Help inside a question (practice mode)

Practice attempts have the same hint ladder as exercises, scoped to the current
question:

- **Hint (level 1–4)** while your answer is still open — one level at a time, and the
  same leak guard applies (a hint can never contain the answer).
- After you submit, **Show full solution** unlocks the level-5 worked solution.
- **Ask about this question** opens the tutor chat with the question already in
  context. While your attempt is open, the chat is under a no-answer wrapper — it will
  guide you, not hand over the answer. The wrapper lifts once you've submitted.

Exam attempts have no help: the buttons are hidden and the server refuses help calls
outright. Every help event is recorded on your answer's transcript.

## The practice tab list

Each quiz row shows its title, the node it's placed at (scope chip) and the
question count. A single click selects (Ctrl/Shift extend, file-browser
style); **double-clicking** a row opens the runner. Every row (and grid card —
the toggle next to the section header switches list/grid) has a **⋯ menu**,
also available on **right-click**: **Open**, **Export** (`.caq.json`),
**`.qpkg`** (shareable package), **Print**, **Rename** and **Delete**
(deleting removes the quiz with its questions and attempt history). Exercise
rows in the same tab get the same treatment: Open, Generate-similar, Rename,
Delete.

## Importing and sharing (caq & qpkg formats)

Quizzes are portable in two tiers:

- **Export** — the *Export* link downloads `.caq.json` (single readable file);
  the *`.qpkg`* link downloads a **package**: a zip with a checksum manifest, the
  right shape for sharing between machines.
- **Import — paste** — Practice tab → **Import** → paste a caq/v1 document. Press
  **Validate** first: every question is checked with the same rules as generated
  ones (per-question report). Commit imports only what you've reviewed.
- **Import — package** — the **Package** tab selects a `.qpkg` file; its integrity
  is verified (tampered archives are rejected) before the same validation preview.
- **Import — inbox folder** — the **Inbox** tab shows files waiting in the app's
  import-inbox folder (path shown on screen). Anything can drop files there —
  you, a script, or an external AI agent. `AUTHORING.md` and `schema.json` inside
  the folder explain the format to agents. Files import with one tap; imported
  files are renamed `.imported`, invalid ones `.rejected` with a report beside
  them.
- **Author with AI** — the **Author with AI** tab builds a ready-to-paste prompt
  (topic, count, types, difficulty) that embeds the full format spec and every
  validation rule. Paste it into any AI, save the JSON it produces into the inbox
  folder (or paste it back), and the same validators decide.

This is the path for quizzes authored by external AI assistants. The validators
decide, not the model's confidence.

## Scores

**Scores** shows your attempt history (with scores) and the mistake notebook (every
wrong answer with its error tags, linked to the quiz).
