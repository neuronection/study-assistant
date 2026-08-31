# Plan 49 — Study experience: cross-course review, study sessions + focus timer, exam timing (user request 2026-08-31)

Status: planned (2026-08-31, user-approved) · Phase: post-1.0 · Suggested order: A → B → C (A first: B and C both log into it)

## Context

The audit (2026-08-31) found the *study* half of the study workbench thinner than the
*content* half:

- **Spaced repetition is trapped per course.** The FSRS engine, due queue and review
  flow are complete, but `ReviewQueue` lives only inside each node workspace's Practice
  tab (`features/flashcards/` is a single file; `/flashcards` is a redirect). A student
  with five courses must tour five workspaces to clear due cards. Vision doc H3
  promises "upcoming SRS reviews" on the dashboard — the Home tile deep-links into one
  course instead of a queue.
- **Time-on-study doesn't exist.** `study_sessions` was in the original feature list
  (I18 focus timer "logging into study_sessions"; H3 "study time") but analytics count
  only *answers* (`daily_rollups` from quiz/exercise events). Streaks measure answers,
  the daily goal is answers-only (H10 says "minutes-or-questions"), reading a chapter
  or reviewing notes — the majority of real study time — is invisible.
- **Exam mode has no time.** Attempts support `mode=practice|exam` with help locked
  (C10 partial), but there is no `time_limit`, no countdown, no server-enforced
  auto-submit — exam mode is practice mode minus help.

Breaking changes fine (no users). Migration head today: 0047.

**ADRs recorded as slices start:**

| # | Decision |
|---|---|
| 106 | `study_sessions` is the single source of truth for *time* analytics; sessions are auto-opened by focus surfaces and by the focus timer, and streaks/goals accept minutes-or-answers (H10 as-written) |
| 107 | The global Review queue is a first-class page over a cross-course due API; the per-course Practice cards segment embeds the same component, course-scoped — one review implementation, two scopes |
| 108 | Quiz time limits are server-enforced: the deadline is computed at attempt start, grading rejects post-deadline answers, and expiry auto-submits with what was answered |

## A — `study_sessions` + focus timer (ADR-106)

**Problem.** No time tracking; goal/streak/heatmap miss most real study.

**Design.**

- Migration **0048**: `study_sessions` (id, profile_id, course_id nullable,
  node_id nullable, kind ∈ `focus|quiz|exercise|review|read|note`, source ∈
  `timer|auto|manual`, started_at, ended_at, duration_sec; index on
  `(profile_id, started_at)`). Ownership semantics mirror existing user-content
  tables; course purge removes its sessions.
- Backend: `POST /study-sessions` (start → id), `PATCH /study-sessions/{id}` (end /
  heartbeat; server computes `duration_sec` from started_at, capped), `GET
  /study-sessions/summary?days=N` (totals per day, per kind — feeds metrics).
  Idle policy: sessions auto-close after a 10-minute heartbeat gap
  (`ended_at = last heartbeat + cap`) so a crashed tab can't inflate time.
- Frontend `lib/useStudySession.ts`: FocusShell surfaces (QuizRunner, Exercise Player,
  NoteFocusPage, MaterialDetailDrawer/reading view) open an `auto` session of the
  matching kind on mount and close it on unmount, heartbeating every 60 s. One
  session per surface instance; the chat sidepanel does *not* open sessions (passive).
  **Fragmentation guard** (revision 2026-08-31): param-driven remounts (the drawer
  opening/closing on the same material, tab switches) must not mint a session per
  mount — the start call carries `(kind, entity)` and the backend *resumes* an
  identical session ended ≤2 minutes ago (extends `ended_at`, keeps one row) instead
  of inserting a new one. Route churn becomes one honest session, not confetti.
- **Focus timer (I18)**: a floating pill in AppShell (start/pause/give-up, mode
  picker: 25/5, 50/10, custom) that runs a `focus` session (with course/node context
  from the active route when available), shows elapsed/remaining, and on completion
  offers the break; break completion returns to the preset picker. Timer state lives
  in a zustand store so it survives route changes (not reloads — honest, server holds
  the truth anyway). Kind logged `source=timer`.
- Analytics wiring (`services/metrics.py` stays the single source): daily rollups
  gain `study_seconds` (from sessions; materialize job sums them per day); **streak**
  = consecutive days with any qualifying activity (≥1 answer OR ≥5 min sessions) —
  guilt-free framing per H10; **daily goal** preference gains a unit field
  (`answers` | `minutes`, default keeps each user's current behavior) — the Home ring
  renders whichever unit is set; Home gains a **study time today/this week** card;
  heatmap colors from `study_seconds + answers`.

**Accept.** Study a material for 12 minutes, run one 25-minute focus block, answer
six quiz questions → Home shows ~37 min today, the streak (previously zero because
the quiz was one answer) is alive, and the goal ring fills under the `minutes` unit.

**Tests.** Backend: session CRUD + duration/idle-cap math, summary aggregation,
purge-on-course-delete, materialize rollup. Frontend: focus-surface auto-session
open/close/heartbeat (fake timers), timer pill flows, goal-unit rendering.

## B — Global Review queue (ADR-107)

**Problem.** Due cards are only reachable per course; H3's dashboard promise is
unmet; `features/flashcards/` is under-structured for its importance.

**Design.**

- Backend: `GET /review/due` — cross-course aggregation (all the profile's courses,
  due cards grouped by course with counts, `limit` per course for the first batch)
  reusing the existing due-query semantics; `POST /flashcards/{card_id}/review`
  stays the single grading verb (no new write path).
- Restructure: `features/review/` owns `ReviewQueue` (lifted from
  `features/flashcards/`, which dissolves) — course-agnostic component driven by a
  cards prop + `onRate`; the Practice tab's cards segment passes its course's cards,
  the new page passes the aggregate.
- New route `/review` (rail: **Review** with a due-count badge next to Home; hidden
  at 0 due? No — show at 0, honest empty state). Page: due cards grouped by course
  (course chip on the card, keyboard 1–4 rating, progress bar, session completion →
  logs a `study_sessions` row kind=`review`, links to the weakest concept per the
  existing card→concept data).
- Home: the due-reviews tile deep-links to `/review` (was: one course's practice tab).

**Accept.** With three courses having due cards, the rail shows Review · 12; the
page clears all 12 in one keyboard session across courses and the Home tile drops
to 0.

**Tests.** Backend: cross-course due aggregation (multi-course, due-only, per-course
limit). Frontend: ReviewQueue reuse in both scopes, page flow + completion logging,
rail badge counts.

## C — Exam timing (ADR-108)

**Problem.** C10's exam mode has no clock; timed self-testing (practice too) is a
core study behavior.

**Design.**

- Migration **0049**: `quizzes.time_limit_sec` nullable; `quiz_attempts.deadline_at`
  nullable, set server-side at attempt start when the quiz has a limit. Deadline is
  **server-computed** — the client clock is untrusted.
- Grading enforcement: answer-submit and finish endpoints compare `now` against
  `deadline_at` — post-deadline answers are rejected (422 `attempt_closed`) and the
  attempt is **auto-submitted** (graded so far) by the first endpoint touch after
  expiry, and by a lazy sweep when the attempt is next read. No background timer
  needed (local-first: nothing runs if nobody's looking).
- Runner UI: countdown chip in the FocusShell meta (server-offset-corrected: render
  remaining from `deadline_at − server_now` snapshot, tick locally), auto-submit on
  expiry with an honest "time's up" summary; attempt detail shows the deadline.
- Quiz create/generate: `time_limit_sec` field (GenerateDialog params + quiz editor),
  presets (30/60/90/120 min + custom), and exam mode keeps its help-lock unchanged.
  Self-timed practice allowed on any quiz (the field, not the mode, carries the
  limit).

**Accept.** Generate a 10-question quiz with a 20-minute limit, start the attempt,
walk away → returning after 25 minutes shows the attempt auto-submitted at the
20-minute mark with the questions answered by then graded; hammering the answer
endpoint after expiry 422s.

**Tests.** Backend: deadline set on start, answer rejection + auto-submit paths,
lazy sweep on read, no-limit quizzes unchanged, exam-mode help-lock regression.
Frontend: countdown rendering + expiry auto-submit, generate/create field wiring.

## Non-goals (this round)

- SRS scheduling for quiz mistakes / exercises (FSRS stays flashcards-only; the
  mistake notebook's re-quiz flow covers mistakes).
- Calendar/ICS export, notifications, planner UI beyond the existing Today exam card
  (plan 22 H1 scoped this deliberately; revisit if asked).
- Per-question or per-section timing (quiz-level limit only).
- Session "goals per node" or course-level time budgets.
- Multi-device sync of in-flight sessions (single-machine app).

## Dependencies & suggested order

A first (B and C log `study_sessions` rows; C's exam sessions ride A's kinds).
B and C independent of each other.

## Verification per slice

Backend: `ruff check . && mypy . && pytest` · Frontend: `pnpm lint && pnpm typecheck &&
pnpm test && pnpm build`. Docs duty: `docs/usage/progress.md` (time tracking, goal
units, streak definition), `docs/usage/flashcards.md` (Review page), `docs/usage/quiz.md`
(time limits), `docs/data-model.md` (0048/0049), `docs/features.md` (H3/I18/C10 rows),
`docs/STATUS.md` changelog + module rows each slice.
