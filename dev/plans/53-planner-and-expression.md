# Plan 53 — Planner & expression: study planner, exam forecast, quiz-me, teach-back, read-aloud, print engine (user request 2026-08-31)

Status: planned (2026-08-31, user-approved) · Phase: post-1.0 · Suggested order: A → B → C → D → E → F (A/B share the exam signal; C–F independent)

## Context

The 2026-08-31 audit's "still missing after 47–51" list, in one round. The app knows
*how* the student performs (diagnostics) and — after plan 49 — *how long* they study
(study_sessions), but not yet *what to do when*: no planner turns exam dates +
coverage into a schedule (H5 was P1 in the vision doc and never shipped), the exam
forecast is a coverage bar rather than a mastery-weighted readiness signal (H6), and
four expression/interaction gaps remain: no Quiz-me mode (F5), no teach-back flow,
no TTS read-aloud (I14), and print is raw `window.print()` on two surfaces instead
of a real export path (I16).

**ADRs recorded as slices start:**

| # | Decision |
|---|---|
| 118 | Planner items are plain user-owned rows; the AI **drafts** plans (spacing by pace arithmetic, never a constraint solver) as editable suggestions — no scheduler engine, no recurring-rules mini-language |
| 119 | Read-aloud = a `speech` capability + `tts` task through the normal chain (provider-native endpoints, audio ephemeral like transcribe's inverse), with the browser's `speechSynthesis` as the zero-config fallback |
| 120 | The print engine is **print-HTML templates + the browser's print-to-PDF** (KaTeX renders natively); no weasyprint/Typst bundling — local-first, zero new heavy deps |
| 121 | Quiz-me grading is deterministic: the model asks via a `QUIZ` tool call carrying the expected answer; **the server grades through the equivalence chain / exact match** and returns the verdict — the model never grades |

## A — Study planner (H5) (ADR-118)

**Problem.** Exam date + coverage exist; no deadline-aware plan tells the student
what to do on Tuesday.

**Design.**

- Migration **0051**: `plan_items` (id, profile_id, course_id, node_id nullable,
  title, kind ∈ `study|practice|review|milestone`, due_date, done_at nullable,
  origin ∈ `manual|draft`, sort_key). Course purge removes items; profile-scoped
  queries like all user content.
- Backend: CRUD + `POST /courses/{id}/plan/generate` — **deterministic drafting**
  (no LLM): takes exam_date + the tree's coverage/telemetry (nodes untouched,
  weak cells from the existing diagnostics) and paces remaining nodes across the
  days left (the plan-22 H1 pace arithmetic generalized), emitting `draft` items
  ("Study: Chapter 3 — Limits", "Practice: weak concept x", weekly `review`
  milestones). Generated items land as *suggestions*: the UI shows Draft n items →
  Keep / discard individually. Re-generate respects done/manual items.
- Frontend: **Planner tab** — where? A course-level Planner tab on the workspace
  root (8th pill, root-only like Settings) + an aggregate **upcoming strip on Home**
  (next 7 days across courses). Views: week list (default) + all-upcoming list;
  check-off, drag to reschedule (date bump), add/edit manually, "generate plan"
  button on courses with an exam date (else a hint to set one). Completed items
  feed the existing streak/day signals (they log `study_sessions`-style activity
  via the plan-49 kinds where applicable — checking off is honest bookkeeping,
  not fake time).
- Today integration: overdue/today items join the next-best-action cards with
  evidence ("Exam in 9 days · 3 nodes untouched").

**Accept.** Set an exam 3 weeks out on a half-covered course → generate → a spaced
draft plan appears; keep it; Home shows today's two items; checking them off and
re-opening the planner keeps the history while re-generate fills only the future.

**Tests.** Backend: CRUD, generator math (pace boundaries: 0 days left, more nodes
than days, done/manual respect), purge, aggregation endpoint for the Home strip.
Frontend: week view, draft keep/discard, drag-reschedule, Home strip.

## B — Exam-readiness forecast (H6) (ADR-118)

**Problem.** `exam_status` (`services/metrics.py:407`) reports coverage % + pace;
"am I going to be ready?" deserves a mastery-weighted answer.

**Design.**

- Extend `exam_status` with a per-course **readiness estimate**: weighted mix of
  coverage (untouched nodes), mastery (concept_skill_stats / weakness matrix cells
  under the exam scope), and recent performance trend (accuracy over the last N
  answers in-scope) — arithmetic over existing data, no new model, documented
  formula in doc 10. Output: score 0–100 + a one-line trajectory ("↑ improving")
  + the 3 weakest in-scope concepts as the reason line (evidence lines per house
  style).
- Surfacing: the Home exam card gains the readiness ring + trajectory; the
  Planner tab header shows it beside the generate button; plan generation (slice A)
  biases weak-concept items first when a forecast exists.
- Honesty rules: <3 answers in scope → "not enough data" (the diagnostics
  precedent), no score theater.

**Accept.** Two courses 10 days out: one shows 72 · ↑ with "weakest: integration
by parts", the other shows the not-enough-data state — and the first one's plan
drafts extra practice on the named concept.

**Tests.** Backend: formula math (fixtures with known inputs), not-enough-data
gate, trend direction, plan bias integration. Frontend: ring/trajectory rendering,
empty state.

## C — Quiz-me chat mode (F5) (ADR-121)

**Problem.** The tutor answers questions; sometimes the student wants the reverse —
the AI interrogates *them*.

**Design.**

- New `QUIZ` chat tool (CHAT_TOOL_CATALOG, prompt + native schemas per ADR-082):
  the model calls `QUIZ {question, expected_latex?, expected_text?, accept?: string[], choices?[]}`
  when in quiz-me mode. The server **holds the expected answer out of the prompt
  stream**, renders an interactive question card (choice buttons or a math/text
  input — the 34D widget/state channel carries the answer back), grades
  **deterministically**: choices → exact match; free text → the equivalence chain
  when `expected_latex` is present, else normalized match against `expected_text`
  plus the model's pre-authorized `accept` variants (a fixed list at question time —
  synonyms are admitted, paraphrase-*judging* is not); then feeds only
  the verdict + the user's answer back to the model as the tool result (it never
  sees the expected answer, so it can't leak it — the G11 guarantee by construction).
- Mode surface: a chat header toggle **Quiz-me** (per-session flag on
  `chat_sessions`, like `use_embeddings` 0039 precedent) that swaps the system
  prompt (Socratic-but-assessing: one question at a time, escalate difficulty, no
  multi-question dumps) and enables the tool. Works node-scoped (the existing node
  binding scopes what it asks about).
- Audited end to end (tool calls, verdicts, answers → `ai_interactions` + message
  `tool_calls`), streak/goal credit: graded quiz-me answers count as answers
  (H4b telemetry) — flagged `source=quizme` in the attempt-ish record on the
  message trace, keeping analytics honest about what was practiced.

**Accept.** Toggle Quiz-me in a calculus node chat → the tutor asks one limit
question; typing the answer grades instantly (correct/incorrect with the server's
verdict card), the tutor follows up harder; the answer lands in the daily answer
count.

**Tests.** Backend: tool execution + grading matrix (choice/latex-chain/text),
expected-answer non-leak (assert it never enters any prompt payload), session flag,
telemetry writes, budget/round caps. Frontend: toggle, question card, verdict card,
answer-count integration.

## D — Teach-back (explain-it-back) flow

**Problem.** Explaining in your own words is the strongest self-test; there's no
first-class flow (rubric grading exists buried in `explain` exercises).

**Design.**

- Thin composition, no new grading engine: a **Teach-back** action on concepts
  (Concepts tab rows + weakness-matrix cells) and workspace nodes → opens the
  exercise player's `explain` kind pre-seeded ("Explain X as if teaching a
  classmate") → existing `grade.freeform` rubric path returns criterion feedback +
  margin comments (AI-graded badge is already honest).
- Concept teach-backs write their rubric result onto `concept_skill_stats` as an
  `explanation` skill sample (the weakness matrix gains a row signal that
  explanation was practiced, distinguishable from procedural answers).
- Home recommendation: after 2+ weak-cell drill sessions, the engine may suggest
  "Teach back: <concept>" (one card type, evidence = the weak cell).

**Accept.** Click Teach-back on a weak concept → explain in two sentences →
criterion-level feedback ("definition correct; missed the geometric intuition")
with the AI-graded badge; the concept's matrix cell notes the practice.

**Tests.** Backend: seeded-explain exercise creation from concept/node, rubric
result → concept_skill_stats write, recommendation card gating. Frontend: entry
points + result rendering (existing player surface reused).

## E — TTS read-aloud (I14) (ADR-119)

**Problem.** Audio learners and accessibility: no read-aloud anywhere.

**Design.**

- Backend: `speech` capability + `tts` task (chain-resolved like `transcribe`);
  `LLMGateway.speak(text, voice?)` — OpenAI-compatible `POST /audio/speech`
  (mp3 bytes); Gemini TTS via `generateContent` audio-out where the model supports
  it; Anthropic unsupported error. Audio is **ephemeral** (streamed to the client,
  never stored; `ai_interactions` ledger row with char count). Text cap mirrors
  transcribe's honesty (e.g. ≤10k chars/utterance, longer text = chunk client-side).
- Frontend: **zero-config fallback first** — the browser's `speechSynthesis`
  (Web Speech API) drives read-aloud with no setup — **feature-detected**
  (revision 2026-08-31): WebKitGTK's Web Speech support is unreliable/absent, so
  when `speechSynthesis` is missing (desktop shell) the ▶ buttons hide with an
  honest hint pointing at the provider path (the dictation-unsupported precedent);
  webapp mode in real browsers keeps the free fallback. The provider task is the
  quality option when assigned (Settings → Tasks shows the tts row
  with the unassigned nudge like embeddings). Read-aloud buttons (▶) on: extraction
  reading view (per-block and whole), note editor preview, chat assistant messages
  (finalized text), lessons (plan 52). Playback bar with stop/speed; math blocks
  read as best-effort text (LaTeX stripped to readable form — deterministic
  strip-and-speak helper, no model round-trip).

**Accept.** Open a lesson, hit ▶ → the browser reads it aloud in webapp mode with
no provider configured; assign a provider TTS model → same button uses the natural
voice.

**Tests.** Backend: task/capability wiring, endpoint (429/409/502 mappings like
transcribe), ledger, chunking cap. Frontend: speechSynthesis harness (mock),
provider path, math-strip helper unit tests, playback bar.

## F — Print/PDF export engine (I16) (ADR-120)

**Problem.** Printing is ad hoc (`?print=` on notes, quiz print menu) with no
templates: no flashcard cut-out sheets, no exam-style paper with/without answer
key, no cheat-sheet booklet form.

**Design.**

- ADR-120: the engine is **dedicated print-HTML routes + print CSS + the browser's
  print-to-PDF** — KaTeX/Mermaid render natively in the webview/browser, zero new
  backend deps (weasyprint/Typst rejected: C/binary bundling for what the user's
  browser already does better, and print-to-PDF is interactive — margins/paper
  choice stay with the user).
- `components/print/` template kit (one `PrintDoc` shell: cover line, course/node
  context, page-break rules, print stylesheet in `print.css`) + surfaces:
  - **Quiz paper** (`/quiz/$id?print=paper|key`): exam-style paper (no feedback
    UI, answer lines) and answer key variant — replaces the current navigate-and-
    print hack.
  - **Flashcard sheets** (`/review?print=…` or practice cards segment): cut-out
    grid (front/back or fold style) over the selected scope (course/node/due set).
  - **Cheat sheet / formula sheet / lesson / study guide**: the existing materials
    get a uniform **Print** action on the extraction view ( PrintDoc shell).
  - **Planner week sheet** (slice A): one-page week view.
- Each surface renders in a dedicated print route/param that strips the app chrome
  (print CSS already hides it) and auto-opens the print dialog on `?autoprint=1`
  (the note `?print=` precedent, generalized).
- **Desktop verification built in** (revision 2026-08-31): `window.print()` in
  WebKitGTK opens the GTK print dialog (export-to-PDF included) — verify per
  surface during implementation; if the GTK PDF output ever mangles KaTeX fonts,
  the documented honest fallback in `docs/usage/printing.md` is "print from webapp
  mode" (feature-detect note, not a blocker).

**Accept.** Print a 20-question quiz as a paper without answers and separately the
key; print this week's due flashcards as a fold-over cut-out sheet; all exports
come out of the native print dialog as PDFs with correct math.

**Tests.** Frontend: template components (structure, page-break classes,
answer-key omission), autoprint param behavior, route wiring per surface. Backend:
none beyond fixture endpoints already existing (verification = existing suites).

## Non-goals (this round)

- Constraint-solver scheduling / calendar-file (ICS) round-trip / notifications
  (ADR-118: drafted suggestions only; revisit on demand).
- Server-side PDF rendering (headless chromium in CI for byte-PDF artifacts) —
  browser print covers the local-first need; revisit only for shareable static
  exports.
- Grading quiz-me free text with an LLM (ADR-121: never; rubric path exists for
  prose-style assessment via exercises).
- TTS voice cloning / per-voice downloads (provider-managed voices only).
- Flashcard *handwriting* print styles (ink-friendly template is part of F, dual-
  sided duplex alignment perfectionism is not).
- Mobile/responsive print targets (desktop print only, per the local-first shell).

## Dependencies & suggested order

A → B (B's forecast biases A's drafts; A's pace math is B's base). C–F independent
of A/B and each other; F's planner sheet depends on A's data model (small).

## Verification per slice

Backend: `ruff check . && mypy . && pytest` · Frontend: `pnpm lint && pnpm typecheck &&
pnpm test && pnpm build`. Docs duty: `docs/usage/progress.md` (planner, forecast),
`docs/usage/chat.md` (quiz-me), `docs/features.md` (H5/H6/F5/I14/I16 rows),
`docs/ai.md` (QUIZ tool + tts task), new `docs/usage/printing.md`, `docs/data-model.md`
(0051), `docs/STATUS.md` changelog + module rows each slice.
