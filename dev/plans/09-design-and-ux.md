# 09 — UI/UX & Engagement Design

Goal: a **modern, calm, feature-rich** interface that makes learning feel good — users
open it *wanting* to study. Design language: "focused study workbench, not a toy" —
Linear/Notion-grade polish with warm, encouraging moments where they earn it.

## Design principles

1. **Calm by default, delightful on success** — quiet surfaces, no decorative noise;
   celebration is reserved for real achievements so it stays meaningful.
2. **Progressive disclosure** — every screen is simple at first glance; power features
   (params, banks, contracts) live one layer down. "Easy ≠ shallow."
3. **No dead ends** — every state has a next action: empty course → "add material",
   wrong answer → "why?", finished quiz → "review mistakes / similar questions".
4. **Instant feedback** — answers respond in <100ms (deterministic grading first, LLM
   explanations stream in after); nothing blocks on a spinner that could not block.
5. **Keyboard-first** — A–E for choices, Enter to submit, `H` for hint, `⌘K` palette;
   stylus/touch equally first-class (C18).
6. **Motion with purpose** — transitions orient (question → question flows horizontally,
   levels deepen vertically), 150–250ms, spring physics; full `prefers-reduced-motion`
   support. Animation never carries information alone.
7. **Trust through transparency** — AI outputs show their nature (cited, LLM-graded badge,
   hint-level indicator); costs visible in dashboard.

## Design system (shadcn/ui + Tailwind, extended)

- **Tokens**: semantic palette (surface / subtle / border / primary / success / warning /
  danger), 8pt spacing grid, radii (sm/md/lg/xl), elevation via subtle borders + shallow
  shadows (modern flat), z-scale documented.
- **Typography**: Inter (UI) + KaTeX (math, always) + JetBrains Mono (code); fluid scale
  13–30px; math blocks optically aligned with text line-height.
- **Theme**: light/dark (default follows OS) + optional AMOLED-dark; accent color
  per-course (user-picked, drives course identity everywhere — icons, progress rings).
- **Density toggle** (comfortable/compact) — power users get more per screen.
- **Mastery color language** (consistent app-wide): red → amber → green rings/fills;
  never color-only (icon + label always accompany — accessibility).
- **Component inventory**: block renderers (doc 03) are the heart — every block type has
  view + edit + inline-preview states shared by quiz/notes/chat/extractions.

## Information architecture & navigation

- **Left rail**: courses (colored, collapsible) → chapters tree; global search; chat
  toggle. **Breadcrumbs** everywhere. **Command palette (I5)** as the power path:
  "jump to section", "quiz me on weak areas", "open mistake notebook".
- **Home / "Today" screen**: the anti-boredom front door —
  streak flame + daily goal ring → **"Next best action" card** (H11: due reviews →
  weakest concept → unfinished exercise → new material), then a 10-second course switcher.
- **Focus modes**: quiz/exercise/reading screens hide the rail (zen); `Esc` exits.

## Quiz & exercise UX (the anti-boredom core)

- **One question per screen** (cards animate in/out horizontally); sticky progress bar
  with segment colors; timer only when configured (never ambient anxiety by default).
- **Flow, not friction**: submit → instant deterministic verdict → explanation & distractor
  analysis stream in → `Enter` advances. Rhythm target: <3 clicks per question.
- **Wrong answers are content**: friendly tone, error-pattern name ("classic sign slip"),
  links to the exact material chunk + option to create a note/flashcard on the spot.
- **Variety engine (H12)**: sessions mix types, difficulties and question *shapes**
  (stem formats alternate: text / diagram / chart / numeric entry) per blueprint —
  monotony is the #1 boredom source in generated quizzes.
- **Session shape**: 5–15 questions default (user-tunable), difficulty ramps mid-session,
  a "boss" composite question (C16) as a satisfying closer, then a **summary screen**
  that feels like a win: score ring, mastery delta animation, streak update, "beat this
  score with similar questions" and "review mistakes now" CTAs.
- **Milestones**: first 100% quiz, 7-day streak, concept mastered → tasteful celebration
  (ring burst animation, optional sound); never confetti-spam on routine events.

## Engagement loop (motivation architecture)

- **H10 Daily goal & streaks**: goal = minutes or questions/day; streak freeze earned
  weekly (Anki-style protection); heatmap (H3) makes consistency visible, not guilt-heavy.
- **Mastery visualization (I20)**: per-concept rings, per-chapter coverage bars, course
  mastery tree that *fills in* as you learn — progress you can see accumulating is the
  strongest retention hook we have.
- **Next best action (H11)**: engine ranks {due FSRS reviews, weak concepts, unfinished
  exercises, un-studied material} by urgency × user goals; one tap starts a session.
- **XP & levels (H8, revised stance)**: on by default but **calm** — XP accrues silently,
  level-ups appear as a toast, badges live in a profile page, zero leaderboards/social
  pressure. Full off-switch in settings; no dark patterns (no loss-aversion streak
  shaming, no pay-gated dopamine).
- **Micro-narratives**: "You've mastered **chain rule** — it took 4 sessions. Efficiency
  +12%." — progress framing in session summaries, generated locally from real data.

## Empty states, onboarding, errors

- Every empty state: friendly one-liner + illustration (consistent line-art set) +
  primary CTA ("Add your first material" → provider check → upload).
- **Guided first run (I9)**: 3-step tour (create course → drop a PDF → generate first
  quiz) with the sample-course shortcut prominent; skippable, never modal-locked.
- Errors are human ("OCR failed on page 7 — the scan may be too skewed. Retry page?
  Open in editor?"), always with a recovery action; provider offline states deep-link to
  Settings (doc 07).

## Frontend engineering for feel

| Concern | Choice |
|---|---|
| Motion | framer-motion (layout animations, shared element transitions between question → explanation) |
| Virtualization | TanStack Virtual (chapter trees, question banks, long extractions) |
| Optimistic UI | TanStack Query mutations with rollback — answers/questions never wait on network |
| Streaming UX | token-by-token chat/explanations over WS with cursor + progressive KaTeX rendering |
| Perf budgets | first paint <1s, interaction <100ms, quiz advance <50ms; Lighthouse in CI |

## Accessibility

WCAG 2.1 AA: full keyboard paths, visible focus rings, ARIA on custom inputs
(MathLive/canvas — both expose keyboard alternatives: LaTeX typing is never the *only*
path), contrast-checked tokens both themes, reduced-motion honored globally,
screen-reader labels on mastery/ring graphics.
