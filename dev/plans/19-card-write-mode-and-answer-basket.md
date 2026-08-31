# 19 — Card write mode, answer-format basket & the Review tab

**Status:** plan drafted (2026-08-21, user-approved direction); implementation not started
**Phase:** post-1.0 polish (follows plan 18)
**Inputs:** user feedback round 2 — (1) cards were self-grade-only ("scope of app is for
user to write answers guided with AI; it should keep the answer"), (2) answers should have
a **basket of valid capture formats** per item with only valid ones active, (3) concern:
does typing make cards indistinguishable from quizzes? (answered: no — scheduling/
purpose/grading semantics differ; typed retrieval is *stronger* for cards; the risk is
queue fatigue, solved by adaptive default), (4) cards should live under practice →
resolved as **Practice | Review tab split** (activity-primary naming, Flashcards page
retired).

## Design decisions (user-approved)

- **Cards get write mode** — the student produces an answer (typed/handwritten) before
  revealing; correctness **pre-selects** the FSRS self-rating, which stays authoritative.
  Adaptive default: write mode ON for new/learning/hard cards (production where it
  matters), self-grade for mature review-state laps; always toggleable per session.
- **Answer-format basket**: `answer_format` (what the correct answer *is*) declares the
  valid **input modalities** (how the student captures theirs). Backend declares
  `accepted_modalities` on every answerable surface — the UI never guesses, invalid
  modalities simply don't render. Every modality produces the same canonical response
  shape the existing graders already consume; grading itself does not change.
- **Review tab**: workspace tabs become Practice | Review; Review absorbs the
  Flashcards page (queue scoped to node, card list, Anki import/export) and the rail
  loses the Flashcards nav item (Study = Home only, or Home + nothing — see slice 0).
  Quizzes/exercises stay on Practice. Quick-in/quick-out review loop is preserved via
  deep links (Today, tree due badges, palette) landing directly in Review.
- **Answers are kept**: every review stores the produced answer + verdict on
  `review_log`; per-card history surfaces "what you said last time" (a study signal in
  itself and the input for future mistake-driven cards).

## Compatibility matrix (the basket)

| answer_format | accepted modalities | canonical response |
|---|---|---|
| `math` | `mathlive`, `text`, `stylus` | string (LaTeX/sympy-parseable) |
| `numeric` | `text`, `stylus` | string |
| `short_text` / `cloze` | `text`, `stylus` | string |
| `essay` | `richtext`, `stylus` | string (markdown) |
| `choice` | `choice` | number / number[] |
| `truefalse` | `choice` | boolean |
| `structural` (matching/ordering/categorize/fill_blank) | `structural` | list |
| `none` (plain cards without a checkable back) | `self` | — (reveal + self-rate only) |

Modalities: `mathlive` = MathLive editor; `text` = plain input; `richtext` =
MarkdownEditor (lazy); `stylus` = DrawCanvas → `POST /quiz/recognize` → "interpreted as"
chips, student confirms (existing shared components); `choice`/`structural` = existing
widgets; `self` = reveal-only.

User preference (`cards.inputModality`, localStorage, Settings later): used when valid,
else the first valid modality activates.

---

## Slices

### 0 — Review tab + Flashcards page retirement

- `NodeWorkspace` TABS: `practice`, `cards` → `practice`, `review` (redirect `?tab=cards`
  → `?tab=review` for one release).
- Review tab = ReviewQueue (node-scoped, from plan 18 follow-up) + card list + Anki
  import/export buttons (moved from FlashcardsPage).
- `FlashcardsPage` + `/flashcards` route retired; rail Study group drops the item
  (Study = Home). Palette/Today/tree due badges redirect to `/courses/{cid}?tab=review`
  (root) or the node workspace Review tab. `WorkspaceGate` case gone.
- i18n cleanup (`nav.flashcards`, `cards.title` where dead).

**Accept.** `/courses/1?tab=review` shows queue + list + Anki tools; `/flashcards`
redirects; rail has no Flashcards item; deep links land in Review.
**Tests.** NodeWorkspace Review tab render; redirect; AppShell rail shape; palette/Today
link targets.

### 1 — Backend: answer specs + stored answers

- `AnswerSpec` derivation in `services/exercise_kinds.py` (or a small
  `services/answer_format.py`): per card/step → `{answer_format, accepted_modalities}`
  from kind + expected shape (`math` if back parses as math & front is a math prompt —
  generation already tags this; `cloze` if cloze deletion; `essay` when back is long
  free-form; `none` fallback).
- `CardOut`/step `input` gains `answer: {format, modalities}`; quiz question payloads
  gain the same (single source — quiz types map 1:1: equation→math, numeric→numeric,
  text→short_text, single/multi→choice, truefalse→truefalse).
- Migration **0027**: `review_log.answer` (text, nullable), `review_log.verdict`
  (string, nullable: correct|partial|incorrect|self), `review_log.input_modality`
  (string, nullable).
- `POST /flashcards/{id}/review` accepts optional `answer` (+modality): runs the
  deterministic check for the format (equivalence chain for math, normalized match for
  short_text/cloze alternatives, numeric tolerance; structural already structural),
  rubric grader only for `essay`; stores answer+verdict; response gains
  `{verdict, expected?, suggested_rating}` (rating stays client-sent; the response
  merely pre-selects). `self` format and reveal-only flows unchanged.
- Answer history: `GET /flashcards/{id}/reviews` → last N {answer, verdict, rating,
  reviewed_at}.

**Accept.** Review with `answer` returns verdict + suggested rating and stores both;
`GET .../reviews` lists them; `none` cards ignore answer.
**Tests.** Backend: verdict/suggestion per format (math equivalence, cloze alt-match,
essay rubric, none), 0027 round-trip (answer survives), history endpoint, quiz payload
answer specs.

### 2 — Frontend: the basket + card write mode

- `components/answer-input/` — `AnswerInput` dispatcher + modality components:
  `MathInput` (existing), `TextInput`, `RichtextInput` (lazy MarkdownEditor),
  `StylusInput` (DrawCanvas + recognize + chips), `ChoiceInput`, `StructuralInput`
  (re-export of exercise-inputs). Shared "interpreted as — pick one" chip UX.
- `useAnswerModality(format, preference)` hook: picks active modality from
  `accepted_modalities` ∩ preference; toggle UI renders only the valid alternatives.
- ReviewQueue write mode: card front → `AnswerInput` → Check → verdict panel (your
  answer vs expected back, side by side) → rating buttons (pre-selected by
  `suggested_rating`); adaptive default from card state (new/learning → write,
  review → self-grade unless toggled); reveal-only when `format=none`. Quiz runner +
  exercise Player switch their inputs to `AnswerInput` behind the same spec (mechanical,
  keeps one basket everywhere; quiz write-mode toggle maps to modality switch).
- Card detail/history: last answers shown on the card row expansion or a small history
  popover (`GET /flashcards/{id}/reviews`).

**Accept.** A math card accepts MathLive/text/stylus (stylus→chips→confirm); a cloze
card text/stylus; an `essay` card richtext/stylus; a `none` card shows only Reveal;
invalid modalities never render; quiz/exercise inputs unchanged visually; rating
pre-selected from verdict; answers visible in history.
**Tests.** AnswerInput dispatch per format+modality; modality hook (preference honored,
fallback, invalid hidden); ReviewQueue write flow (answer → check → preselected rating →
stored call payload with answer); adaptive default; reveal-only path.

### 3 — Generation alignment (small)

- `flashcards.generate` skill prompt asks for `back_format` per card
  (math|short_text|essay|none) so new cards carry a trustworthy answer format from the
  start; validator accepts the field (default derived otherwise).
- Quizgen/exgen unaffected (formats derivable from types).

**Tests.** flashcards validator: `back_format` honored/derived; prompt contains the
format instruction.

---

## Non-goals

- Changing FSRS scheduling or making correctness *override* the self-rating.
- Voice/audio modality, OCR-free ink recognition.
- New quiz question types.
- Card write-mode streaks/analytics beyond stored answers (later, mistake-notebook
  integration for repeated-wrong cards is a natural follow-up).

## Verification per slice

Backend `ruff check . && mypy . && pytest`; frontend `pnpm lint && pnpm typecheck &&
pnpm test && pnpm build`. Docs per ca-docs-sync: usage/flashcards.md + usage/quiz.md
rewrite (modalities), features.md (write mode, Review tab), ai.md unchanged,
data-model.md (0027), STATUS.md changelog per slice.

## Open questions (defaults chosen, flag to change)

1. Rail Study group after retirement = Home only (default) vs keep a "Review" rail item
   that routes to the current course's Review tab.
2. `suggested_rating` mapping: correct→Good, partial→Hard, incorrect→Again (default;
   new cards: correct→Easy is tempting but Good is the conservative default).
3. History surface: popover on the card row (default) vs dedicated panel.
