# Retrieval operations (plan 51 Q3a/Q3b)

Status: **Q3b shipped** (2026-11-04). The family contract, the `VECTOR_*`
job slot, the two bounded aggregates, the admin read surface, the
management/action seam (idempotency, single-active-run lock, stale reaper,
audit) and the Tools → Indexing controls are shipped. The real vector-space
lifecycle/cutover, golden-query quality gates and the full family parity
runner remain Q3c.

## Contract

- Canonical: `dev-vector-p0/contracts/retrieval_ops.py` and
  `retrieval-ops.fixtures.json` (plan 51 Q0).
- Vendored byte-identically:
  - `backend/app/storage/retrieval_ops.py` —
    sha256 `4d3db17c795280a700fc6b39d1ef4383fc67f5e478dce08bae706430ee529551`
  - `backend/tests/fixtures/retrieval_ops.fixtures.json` —
    sha256 `4463cb45ff115ea1fe98838e7b81b46c4bdac9afe3ff865bac7d369c26d8de52`
- The fixture wall is `backend/tests/test_retrieval_ops_contract.py`; it runs
  every canonical group and asserts byte identity when the dev checkout is
  next to this one (skips in CI/public clones).
- The dev `sync-retrieval-ops.sh` ledger still records the **career-main
  handoff**. Study's worktree copy was copied directly from the canonical
  (same bytes); the family ledger/sha gate is not claimed until this branch
  lands on `main`.

There is no `VECTOR_RECONCILE` in Q0. The canonical job names are
`VECTOR_REINDEX`, `VECTOR_MAINTENANCE`, `VECTOR_CUTOVER`; the reconcile pass
runs as `VECTOR_REINDEX`.

## Legacy store adapter

Study has **no vector-space lifecycle** (`vector_spaces`/`vector_documents`
from plan 50 never landed here). Q3a reads the active legacy configuration
honestly:

| Family concept | Study source |
|---|---|
| space | one synthetic `legacy-chunk-vecs` |
| model / dim | `vec_meta` |
| backend | dialect: `pgvector` on PostgreSQL, `sqlite_vec` on SQLite |
| index table | `chunk_vecs` (+ `chunk_vec_ids` mapping) |
| documents / records | distinct material count / vector count |
| coverage | latest `retrieval_coverage_snapshots` row only |
| runs | `jobs` rows with the three `VECTOR_*` types |
| query health | `retrieval_query_rollups` |

A store with no `vec_meta` dim is `empty`; an existing store with no snapshot
is `cold`/`never reconciled`; no number is invented.

## Jobs and handlers

`app/pipelines/retrieval_ops.py`:

- **`VECTOR_REINDEX`** — bounded scan (`limit`, default 500; `batch_size`,
  default 32) over `chunks`. Without `force`, existing vectors are verified
  and skipped at zero provider cost; missing ones are embedded and stored.
  `chunk_ids` focuses a retry. The pass writes the contract result
  `{scanned, embedded, skipped, failed, failed_ids[≤500],
  failed_ids_truncated, gate}` to `jobs.result`. It writes one coverage
  snapshot only when the full corpus was covered; a partial or cancelled run
  publishes none.
- **`VECTOR_MAINTENANCE`** — `orphan-sweep` (vectors/mappings whose chunk is
  gone), `vacuum` (autocommit; PostgreSQL/SQLite), `index-rebuild`
  (`REINDEX INDEX CONCURRENTLY` on PostgreSQL; SQLite returns an honest
  "run a full reindex" note), `retry-failed` (scoped reindex over
  `chunk_ids`).
- **`VECTOR_CUTOVER`** — registered so the closed `JobType` registry stays
  complete, but it **fails honestly**: there is no space lifecycle to cut
  over to. This is Q3b work, not a fake success.

Cancellation goes through the runner's `report()` checkpoint; a cancelled
reindex leaves no coverage snapshot and no result counters.

## Bounded stores

Migration `0010_retrieval_ops` adds:

- `jobs.result` (JSON) — the bounded run-result document.
- `retrieval_query_rollups` — dimensions
  `(space_id, kind, view, degraded_reason, bucket_start, bucket_width)`,
  measures `count`, `zero_results`, `candidates_sum` and a versioned
  `latency_histogram` (`le` buckets + overflow). TTL 30 days.
- `retrieval_coverage_snapshots` — one row per `(space_id, kind, as_of)`
  with total/missing/stale/failed/embedded and nullable ANN recall. TTL 90
  days.

Both are **operational aggregates, not audit ledgers** (ADR-0044's
no-silent-pruning rule does not apply). Query telemetry is appended to a
bounded in-memory deque by the search path and flushed by a daemon every 60
seconds into 5-minute buckets; no query text enters the recorder. Coverage
snapshots are written only by the reconcile pass.

## Read surface

Admin-only, under `/api/v1/admin/retrieval`:

- `GET /overview?window=24h|7d|30d|90d`
- `GET /spaces`
- `GET /coverage?space=`
- `GET /runs?limit=`
- `GET /query-health?window=`

DTOs are shaped by the vendored contract; no payload selects `prompt`,
document text or query text.

## Action surface (Q3b)

Admin-only `POST` under the same namespace. Long work never runs inside the
request: enqueue actions reuse the Q3a `VECTOR_*` handlers.

| Endpoint | Body | Behaviour |
|---|---|---|
| `POST /reindex` | `limit` (≤5000), `batch_size` (≤256), `force`, `chunk_ids?` (≤500), `kind?`, `space_id?` | Enqueues `VECTOR_REINDEX`; `Idempotency-Key` required. `force=false` verifies existing vectors at zero provider cost, `force=true` re-embeds. `chunk_ids` is the scoped-retry path. |
| `POST /maintenance` | `action: orphan-sweep\|vacuum\|index-rebuild\|retry-failed`, `dry_run`, `chunk_ids?` | Enqueues `VECTOR_MAINTENANCE`; required key. `dry_run` is supported only for `orphan-sweep` (counts without deleting); `retry-failed` requires `chunk_ids`. SQLite `index-rebuild` returns the honest “run a full reindex” note. |
| `POST /runs/{id}/cancel` | — | Queued rows become `cancelled` immediately; running rows get the cooperative cancel flag (`cancel_requested=true`) and finish through the runner checkpoint. Terminal rows → 409. |
| `POST /runs/{id}/retry` | `Idempotency-Key` required | Failed/cancelled vector runs enqueue a **new** row with `requeue_of` and a fresh lock; done/running/cutover rows → 409. |
| `POST /spaces`, `/spaces/{id}/{activate,retire,drop}`, `/cutover`, `/quality/compare` | — | Structured `409 {"reason":"unsupported_action", ...}` — there is one legacy space and no lifecycle target. No fake success. |

Responses use the contract shape (`action`, `accepted`, `audit_event`,
`http_status`, `deduplicated`, `run_id`, `status`, `idempotency_key`,
`message`). First enqueue → 202; an idempotent replay → 200 with
`deduplicated=true`; refusals → 409 with `{"reason","message",…}` (the
frontend surfaces `message`).

## Idempotency, lock and stale recovery

Migration `0011_retrieval_run_actions` adds four `jobs` columns and two
partial unique indexes (active statuses only):

- `idempotency_key` (8–120 chars). The service first looks for the same
  `(type, key)` inside the contract's 24 hour window: same payload returns
  the original row; a different payload is a 409 `idempotency_mismatch`.
  After the window, terminal rows no longer block reuse.
- `lock_key = vector_space:legacy-chunk-vecs`. The partial unique index over
  `queued|running` is the DB-level **one active vector run** invariant, so
  two concurrent admins cannot both start work; a different key while one is
  active is a 409 `run_in_progress`.
- `heartbeat_at` is written when the runner claims a vector job and at every
  `report()` checkpoint. `reap_stale_runs` (called at the start of every
  action) fails a `running` row older than 15 minutes, records
  `vector.run.stalled`, clears the lock and lets the next action proceed —
  no restart required. A reaped row is an ordinary failed run that can be
  retried.
- `cancel_requested` is the honest “asked, not yet observed” flag the run
  DTO renders.

Only vector rows carry these handles; the generic job enqueue contract is
unchanged for every other job family.

**Cancel/retry keys:** enqueue actions (`reindex`, `maintenance`, and the new
row created by `retry`) require a key. Cancel is state-driven (repeat on a
terminal run is a 409), so it carries no key.

## Audit

Actions write the existing family `audit_events` table through the small
`services/retrieval/audit.py` emitter — **no second ledger**:

| Event | When | Outcome |
|---|---|---|
| `vector.reindex.started` | reindex accepted/enqueued | `accepted` |
| `vector.maintenance.started` | maintenance accepted/enqueued | `accepted` |
| `vector.reindex.cancelled` | queued cancel or running cancel request | `accepted` |
| `vector.reindex.retried` | a new retry row is enqueued | `accepted` |
| `vector.run.stalled` | stale reaper fails a running row | `error` |
| `vector.gate.failed` | a full reconcile finishes with `gate=fail` | `fail` |

`actor` is the admin email (`system` for reaper/gate), `resource` is
`space:legacy-chunk-vecs` or `run:<id>`, and `outcome` is a short token.
No raw document/query/prompt text is written or returned.

## Tools → Indexing and settings map

`RetrievalStatusCard` (inside Settings → Tools → Indexing, admin-only) is the
control surface: reindex (verify/force), recent runs with true
queued/running/succeeded/failed/cancelled states and result counters, cancel
and retry, typed maintenance with the orphan-sweep dry run, and structured
refusal text. Every mutation sends a fresh `Idempotency-Key`; a replay shows
the original run instead of a second one. The legacy-space warning
("no build/activate/cutover lifecycle") stays visible.

The study settings map (`contracts/settings-map.json`) marks
`tools.retrieval` **aligned** and hosts it in the `indexing` section;
`tools.indexing` remains the user-scoped semantic-search/OCR domain. The dev
canonical still says `pending (plan 51 Q3)` — re-vendoring it (plus career's
copy) is the sync handoff when this branch is ready for adoption.

## Parity

`tests/test_retrieval_ops_parity.py` pins study's emitted run-status, cold
and degraded tokens to the shared career/study fixture table: every status
maps into the contract `RunStatus`, a cold store reports `as_of=null`,
`coverage=null`, `gate=unknown`, and degraded reasons stay inside the closed
set. This is fixture-level parity, not the full family runner.

## Q3c handoff (explicitly not shipped)

- Vector-space lifecycle: `vector_spaces`/`vector_documents`/`vector_records`
  (build, activate, retire, drop), a real space id in the rollups and the
  `VECTOR_CUTOVER` target. Until then cutover refuses and the API returns
  `unsupported_action`.
- Golden-query quality gates and the pre-cutover compare/quality surface.
- The full family parity/family gate and PG baseline repair if the existing
  chain is still blocked.
- Alerts (`retrieval.*` notification kinds) and `ai_generations`-style
  metadata tagging. Study's equivalent ledger is `ai_interactions`, which
  still has no metadata/prompt column; no second ledger was invented.
