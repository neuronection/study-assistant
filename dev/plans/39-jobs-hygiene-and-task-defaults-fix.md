# 39 — Jobs hygiene & task-defaults persistence: delete + stale grouping for failed jobs, boot-time pruning, and the seeding fix (ADR-089…090)

**Status:** COMPLETE (2026-08-27, user-approved; commits e476a5d / 1b5e15b / 1ba4d56 /
39D) — ADR-090 + ADR-089 · backend 640 · frontend 742 tests green ·
**Phase:** post-1.0 · **Suggested order:** A → B → C → D (A lands immediately and alone —
it is a standalone bug fix worth committing before anything else)

## Summary

Two independent issues reported 2026-08-27:

1. **Failed tasks cannot be deleted.** Failed job rows (e.g. `ingest` → `material {id}
   not found`) accumulate forever, the red activity badge stays lit until every row is
   retried successfully or manually cleaned via SQLite, and rows whose target entity was
   already deleted can never be resolved at all — retry just fails again. There is
   currently *no* delete endpoint, no pruning of any kind (`jobs` has zero GC since
   migration 0002), and completed history grows unboundedly too.
2. **Settings → Tasks capability defaults reset on restart** (`/settings?tab=tasks`).
   Root-caused: the save path itself works end-to-end (PUT → `default_task_assignments`,
   gateway honors it). What wipes it is **startup reseeding**: `create_app()`'s lifespan
   calls `assign_default_task(session, requires, None, None)` as an *unguarded upsert* on
   every boot (`backend/app/main.py:171–172`), overwriting each row's `model_id` /
   `fallback_model_id` back to NULL before the first request is served. The same defect is
   replicated in backup restore (`backend/app/api/backup.py::_apply_restore`, lines
   ~195–197). Per-task overrides survive only because their seed loop
   (`main.py:166–170`) is properly insert-only.

### Recommendations taken (and how they differ from the original ask)

The ask considered: auto-delete failed jobs, or auto-group them for manual deletion
("delete selected group"), on both the `/jobs` page Failed tab and the task-activity
popover. Decision per slice below, summarized:

- **Failed jobs are never silently auto-deleted** — failures carry signal (retry afford-
  ance, error text, audit trail). Instead they get (a) explicit single delete, (b) bulk
  "Delete failed…" incl. the active Type filter acting as the "delete selected group",
  and (c) server-computed **stale detection**: a failed job whose referenced material or
  chat session no longer exists is flagged and surfaced as its own one-click group
  ("source removed") — this covers exactly the reported `ingest > material x not found`
  class, where retry can never succeed.
- **Auto-pruning applies to completed history only**: `done` jobs older than TTL are
  pruned at boot (new env knob `CA_JOBS_DONE_TTL_DAYS`, default 14). The jobs table has
  been append-only forever; done rows are pure history with no future reader.
- **No FK/cascade cleanup when materials/sessions are deleted** — jobs stay an audit log;
  deletions become stale flags instead of silent erasure.
- The defaults bug fix (Slice A) is trivial and ships first, alone.

## Reserved ADRs

| # | One-line decision |
|---|---|
| 089 | **Job lifecycle hygiene: explicit deletion for terminal jobs, stale-source detection, and done-history pruning — no silent deletion of failures.** `DELETE /jobs/{id}` allows done+failed only (queued/running → 422); `DELETE /jobs/failed` (optional `{types?}` body, mirrors retry-failed) deletes across all failed types *including non-retriable `chat_turn`*; batched existence checks flag failed jobs whose `payload` material/chat-session target is gone as `stale` (JobOut) with `failed_stale` in the summary; boot prune deletes `done` rows past `CA_JOBS_DONE_TTL_DAYS` (default 14). No FK/cascade from entities into `jobs`, no trash snapshotting of job records |
| 090 | **Startup/recovery seeding must be insert-only, forever.** Any code path that seeds DB defaults at boot (or after restore) may create missing rows but must never mutate existing ones through a shared upsert helper — implemented as one guarded `seed_default_task_assignments(session)` used by both `main.py` lifespan and backup `_apply_restore`; fixes the `default_task_assignments` wipe of ADR-088's data |

## Context — exact findings (audit 2026-08-27)

1. **Storage**: `Job` model (`app/domain/models.py:349–361`), table created in migration
   `0002_phase1_core_tables.py`. Payload is JSON (no FKs); material/chat references live
   inside `{"material_id": …}` / `{"chat_session_id": …}` / postprocess
   `{"material_id", "extraction_id", "old_chunk_ids"}`. Labels resolve live via
   `_material_label()` (`api/jobs.py:53–60`) returning `None` for deleted targets —
   proof the referential check is cheap to add next to it.
2. **No deletion/pruning anywhere**: no `delete(Job)` call sites; nothing touches `jobs`
   in `purge_material` (`services/materials.py:46–75`) or session delete; no retention
   settings exist. `_reclaim_interrupted` (`jobs/runner.py:83–91`) converts orphaned
   `running` → failed `"interrupted: the backend restarted…"` rows at every boot — a
   steady source of noise that makes explicit deletion more valuable than retry.
3. **API surface today** (`api/jobs.py`): GET /jobs (status/type filters), GET /jobs/
   summary, GET /jobs/types, POST /jobs/{id}/retry (404/422 conventions established,
   lines 165–187), POST /jobs/retry-failed (+ optional body, 190–212).
   `retriable = failed ∧ type ∈ retriable_handlers() ∧ ≠chat_turn` (`_to_out`, 80–84);
   `NON_RETRYABLE_TYPES = {"chat_turn"}`.
4. **Deletion safety**: worker code tolerates missing rows (`session.get(Job)` returns
   None → handler result silently dropped, `_mark_failed` same), so deleting a running
   row would not crash but must still be refused (side-effects continue mid-run);
   deleting queued rows is technically safe but is refused for symmetry/predictability.
5. **Frontend**: api client helpers grouped ~lines 2890–2990 (`listJobs`, `retryJob`,
   `retryFailedJobs`, …); `features/jobs/JobsPage.tsx` (URL-param tabs/type filter, 5 s
   polling, header Retry-all at lines 235–247) and
   `components/layout/ActivityPopover.tsx` (failed section top-8 w/ inline retry, footer
   Retry-all-N, summary badge drives red dot; 2 s polling while open). Mutations share
   an `invalidate(['jobs-summary'], ['jobs-list'])` pattern — new delete mutations ride
   the same rails, so the red badge self-clears once the summary drops.
6. **Defaults bug**: `assign_default_task` upserts unconditionally
   (`ai/providers.py:338–347`, else-branch writes the passed values); startup loop calls
   it with `(None, None)` per capability (`main.py:171–172`); restore repeats it
   (`backup.py:195–197`). Gateway resolution reads rows fresh per call
   (`gateway.py:_resolve_chain:229–276`) with per-task override → capability default →
   TaskUnassigned; a missing row behaves identically to a NULL row, so insert-only
   seeding changes nothing semantically for fresh DBs while preserving user data.
   Tests existed for the happy path only — no test ever booted a second app instance
   against an existing DB, which is why this survived review.

## Slice 39A — Fix task-defaults persistence (backend, standalone bug fix)

**Problem.** Finding #6 — user choices in `/settings?tab=tasks` capability-default rows
are erased at every app start (and by every backup restore).

**Design.**

- New `providers.seed_default_task_assignments(session)`: for each capability in
  `DEFAULT_REQUIRES`, `if session.get(DefaultTaskAssignment, requires) is None:
  session.add(DefaultTaskAssignment(requires=requires, model_id=None,
  fallback_model_id=None))` — mirrors the `TaskAssignment` guard right above it in
  `main.py` (never mutates existing rows; flush once).
- Replace the `for requires in DEFAULT_REQUIRES: assign_default_task(...None...)` loops
  in both callers (`main.py` lifespan, `backup.py::_apply_restore`) with the seeder.
- `assign_default_task` keeps its current mutating semantics — it remains the legit PUT
  implementation. Optionally add a docstring line noting it is caller-unsafe for seeding.
- Restore path nuance: archives predate/keep their own rows, so insert-only re-seed after
  migration fills gaps without resurrecting wiped state.

**Accept.**
(a) Fresh DB boot → three rows exist, all NULL (behavior unchanged vs today);
(b) boot #2 after assigning defaults → values intact;
(c) restore of a pre-0041-era archive → rows seeded, no crash.
One regression test does all three: build TestClient #1 on tmp storage dir, PUT
`/tasks/defaults/text` {model_id}, close runner + dispose engine, rebuild TestClient #2
on the same dir (a second `create_app()` = a real restart), GET and assert persisted;
plus restore-path assertions following the existing backup test harness.
Pattern to copy for the two-app dance: tests that construct `TestClient(create_app())`
with the suite's tmp-path sqlite engine; `client.app.state.jobs.stop()` teardown required.

**Tests.** Extend/attach near `test_providers_api.py::test_task_defaults_endpoints_and_inheritance`;
restart test named e.g. `test_task_defaults_survive_restart_and_restore`.

**As-built (39A).** Landed as planned, split into two tests:
`test_task_defaults_survive_restart` (two `create_app(Settings(data_dir=…))` boots on one
tmp DB — red on old code, green on fix) and `test_task_defaults_survive_restore`
(assign → `GET /backup/export` → `POST /backup/restore` into the same app → defaults
intact; also red on old code since `_apply_restore` re-ran the wiping upsert). Model rows
created via the public `POST /providers` + `POST /models` APIs (simpler than the session
insert the sketch proposed). Both verified to fail on pre-fix code by stashing
`main.py`/`backup.py`/`providers.py` and re-running. Backend gate: ruff ✓ · mypy strict ✓
· 633 passed (631 + 2).

## Slice 39B — Job deletion API + stale detection (backend)

**Design.**

- `DELETE /api/v1/jobs/{job_id}` → 204:
  - 404 unknown id (existing convention, `jobs.py:173`).
  - 422 if status ∈ {queued, running} — message style "job 'x' cannot be deleted while
    queued/running".
  - Allowed: done | failed (any type — including `chat_turn`).
- `DELETE /api/v1/jobs/failed` (declared BEFORE the `/{job_id}` route) → `{"deleted": n}`;
  optional body `DeleteFailedBody{types?: list[str] | None}` mirroring `RetryFailedBody`.
  Unknown type values in filter → empty match set (same lenient posture as retry-failed).
  Must include ALL failed rows regardless of `retriable` — deleting hopeless failures
  (deleted-material ingests, dead-session chat turns) is precisely the point.
- Stale detection helper in `api/jobs.py` (batched — never N queries):
  collect `material_id`s and `chat_session_id`s from the page's payloads; two
  `SELECT id FROM … WHERE id IN (…)` existence checks against `materials` / 
  `chat_sessions`; map back. Job is `stale` when the entity it references is gone.
  Computed for all listed rows; row without any reference payload → False.
- `JobOut.stale: bool = False`; `JobsSummary.failed_stale: int` (count of failed ∧ stale
  in the whole table, not the page).
- Interaction with ingest material status: untouched (stale flags are presentation +
  deletion targeting only).

**Accept.** Delete endpoints obey status guards; bulk delete ignores retriable and honors
type filters; `GET /jobs` marks seeded-fixture rows stale when fixture material ids don't
exist and alive when they do; summary counts agree with list observations.

**Tests.** `test_jobs_api.py` additions: single-delete success/404/queued-422/running-422;
bulk-delete all + with `types` filter + chat_turn inclusion + zero-match filter; stale
flag true/false cases (insert material → stale=False, delete it → True on refetch);
`failed_stale` accuracy; route-ordering regression (literal `/failed` wins over int path
param — assert a DELETE to `/jobs/failed` never parses "failed" as an id).

**As-built (39B).** Landed as planned with two refinements: (1) `stale` is computed for
**any listed row whose payload reference is unresolvable**, not only failed rows (honest
audit semantics — a done ingest whose material was later deleted is genuinely
source-removed); the UI gates visuals by status, and `failed_stale` filters to failed.
(2) `retry_job`'s response also carries `stale`. The old summary only summed
`failed_retryable` when `counts.get("failed")`; the rewrite sums over the fetched failed
rows unconditionally (equivalent result, one fewer branch). Test-harness notes for the
future: the suite's starlette TestClient has **no `delete(json=…)`** — use
`client.request("DELETE", url, json=…)`, exactly what the 39D frontend fetch will do;
and API-side deletes are invisible to the fixture's long-lived Session identity map via
`session.get()` — assert through fresh queries (`session.query(Job).all()`) or plain ids
captured before the calls. Backend gate: ruff ✓ · mypy strict ✓ · 637 passed (+4:
single-delete guards, bulk delete incl. chat_turn + type filter + zero-match, stale flag
true/false + `failed_stale` before/after material delete, literal-route ordering).

## Slice 39C — Boot-time pruning of done history (backend, config)

**Design.**

- `config.Settings.jobs_done_ttl_days: int = Field(default=14, alias/env prefix CA_)`
  → `CA_JOBS_DONE_TTL_DAYS` (fields-only precedent in `config.py:16–30`).
- New tiny module `app/jobs/pruning.py::prune_done_jobs(session_factory, now=None,
  ttl_days=None)`: deletes `done` rows where coalesce(`finished_at`,`created_at`) <
  cutoff; logs pruned count via structlog; called from `main.py` lifespan right next to
  trash `purge_expired` (`main.py:184`). Runs before workers start; owns a short
  transaction (risk-register "all DB writes short-transactions").
- Failed rows are NEVER pruned here (ADR-089 rationale); queue-integrity rows
  (queued/running) are out of reach; interrupted reclaim in the runner is untouched.

**Accept.** Second boot against a DB with old done rows removes exactly those; fresh-test
suite unaffected; countdown counts appear in boot log.

**Tests.** `test_job_pruning.py`: seed done rows young/old/failed-old/queued; run pruner;
assert exact survivors; ttl override respected.

**As-built (39C).** Landed as planned: `prune_done_jobs(session_factory, ttl_days, now)`
in `app/jobs/pruning.py` (structlog `jobs_done_pruned` event; `rowcount` guarded like
`services/trash.py` for mypy-strict), wired into `create_app()` immediately after the
seeding/trash-purge block (before scheduler/job startup), Settings field
`jobs_done_ttl_days` (`CA_JOBS_DONE_TTL_DAYS`, ge=1). Tests cover the exact-survivor
matrix (old done pruned while young-done/old-failed/old-queued survive), the
`coalesce(finished_at, created_at)` fallback (done row with NULL finished_at), and TTL
override ordering. One test-writing note: distinct sqlite files must live in existing
directories (mkdir in the factory helper).

**Flakiness observation (pre-existing, surfaced by timing shifts):** during slice-C
verification two full-suite runs failed once each on *unrelated* tests —
`test_folders_api::test_delete_cascades_subtree` and
`test_providers_api::test_task_defaults_survive_restore` — both pure-HTTP tests racing
the background JobRunner/scheduler threads; both pass in isolation and three consecutive
full runs were green afterwards. The job system's threads + per-request sessions are an
order-sensitive environment; nothing in 39B/39C touches those paths. Worth a future
round: audit HTTP tests that assert on rows a live runner may concurrently mutate
(deterministic harness or explicit `jobs.stop()` before sensitive requests).

## Slice 39D — Frontend: delete + stale grouping on both surfaces

**Design.**

- `lib/api.ts` (~jobs group): `deleteJob(id)` (204), `deleteFailedJobs(types?)`
  (DELETE w/ optional JSON body like its retry twin), extend `JobInfo` with `stale`,
  `JobsSummary` with `failed_stale`.
- `JobsPage.tsx`:
  - Header gains a secondary actions dropdown (reuse shared `PopoverMenu` grammar)
    beside **Retry all failed**: items **Delete failed…** (respects the page's current
    Type filter — passes it as `types`; label reads "Delete failed (Type)" when filtered),
    **Delete source-missing entries (N)** enabled iff `failed_stale > 0`. Each opens the
    confirm dialog ("This permanently removes N task records. It cannot be undone.").
  - Per-row delete (trash icon) on failed/done rows only, hover-revealed like other row
    kebabs; hidden on queued/running.
  - Failed rows with `stale=true` render muted + a **source removed** chip and hide their
    ⭯ retry affordance (retrying can't succeed).
  - Reuse selection? No — rows stay single-action; the Type filter *is* the grouping
    primitive (deliberate, ADR-089 alternatives-rejected list).
- `ActivityPopover.tsx` failed section:
  - Footer gains **Delete stale (N)** (primary danger-ish text button, shown iff N>0)
    alongside **Retry all N failed**; long-press-free confirm dialog first.
  - Per-row small trash icon on failed rows (top-8) calling single delete with confirm.
  - Stale rows show the same muted treatment; the popover failure count derives from
    `summary.failed` (badge auto-drops after deletes — no extra wiring).
- Both surfaces' mutations invalidate `['jobs-summary']` + `['jobs-list']` (copy the
  retry mutation `invalidate` helper), keep their 2–5 s refetch intervals.
- i18n: keys under `jobs.*` / `activity.*` (page + popover), English catalog; honors the
  `no-literal-string` lint rule.

**Accept.** Deleting the last failed row clears the rail badge within poll cadence; type-
filtered bulk delete matches visible rows; stale chips render; no dead buttons on
non-deletable statuses.

**Tests.** Extend `JobsPage.test.tsx` (header menu delete invoked with expected payload;
per-row delete invocation; stale chip + retry hidden) and `ActivityPopover.test.tsx`
(footer Delete-stale visibility gate on `failed_stale`, row-delete call, confirm dialog
gate before call).

**As-built (39D).** Landed as planned with one backend refinement discovered while
wiring the UI: the stale one-click originally called the bulk endpoint unfiltered — it
would have deleted **all** failures, not just source-missing ones. Added optional
`stale_only: bool` to `DeleteFailedBody` (backend) so *Delete source-missing* removes
exactly the stale rows; retry-failed deliberately did NOT get this (retrying hopeless
rows is meaningless anyway, retriable already excludes them). UI notes:
window.confirm (CoursesPage precedent) gates every destructive action; JobsPage header
uses shared `PopoverMenu` with two danger items; Type-filtered bulk delete passes
`{types:[active]}`; activity popover's delete-all is an icon in the Failed section
header gated on `summary.failed > 0`, and its stale shortcut on
`summary.failed_stale > 0`. Popover tests had a classic pitfall worth remembering:
clicking a menu item before the jobs query resolves clicks a DISABLED item — await a
loaded-row finder before opening menus. Backend 640 green (+1 for stale_only),
frontend lint/typecheck/build + 742 tests green (+7).

## Result

All four slices landed; both user-reported issues are resolved:
(1) failed tasks are deletable individually/by group/stale-group on `/jobs` and in the
popover, with done-history auto-pruning as the only automatic cleanup;
(2) per-capability default task models persist across restarts and restores.

## Non-goals (this round)

- **No cancel verb for queued/running jobs** (distinct semantics from delete; candidate
  for a later round if needed).
- **No per-type group headers / multi-select checkboxes redesign of the Failed tab** —
  the existing URL-addressable Type filter plus filtered bulk delete delivers the
  "delete selected group" ask without a second interaction model.
- **No Settings→Data retention card yet** — TTL ships as documented env default; revisit
  if users want runtime tuning (precedent: `backup-settings.json` overrides).
- **No FK constraints or cascade hooks between entities and `jobs`** — audit-log stance
  (ADR-089); no trash snapshotting of job records (ADR-048 governs content entities).
- **No WS push refresh for deletions** — existing poll cadence is adequate.

## Dependencies & suggested order

- 39A stands entirely alone (touches `providers.py` seeder + two callers + test) — commit
  first as `fix(settings): keep per-capability task defaults across restarts (ADR-090)`
  with docs sync, regardless of B/C/D progress.
- 39B → 39C → 39D; C depends on nothing from B except shared files (can land either side);
  D requires B's endpoints/fields.
- Migration-free: no schema change anywhere in this plan.

## Verification per slice

Standard gates before any commit (AGENTS.md):
backend `ruff check . && mypy . && pytest` (mypy strict clean, esp. new seeder + pruning
module); frontend slices additionally `pnpm lint && pnpm typecheck && pnpm test &&
pnpm build`. Golden-set evals (`pytest tests/evals/`) untouched paths but re-run per rule.
Docs sync via `ca-docs-sync` per landed slice: STATUS changelog entry, module-status row
(**Job retry + task-activity rail** extends with deletion/stale/prune), `docs/usage/
activity.md` user-facing notes, this plan's as-built annotations, ADR rows 089–090
appended to `dev/plans/06-decisions-and-risks.md`.

Commit strategy: 4 commits max — `fix(settings)/ADR-090` (A), `feat(jobs): delete APIs +
stale detection (ADR-089)` (B), `feat(jobs): boot-time done-history pruning` (C),
`feat(jobs): delete + stale controls on jobs surfaces` (D) — each green on the full gate.

## Risks

- **Bulk delete of failed `chat_turn` rows removes forensic traces** of broken sessions —
  accepted: turn content lives in `chat_messages`/`ai_interactions`, the job row is
  transport bookkeeping; confirm dialog names the count.
- **Stale detection correctness** relies on payload key shape; unknown payload shapes are
  simply never marked stale (conservative — false negatives fine, no false positives by
  construction since we require the referenced id AND absence in DB).
- **Boot prune + backup retention interplay**: pruned done rows vanish from older
  backups too (they're full snapshots) — acceptable; failed/audit-bearing state is kept.
- **Restart-simulation test flakiness** (two apps, one engine/file): mitigate by full
  dispose+stop teardown order copied from existing fixtures; sqlite WAL on tmp_path has
  been reliable in the existing two-suite pattern.

## Alternatives rejected

- **Silent auto-delete of failed jobs (user's option 1)** — kills the red-badge signal and
  the record of what happened; contradicts calm-engagement trust posture; stale-group
  one-click achieves identical cleanup effort with explicit consent.
- **FK/cascade from materials→jobs or auto-clean on entity delete** — jobs is JSON-payload
  audit log; a generated column + trigger adds schema machinery for a benefit stale flags
  deliver read-side anyway.
- **Marking instead-of-erroring on missing entities (skip-failed-not-stale)** — the
  handlers already fail correctly; changing pipeline semantics is out of proportion.
- **Guarding the old upsert at the call site with `if session.get(...) is None` duplicated
  in main.py and backup.py** — two copies of the invariant to drift; one exported seeder
  function is the ADR-090 fix's whole point.
- **DELETE bodies everywhere + query param mix** — chose body-shape symmetry with
  `POST /jobs/retry-failed` for the one bulk endpoint; local fetch handles DELETE+body
  reliably (single trusted client, LAN-only server).
