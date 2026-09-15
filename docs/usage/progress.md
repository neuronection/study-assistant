# Today screen and progress

The **Today** screen is where your day starts, and **Scores** is where you see the
bigger picture. Everything on both pages is computed from your real answers —
nothing is a guess.

## Today

- **Exam countdown** — for courses with an exam date set (course settings) within
  30 days: days left, how many nodes you've studied, a pace line ("≈2
  nodes/day to finish" — turns red when that pace can't realistically get you
  there) and a jump button to the first node you haven't touched.
- **Streak** — consecutive days with any qualifying activity: at least one
  answer or card review, **or five minutes of tracked study time**. Reading a
  chapter or running a focus block keeps the streak alive without a single
  answer. No shaming: a broken streak just resets the number.
- **Daily goal** — answers per day **or minutes per day**, whichever unit you
  pick (toggle it inline in the goal card). The ring fills as you go.
- **Study time** — how long you actually studied today and this week. Time is
  tracked automatically while a focus surface is open (quiz runner, exercise
  player, note editor, the material reading drawer) and by the **focus timer**
  — the floating pill in the bottom corner (25/5 and 50/10 presets, or a custom
  length). Only open-surface time counts: closed or crashed tabs stop counting
  at the last heartbeat, so tracked time never inflates.
- **Due reviews** — flashcards waiting in your spaced-repetition queue.
- **Next best action** — ranked suggestions, each with its evidence:
  - *Review due cards* when your FSRS queue is waiting.
  - *Read* a concept you keep missing on conceptual (understanding) questions.
  - *Drill* — generates a quiz focused on that exact concept and skill
    (easier difficulty band) and opens it for you.
  - *Challenge* a concept you're strong on but haven't touched in over a week —
    same one-tap generation, harder band.
  One tap takes you to the right screen.
- **Consistency heatmap** — the last 90 days; darker means more activity
  (answers plus tracked study minutes).

Practice attempts feed these signals; **exam attempts are excluded** (they measure
the exam, not your learning).

## Scores

Four tabs:

- **History** — every attempt with its score.
- **Diagnostics** — the "what am I bad at" view:
  - *Weakness matrix*: concepts × skills; each cell shows accuracy. Faded cells
    have fewer than 3 answers — not enough data for a verdict yet.
  - *Error patterns*: your named misconceptions (e.g. sign slips) with a 7-day
    trend.
  - *Speed vs accuracy*: per concept — *rushing* (fast + wrong), *struggling*
    (slow + wrong), *effortful* (slow + right), *fluent* (fast + right), measured
    against each question's expected time.
- **Tips** — the same recommendations the Today screen uses, with their evidence.
- **Mistakes** — your mistake notebook.

Diagnostics quality grows with volume: answer more practice questions and the
matrix sharpens. Items that nearly everyone gets wrong (or right) are flagged for
review in the question bank automatically.

## Planner

Every course with an exam date can have a **plan**: open the course workspace's
**Planner** tab (course root only) and press **Generate plan**. Study Assistant
paces the topics you haven't touched yet across the days left before the exam,
adds practice items for your weakest concepts (from the diagnostics above) and
a weekly review marker — everything arrives as **draft suggestions** (dashed
rows) you can keep or discard one by one. Regenerating never touches items you
checked off or added yourself.

Check items off as you go (they count toward your streak honestly), drag a row
onto another day to reschedule it, or use the +1-day button. Add your own items
with **Add item**. The Home screen shows the coming week across all courses
under **This week's plan**.

### Week view

Toggle the planner between **List** and **Week** (the segmented control in the
tab header). The week view lays out Monday–Sunday as a grid with today
highlighted — drag a card onto any other day to reschedule it (the same drag
works in both views). Overdue items get a warning left border; checked-off
items render struck-through.

### Calendar export (ICS)

**ICS** in the tab header downloads the course plan as a calendar file: every
plan item becomes an all-day event on its due date (done items appear only for
the past week, marked cancelled), and the exam date becomes an all-day event.
The file carries stable event IDs, so re-importing after moving items *updates*
the existing events instead of duplicating them — import it into Google
Calendar, GNOME Calendar, Outlook or anything that reads ICS.

Tips:
- Set the exam date in the course's **Settings** tab first — the planner paces
  toward it and refuses dates in the past.
- Generation is arithmetic, not AI: it is instant, deterministic and free.

## Exam readiness

When a course has an exam within 30 days, the Home exam card and the Planner
tab show a **readiness score (0–100)** next to the coverage bar. It is plain
arithmetic over your own data — no black box:

- **coverage (50 %)** — share of course nodes you have engaged with
  (studied, notes, quizzes or exercises);
- **mastery (35 %)** — your answer accuracy across the diagnosed
  concept/skill cells in the course (weighted by how many answers each cell
  has);
- **trend (15 %)** — is your recent accuracy better than before it
  (↑ improving / → steady / ↓ declining)?

Underneath the score you'll see the trend and the up to three weakest
concepts in the course. Honesty rule: with fewer than three answered
questions in the course there is **not enough data** — no score is shown
until there is something real to measure. When a forecast exists, generated
plans schedule their practice items on the earliest days.

## Teach-back

The strongest self-test is explaining a topic in your own words. Weak
concepts offer **Teach back**: you get a short essay prompt ("Explain X as if
teaching a classmate — definition, intuition, one example") and the AI grades
your explanation against a rubric — criterion by criterion, with an honest
AI-graded badge. After a few rounds of drilling a weak area, Today may suggest
"Explain it back" instead of another drill: recognizing a gap and explaining
it is a different skill from computing answers, and your diagnostics track it
as such (an "explanation" sample on the concept, separate from procedural
accuracy).
