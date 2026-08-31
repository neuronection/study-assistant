# 28 — Error-pattern drills: hardcoded calculus list → course-type taxonomies + agentic discovery

**Status:** COMPLETE 2026-08-22 (A–F in one pass; backend 448 + frontend 552 tests
green; ADR-063 recorded) · **Phase:** post-1.0 (follows plan 27) ·
revisits the Phase-5 features D8 / G10 and their "calculus-only" seed

**As-built deltas:** approved discovered patterns start at **0 occurrences** (no
retroactive re-tagging — the propose digest doesn't map proposals to specific
mistakes; counts grow as detectors/quizgen tag future mistakes). Discovery runs
on the course's 30 most recent **wrong answers** (Answer rows), not Mistake rows
(unresolved-ness isn't tracked per answer; `resolved_at` is left untouched).
`GET /exercises/drills/patterns` makes `course_id` **required**. `course_id IS
NULL` on `error_patterns.course_type_id` means *global* (applies to all types);
a course with no type resolves to global patterns only (none seeded today, so
empty). The propose endpoint returns 502 on unassigned tasks, 422 on
contract-invalid proposals.

This plan replaces the fixed 8-entry calculus `ERROR_TAXONOMY` with a **DB-backed,
course-type-scoped, discoverable** error-pattern system. The drill *mechanics* (exgen
prompt seeding, mistake-notebook counts, course-required writes) already generalize; the
plan moves the taxonomy out of code, scopes counts to the open course, adds deterministic
detectors where the math engine can prove a pattern, and lets the AI **propose** new
patterns from observed mistakes through the existing HITL protocol.

## Context

As built (Phase 5, D8/G10):

- `ERROR_TAXONOMY` — a hardcoded 8-entry calculus dict — lives in
  `backend/app/pipelines/exgen.py:84` (missing chain-rule factor, wrong power rule,
  missing +C, u-sub bounds, limit/continuity confusion, sign slip, dropped factor,
  notation misuse).
- `GET /exercises/drills/patterns` (`api/exercises.py:243`) counts `Mistake.error_tags`
  **only where the tag is a taxonomy key**, profile-wide — and always returns all 8
  patterns regardless of the course being viewed.
- `POST /exercises/drills` (`api/exercises.py:263`) validates the pattern against the
  taxonomy, then runs `exgen` with `pattern` seeded into the prompt (hard-coded
  "calculus error" wording in `exgen.py:485`), fixed 3 steps, course required (ADR-040).
- The signal: `Mistake.error_tags` are authored by **quizgen at generation time**
  (`distractor_misconceptions`, constrained to a tag format by the quizgen contract) plus
  one deterministic tag (`incomplete_selection`, `grading.py:76`). Nothing verifies, at
  *grade time*, that a wrong answer actually exhibits the claimed pattern.

Problems this plan fixes:

1. **Calculus-only, in code.** The taxonomy is not data, not extensible, not per-subject —
   despite `course_types` (math/science/language/programming/generic) already existing.
2. **Counts ignore the open course.** A history course's drill card shows 8 calculus
   patterns, all 0, with a hint that literally says "common calculus errors"
   (`frontend/src/locales/en.json:148`).
3. **LLM-claimed, not verified.** The deterministic-before-probabilistic principle
   (ADR-008/021) is not applied to pattern *detection* at all.
4. **No learning.** The app can never surface a recurring error it didn't ship with.

Existing hooks to build on (do not reinvent):

| Hook | Where | Reuse |
|---|---|---|
| `course_types` table + `Course.course_type_id` | `models.py:814`, `:51` | the scoping axis for taxonomies |
| Skills scope chain `(system, course_type, course)`, code-seeded DB-backed (ADR-020) | `services/skills.py:11` | the seeding pattern `error_patterns` follows |
| HITL proposal protocol (approve/dismiss, audited) | ADR-043 / `chat_proposals` | where "AI proposes a pattern" lands |
| `exgen` TaskRunner + ContextResolver | ADR-042 | drill generation already rides it |
| Equivalence chain (simplify + numeric sampling + solveset) | ADR-022 | deterministic pattern detectors |
| `Activity.course_id` (FK, indexed) | `models.py:443` | course-scoping counts via `Mistake→Question→Activity` (no schema change for scoping) |

## Proposed ADR-063 (record in `06-decisions-and-risks.md` at slice start)

**Error patterns become DB-backed, course-type-scoped data; detection is
deterministic-first, discovery is agentic (HITL).**

- New `error_patterns` table seeded idempotently from code (ADR-020 pattern); each row
  carries an optional `course_type_id` (null = generic/global) and an optional
  deterministic `detection` spec. The G10 calculus seeds move here verbatim under
  `course_type_id = math`; the code constant is deleted.
- Drill resolution is **course-scoped**: the open course's type selects the visible
  pattern set (its type's patterns + generic ones + anything discovered for that course),
  and occurrence counts are computed over that course's mistakes only.
- Where a `detection` spec exists, a wrong answer is tagged **by code** (equivalence
  chain), not by the quizgen author's claim; deterministic tags win over LLM-authored
  `distractor_misconceptions` for the same key.
- A new `pattern.discover` skill (on the `description` task, like `note.compose` in
  ADR-044) clusters unresolved mistakes and **proposes** new patterns as HITL cards;
  approved patterns become active `error_patterns` rows scoped to the course type
  (`is_system = False`), dismissible, audited.

Alternatives rejected:

- **Keep the taxonomy in code, add more subjects as more dicts.** Same dead-end; every new
  subject is a code change, no user/AI extension path.
- **One global taxonomy, no course-type scoping.** Keeps the "8 calculus patterns on a
  history course" bug; ignores the `course_types` model we already committed to.
- **Full auto-tagging with no HITL.** ADR-043 already decided the app never takes
  autonomous state-changing actions; pattern creation is a write and must be approved.
- **Drop D8 entirely.** `metrics.py` and weak-area sessions already emit `drill`
  recommendations; error-pattern drills are their pattern-targeted complement, a P1 vision
  feature — removing it would orphan that axis.

Non-goals: cross-profile pattern sharing (local-first, profile-scoped); LLM *grading* of
patterns (detection stays deterministic, discovery is the only LLM step); a pattern
marketplace.

## Data model (migration 0031)

`error_patterns`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `key` | str(80), unique | stable slug, e.g. `missing_chain_rule_factor` |
| `course_type_id` | int FK→course_types, nullable | null = generic (applies to all types) |
| `name` | str(200) | display, e.g. "Missing chain-rule factor" |
| `description` | text | what the error is; seeded into the drill prompt |
| `example` | text, nullable | short canonical wrong-vs-right example (LLM context + tooltip) |
| `detection` | JSON, nullable | optional deterministic detector spec (slice B) |
| `is_system` | bool | seeded vs AI/user-discovered |
| `is_active` | bool | dismissal = deactivate, not delete (audit) |
| `order_idx` | int | card ordering |
| `created_at` | datetime | |

- Unique index on `key`; index on `course_type_id`. No FK back from
  `exercises.created_from` — it stores a `pattern` *string* (a stable key), so provenance
  is by key, not id.
- Seed set (idempotent, code as reset point — ADR-020): the 8 G10 calculus patterns under
  `math`, with `detection` specs where derivable (slice B). Science / language /
  programming start with **only the generic seeds + whatever discovery finds** —
  deliberately thin: we do not author low-confidence taxonomies we cannot verify.
- What we do **not** seed: cross-subject "generic error" rows with no verifiable detector
  or description add noise to the card. The card's real content for non-math courses is
  the **discovered** section (slice C); the seeded section exists only where a trusted
  taxonomy exists (math today).

## A — Backend: seed + resolution service (`services/patterns.py`)

1. Move the 8 entries out of `exgen.py` into a `SEED_ERROR_PATTERNS` list in
   `ai/skills/__init__.py` (next to `SEED_COURSE_TYPES`), each tagged `course_type="math"`.
   `seed_error_patterns(session)` inserts missing rows by `key`, called from `main.py`
   alongside `seed_course_types`/`seed_skills`.
2. `ErrorPatternService`:
   - `resolve(course_id)` — the course's `course_type_id` → active patterns where
     `course_type_id IS NULL` or equals the course's type, plus course-discovered rows
     (`is_system=False` scoped to this course), ordered by `order_idx`.
   - `counts(course_id)` — `Mistake.error_tags` joined `Question → Activity` filtered to
     `Activity.course_id`, counted only for keys in the resolved set (replaces the
     profile-wide query at `exercises.py:246`).
   - `create(...)` / `set_active(...)` — for approved proposals and dismissal.
3. `GET /exercises/drills/patterns?course_id=` — `course_id` becomes required (drills are
   course-required writes, ADR-040; the card always has a bound course). Response gains
   `example` and `source: "seeded" | "discovered"` so the UI can section it. A course with
   no type resolves to `generic` patterns only (legacy courses default to `generic`).
4. `POST /exercises/drills` validation switches from `pattern in ERROR_TAXONOMY` to
   "pattern key exists, is active, and is resolvable for the body's course" (else 422 with
   the same detail string, preserving the existing test contract).

## B — Deterministic detectors (determinism before LLM)

Add `detection` specs and a small `services/pattern_match.py` that, given
`(response, expected, kind)` where both parse as math, proves a pattern **by code** using
the equivalence chain (`math/equivalence.py`). Specs are declarative:

| Pattern | Detector (deterministic) |
|---|---|
| `sign_slip` | `equivalent(response, -expected)` is true |
| `missing_constant_of_integration` | expected is an indefinite integral and `equivalent(response, expected_without_+C)` is true |
| `dropped_factor` | response differs from expected by a constant factor: `equivalent(response/expected, k)` for small integer k |
| `wrong_power_rule` | response is `x^(n±1)` / `n·x^(n±1)` where expected is `d/dx x^n` |

Patterns whose detector cannot be expressed declaratively (e.g.
`limit_continuity_confusion`) ship with `detection = null` and rely on quizgen-authored
misconception tags (current behavior). Wiring:

- In `grade()`'s equation/numeric branches and the tutor's `check_step`, after the
  equivalence verdict, run the **active** detectors for the course's resolved patterns;
  matched keys are appended to `error_tags` (deterministic tags win on key collision with
  `distractor_misconceptions`).
- Detectors run on the chain: free, auditable, and they make occurrence counts *true*
  rather than generation-time hopes.

## C — Agentic discovery (HITL)

1. New skill `pattern.discover` on the `description` task (a text-analysis skill, matching
   the `note.compose` precedent — no new task row). Input: a compact digest of the course's
   **unresolved** mistakes (wrong answer + expected + existing tags + stem, capped at the
   N=30 most recent) plus the course's current resolved pattern set (so it proposes *new*
   keys). Contract-validated output: `{key, name, description, example}` with slug/format
   validators (key regex, non-empty description, no collision with existing keys).
2. `POST /exercises/drills/propose` (on demand from the card's "Find more patterns"
   action, never automatic) → `PatternProposal[]`. The frontend renders them as the
   existing **proposal cards** (approve/dismiss) — ADR-043 protocol and audit, no new
   plumbing.
3. **Approve** → `ErrorPatternService.create(...)` with `course_type_id = course's type`
   (siblings of the same type benefit), `is_system=False`. **Dismiss** → audit row only.
   Approved patterns appear immediately in the card's *Discovered* section with real counts
   (the motivating mistakes already carry matching tags — counts are recomputed, not
   stored).
4. Guardrails: proposals capped (max 5 per run); keys must not collide with existing keys
   or each other (validated); the run is budgeted + audited through the TaskRunner like
   every other task; a course with no unresolved mistakes returns an empty proposal list
   (no call made — the card hides the action instead).

## D — Drill generation generalization (`exgen.py`)

`_build_prompt`'s drill branch stops hard-coding "calculus error" and instead:

- resolves the pattern row (name + description + example) for the body's course;
- renders: `Create a short ERROR-PATTERN DRILL (2-4 steps) targeting this common
  {course_subject} error: {description}. Example: {example} ...` — subject word from the
  course type, description/example from the resolved row;
- passes the course's ContextResolver context (already done via `_run_exgen`) so the drill
  stays in-material for any subject.

The validation contract (every expected answer parses via the chain) is unchanged and
already subject-agnostic — this is the property that makes drills safe to generalize.

## E — Frontend: DrillsCard redesign (`features/exercises/DrillsCard.tsx`)

1. Two sections: **Seeded** (system patterns for the course type) and **Discovered**
   (course-discovered patterns, hidden when empty), each row showing name, one-line
   description, and the mistake-count badge. Counts are now course-scoped so the badge is
   meaningful for the open course.
2. Copy drops the calculus-specific hint ("common calculus errors") for a neutral
   "Recurring errors in this course" — i18n key updated (`en.json:148`).
3. Empty states: no seeded patterns for the type and no discovered rows → a single
   friendly line ("No error patterns yet. Wrong answers from quizzes will build this list
   and you can ask the tutor to find more.") with the **Find more patterns** action when
   unresolved mistakes exist.
4. **Find more patterns** → `proposeDrills()` → proposal cards inline (approve/dismiss,
   matching the chat proposal UX); approve refreshes the list with the new discovered row.
5. Drill button passes the pattern key unchanged (`drill.mutate` contract preserved).

## F — Analytics integration

`services/metrics.py`'s error-pattern profile already ranks `error_tags`; it now benefits
automatically from deterministic tags (slice B) and course-type scoping — no shape change
required. Verify the profile and the Scores → Diagnostics error-tag list stay consistent
with the resolved-pattern vocabulary (they share the same `error_tags` source).

## Tests

- **Backend** (`test_exgen_api.py` + new `test_patterns.py`):
  - seeding is idempotent; G10 rows land under `math`;
  - `resolve`/`counts` are course-scoped (a math course and a `generic` course return
    different sets; counts only count the open course's mistakes);
  - deterministic detectors tag `sign_slip`/`missing_constant_of_integration` without any
    LLM call, and deterministic tags override a colliding `distractor_misconceptions`;
  - `propose` returns nothing for a course with no unresolved mistakes, and approval
    creates an active discovered row scoped to the course type; dismissal deactivates.
  - existing drill/pattern tests keep passing (detail strings, provenance `{source: drill}`).
- **Frontend** (`DrillsCard.test.tsx`): seeded/discovered sections render from `source`;
  non-math empty state renders the neutral copy + Find-more action; approve→list refresh;
  drill button still fires with the pattern key.

## Docs (same commit)

`docs/STATUS.md` (changelog + exercises module row), `docs/usage/exercises.md` (reword the
drills section to "recurring errors for this course type", add the discovered/find-more
flow), `docs/data-model.md` (`error_patterns`), ADR-063 in
`dev/plans/06-decisions-and-risks.md` (local-only).

## Migration & rollback

Migration 0031 creates `error_patterns` + seeds the G10 math rows (data-only; the old
`ERROR_TAXONOMY` constant is removed in the same commit). Downgrade drops the table; the
endpoints fall back to a 422 on unknown keys, which is the pre-feature behavior for any
non-calculus course. No existing data is mutated.

## Sequencing & open questions

1. Slice order: A (table+service+scoping) → D (prompt) → B (detectors) → E (UI) → C
   (discovery). A+D+E ship a useful generalization alone; B and C are independent
   enhancements and can land separately.
2. Open: do `generic`-type courses show *no* seeded section at all (my recommendation) or a
   starter "misread/off-by-one" set? Leaning no — keep noise low, let discovery populate.
3. Open: should discovered patterns be promoted to `course_type` scope or stay
   course-scoped on approval? This plan promotes to `course_type` (siblings benefit); a
   stricter "course-only by default, promote-on-second-approval" is the fallback if
   cross-course noise shows up.

## Verification

Full gate per AGENTS.md (backend ruff/mypy/pytest; frontend lint/typecheck/test/build).
CI mirrors; no golden-set eval changes expected (drills ride the existing exgen validators).
