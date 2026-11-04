# Retrieval operations (plan 50 P3a / plan 51 Q3a/Q3b/Q3c2a/Q3c2b1)

Status: **Q3b shipped, plan 50 P3a storage foundation, Q3c1 PostgreSQL
baseline repair, Q3c2a vector backend/provisioning and Q3c2b1
lifecycle/cutover shipped** (2026-11-04). The family contracts, the
`VECTOR_*` job slot, the two bounded aggregates, the admin read surface, the
management/action seam (idempotency, single-active-run lock, stale reaper,
audit) and the Tools → Indexing controls are shipped. Q3c2a implements the
family `VectorBackend` protocol and provisions real `vec_<8hex>` tables;
Q3c2b1 adds real build/backfill/activate/retire/drop and the `VECTOR_CUTOVER`
handler over that boundary. Golden-query quality compare, the quality
activation gate and the full family parity runner remain **Q3c2b2**.

## Contracts

### Vector retrieval contract (plan 50 P3a)

- Canonical: `dev-vector-p0/contracts/vector_contract.py` and
  `vector-contract.fixtures.json` (ADR-0051).
- Vendored byte-identically:
  - `backend/app/storage/vector_contract.py` —
    sha256 `43a2cefe22b9ad0e50f3e5c04d311726d7bb8d123fc0ad66b6dbceeafe7280f2`
  - `backend/tests/fixtures/vector_contract.fixtures.json` —
    sha256 `ad67ec05cd95d29ce62d944e28fedb2e3122df8b82555004011652a8b5af7202`
- `backend/tests/test_vector_contract.py` runs every canonical group and
  asserts byte identity when the dev checkout is next to this one (skips in
  CI/public clones).
- The fixture table also pins the pure helpers study now uses directly
  (`content_hash`, `space_key`).

### Retrieval operations contract (plan 51 Q0)

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

## Vector storage adapter (plan 50 P3a / plan 51 Q3c2a)

`storage/vector_store.py::StudyVectorStore` is the one seam over the
physical index **and** the metadata layer. Search, embedding writes, purge
paths and the retrieval handlers call it; no retrieval DTO or route issues
vector SQL itself. Q3c2a adds the two app-side pieces behind that seam:

- `storage/vector_backends.py` — the family `VectorBackend` protocol
  implemented per dialect (`PgVectorBackend`, `SqliteVecBackend`,
  `LinearBackend`). Every backend shares the caller's session, so a write
  and its metadata registration commit together.
- `storage/vector_provisioning.py` — the only seam allowed to
  `CREATE TABLE` a vector index; it writes `vector_spaces.index_table` in
  the same transaction as the DDL.
- `storage/vector_schema.py` — the `vec_<8hex>` naming/validation rule and
  the Alembic autogenerate exemption for extension-managed tables.

### What is real now

Migration `0012_vector_spaces` adds:

- `vector_spaces` — one `content` space (`id = legacy-chunk-vecs`, the id
  Q3a/Q3b rollups already carry), model/dim from `vec_meta`, provider from
  the embeddings assignment, status `active`.
- `vector_documents` — a material source handle (`kind='material'`,
  `source_id` = material UUID, `profile_id` scope), unique per
  space/kind/source.
- `vector_records` — a chunk's `body` view with the family `content_hash`,
  `chunk_index`, the study `rowid`, and since 0014 the space-local
  `chunk_id`; unique `(document, view, chunk_index)` and
  `(space_id, chunk_id)`. Legacy rows keep `chunk_id = id`; a building
  space gets a deterministic `uuid5(space, chunk)` record id, so a search
  hit still maps to the chunk without sharing the global primary key.

The migration backfills the space from `vec_meta` and documents/records from
`chunk_vec_ids` + chunks/materials. It never writes coverage. Rows the SQL
backfill maps without hashing stay `content_hash=''` until
`StudyVectorStore.backfill_metadata()` (idempotent, batch-bounded) fills
them.

### Physical provisioning and the content migration (Q3c2a)

| Family concept | Study source (Q3c2a) |
|---|---|
| space | one `content` space, id `legacy-chunk-vecs` |
| model / dim | `vec_meta` (mirrored in `vector_spaces`) |
| backend | `pgvector` (PostgreSQL) / `sqlite_vec` (SQLite) / `linear` fallback |
| index table | `vec_<8hex>` (`vec_dfbcce9b` for the content space) |
| rowid map | `vector_records.rowid` (sqlite-vec); pgvector keys `record_id` |
| document | material (`vector_documents`) |
| record | chunk `body` (`vector_records`, `chunk_id` hydration handle) |
| coverage | latest `retrieval_coverage_snapshots` row only |
| runs | `jobs` rows with the three `VECTOR_*` types |
| query health | `retrieval_query_rollups` |

The physical name is deterministic: a UUID space id uses its first eight hex
characters; study's string id `legacy-chunk-vecs` uses four BLAKE2b bytes
(`vec_dfbcce9b`). Only `vec_` + eight lowercase hex is accepted, which is
also the boundary for the dynamic SQL the backends issue.

- **PostgreSQL** — `CREATE EXTENSION vector` (hard prerequisite),
  `record_id UUID PRIMARY KEY REFERENCES vector_records(id) ON DELETE
  CASCADE`, `embedding vector(dim) NOT NULL`, and
  `ix_<table>_hnsw USING hnsw (embedding vector_cosine_ops)`. HNSW supports
  at most 2,000 dimensions; runtime provisioning refuses a larger space and
  the one-time migration leaves it on the legacy store rather than silently
  creating an unindexed table. Scope is joined into the ANN query
  (`r.space_id`, view and the
  document predicate), never a Python post-filter; `hnsw.ef_search` is set
  per transaction and at or below `EXACT_SCAN_THRESHOLD` scoped candidates
  the scan is forced exact.
- **SQLite** — `vec0(record_rowid INTEGER PRIMARY KEY, embedding
  float[dim] distance_metric=cosine)`. `vector_records.rowid` is the rowid
  map, matching `chunk_vec_ids` for the content space. vec0 is brute force,
  so it answers exactly when the whole scoped index is requested; above the
  threshold it over-fetches `k` and post-filters against metadata, with the
  allowed set always coming from SQL (never from the ANN result).
- **Linear** — exact cosine over `vector_records.embedding`, `ann=False`,
  capped at `LINEAR_CAP_ROWS`, deterministic tie-breaking. It is the
  factory's honest fallback when the extension/driver probe fails and the
  backend used by an explicitly linear space.

Migration `0013_vector_space_provisioning` is the one-time content move: it
provisions `vec_dfbcce9b` for every space still on `chunk_vecs`, copies the
legacy rows (`chunk_vecs ⨝ chunk_vec_ids ⨝ vector_records`), verifies the
copied row count, and only then updates `vector_spaces.index_table` — all in
the migration transaction. `chunk_vecs` and `chunk_vec_ids` are left intact
and are still dual-written while the space is `active`. A dialect without
the extension (or a dimension above the HNSW ceiling) keeps the legacy
store and does not fail the upgrade; the read path stays honest and the
write path reports the deferred provisioning.

A model/dimension change still never drops a table. `vectors.ensure_table`
raises `VectorSpaceChangeRequired` (old/new model+dim, "chunk_vecs was left
untouched"); the old vectors remain searchable until Q3c2b's explicit
new-space/cutover handoff. The metadata row must agree with `vec_meta`; a
disagreement is the same explicit error, never an in-place rewrite.

### Space lifecycle and cutover (Q3c2b1)

`services/retrieval/lifecycle.py` owns the pointer and the physical tables;
the HTTP/action seam wraps it, never duplicates it.

- **Build** creates a `building` `vector_spaces` row with the real
  provider/model/dim/prefix metadata, then calls
  `vector_provisioning.provision_space` (the only DDL seam) and returns the
  real space id/key and `vec_<8hex>` table. A matching building space is
  reused idempotently; a different one under the same name is refused.
- **Backfill** is the ordinary `VECTOR_REINDEX` writer scoped by
  `payload.space_id`. `StudyVectorStore(session, space_id=...)` writes
  documents/records and backend rows for that space only; the active space is
  untouched. `vector_records.chunk_id` (migration `0014`) is the space-local
  hydration handle, while the global primary key stays the deterministic
  `uuid5(space, chunk)` record id.
- **Activate** verifies the physical table/dim/ANN index and the latest
  coverage snapshot, retires every previous `active` row, then flips the one
  active pointer in one transaction. It is coverage-gated only:
  `quality="not_sampled"` is reported explicitly (Q3c2b2).
- **Retire** accepts a non-active space (building or already retired).
  **Drop** requires a retired space, the typed space name, and the 7-day grace
  period unless `force` is set together with the typed name. The active space
  can never be dropped.
- **Cutover** (`VECTOR_CUTOVER`) runs the same backfill, refuses a
  non-`pass` coverage gate, activates, retires the previous space and reports
  the activated/previous ids plus `quality="not_sampled"`. Reindex,
  maintenance and cutover keep the Q3b idempotency key, one-active-run lock,
  cancel and retry; build/activate/retire/drop execute as a real job row under
  the same lock and replay semantics.

**One active row.** Study's historical partial unique index is per name;
activation therefore retires *all* other active rows before flipping, so the
database can never expose two searchable spaces. Readers resolve that one
active row (then fall back to `vec_meta` only for a pre-metadata store).

**Compatibility boundary (`chunk_vecs` is still the fallback).** Activation
does not drop `chunk_vecs`. It is dual-written only while the legacy
`legacy-chunk-vecs` space is active; once another space is active, writes go
to that space and `chunk_vecs` is read-dead but retained. Dropping the retired
legacy space is the explicit retirement step and removes `chunk_vecs` /
`chunk_vec_ids` (plus its provisioned table). Until then the overview says the
compatibility store is retained.

Until the legacy space is retired, `chunk_vecs` is the compatibility store:

- writes go to both the provisioned backend (primary) and `chunk_vecs`
  (mirror) in the caller's transaction;
- search reads the provisioned backend; if the extension or table is
  missing it falls back to the legacy `vector` search, and a partial
  backfill is never reported as coverage (coverage comes only from a
  snapshot);
- `VECTOR_REINDEX` verifies existing vectors through
  `stored_chunk_ids()`, which is the legacy map merged with the metadata
  rowids, and writes each new batch through the backend;
- the maintenance actions address the active table:
  `VECTOR_MAINTENANCE` vacuum uses `StudyVectorStore.index_table`, and
  PostgreSQL `index-rebuild` rebuilds `ix_<active>_hnsw` (a legacy or
  unprovisioned space gets the honest "run a full VECTOR_REINDEX" note).

Cold/partial states are explicit: no `vec_meta` dim → no space row and
`empty`; a provisioned table with missing rows → `health()` says `partial`
and the backend keeps returning what exists; a missing table → healthy
`ok=false` detail and the legacy fallback answers.

### PostgreSQL chain and backfill assertions (plan 51 Q3c1)

`tests/test_migrations_postgres.py` now runs on the pgvector test container
instead of skipping, and the full chain `0001_baseline` →
`0013_vector_space_provisioning` is green. Repaired pre-0012 incompatibilities (final
schema unchanged; details in [migrations.md](migrations.md#postgresql-chain-plan-51-q3c1)):

- six boolean `server_default` values (`0`/`1`) became `sa.false()` /
  `sa.true()`; PostgreSQL rejects `BOOLEAN DEFAULT 0` at `CREATE TABLE`;
- the baseline decision-slot seed casts its bind parameter, fixing
  PostgreSQL's `AmbiguousParameter` (`text` vs `character varying`);
- the 0002–0011 `batch_alter_table(recreate="always")` calls use a local
  `_recreate_mode()` (`always` on SQLite, `auto` on PostgreSQL), because a
  PostgreSQL table copy drops the primary key while dependent FKs exist.

The PG suite seeds a real legacy store at 0011 (`vec_meta`, `chunk_vecs`,
`chunk_vec_ids` + materials/chunks) and, after upgrading, asserts the
`content`/`legacy-chunk-vecs` space row, the document/record backfill shape,
rowid parity with the reverse map, content hashes, no fabricated coverage
snapshot, model/dim agreement with `vec_meta`, the Q3b partial indexes on
`jobs`, and a 0013 downgrade/upgrade that leaves `chunk_vecs` intact. Since
0013 runs at head, the assertion also pins the provisioned
`vec_dfbcce9b` table, its HNSW index and copied rows.

A store with no `vec_meta` dim is `empty` and has **no** space row; an
existing store with no snapshot is `cold`/`never reconciled`; no number is
invented.

### Adapter surface

- identity/read: `content_space()` (active or explicit `space_id`),
  `content_space_for()`, `space_for()`, `read_meta()`, `index_table`,
  `index_name`, `vector_count()`, `stored_chunk_ids()`,
  `stored_chunk_hashes()`, `rowid_map()`, `document_count()`,
  `record_count()`, `documents()`, `records()`, `record_for_rowid()`,
  `metadata_complete()`, `health()`, `space_status()`;
- writes: `store()` (space-aware model guard + legacy mirror only while the
  legacy space is active + metadata registration + backend upsert),
  `delete_for_extraction()`, `delete_rowids()`, `unregister_records()`,
  `backfill_metadata()`, `ensure_content_space()`, `provision()`,
  `backfill_physical()`;
- reads: `search()` with optional `course_id` / `material_ids` /
  `profile_id` scope, hydrating `record_id -> chunk_id` through
  `vector_records.chunk_id`, so the unchanged `(chunk id, distance)` shape
  survives two coexisting spaces. A non-legacy space never falls back to the
  legacy store.

`legacy.load_store()` resolves the active space through this adapter, so the
admin read surface reports the metadata space identity, the real active
table and the backend's row count. `health()`/`space_status()` supply the
truthful detail rendered in the overview notes and `last_error`;
`metadata_complete()` gates the metadata document count, and an unmapped
physical store falls back to the distinct-material count instead of
reporting a fabricated `0`.

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
  (`REINDEX INDEX CONCURRENTLY` on the active `ix_<vec_>_hnsw` on
  PostgreSQL; SQLite returns an honest "run a full reindex" note), `retry-failed` (scoped reindex over
  `chunk_ids`).
- **`VECTOR_CUTOVER`** — backfills the candidate (`space_id`), enforces the
  coverage gate, activates it, retires the previous active space and reports
  `quality="not_sampled"`. A partial/limited pass fails explicitly; an
  already-active candidate is an idempotent success. The retired legacy
  `chunk_vecs` store is retained until an explicit drop.

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

- `GET /overview?window=24h|7d|30d|90d` (includes the space list)
- `GET /spaces` (all real spaces + `active_space_id`)
- `GET /coverage?space=` (any persisted space; cold/unknown is honest)
- `GET /runs?limit=`
- `GET /query-health?window=` (the active space's real id)

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
| `POST /spaces` | `name?`, `provider?`, `model?`, `dim?`, `normalize?`, prefixes | Build/provision a real `building` space; returns its id/key/table. Required key; a matching building space replays. |
| `POST /spaces/{id}/activate` | `Idempotency-Key` | Physical + coverage gate; retires every previous active and flips the pointer. Reports `quality="not_sampled"`. |
| `POST /spaces/{id}/retire` | `confirm_space_name`, key | Typed non-active retirement; active → 409. |
| `POST /spaces/{id}/drop` | `confirm_space_name`, `force`, key | Typed retired-space drop after the 7-day grace (or forced); active/building → 409. |
| `POST /cutover` | `space_id`, `limit`, `batch_size`, `force`, key | Enqueues `VECTOR_CUTOVER`: backfill, coverage gate, activate, retire previous, keep legacy compatibility. |
| `POST /quality/compare` | — | Structured `409 {"reason":"quality_not_sampled", ...}` — golden-query compare is Q3c2b2, never faked. |

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
| `vector.space.provisioned` | a building space is created/reused | `accepted`/`error` |
| `vector.space.activated` | pointer flip accepted / cutover enqueued | `accepted` |
| `vector.space.retired` | a non-active space retired | `accepted`/`error` |
| `vector.space.dropped` | a retired space dropped | `accepted`/`error` |
| `vector.model.changed` | a build's key differs from the active key | `accepted` |
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
refusal text. Q3c2b1 adds the minimal space controls: build a candidate from
the active space's model/dim, list building/active/retired spaces, cut over or
retire a building space, and drop a retired space only after typing its exact
name. It states explicitly that activation is coverage-gated and quality is
not sampled (Q3c2b2). Every mutation sends a fresh `Idempotency-Key`; a replay
shows the original run instead of a second one.

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

Q3c2a adds backend parity assertions on both dialects:
`tests/test_vector_backends.py` (SQLite) and
`tests/test_vector_backends_postgres.py` compare sqlite-vec/pgvector against
the exact `LinearBackend` over the same unit vectors (identical top-k and
distances), pin the rowid map against `chunk_vec_ids`, and exercise
scope/empty-scope/profile isolation. The PostgreSQL test also switches the
scoped threshold to run the exact and ANN branches and asserts they agree.
`tests/test_search_vector_backend.py` pins FTS/RRF invariance across the
provisioned and forced-legacy paths. The full cross-repo parity runner
remains Q3c2b.

## Q3c2b1 shipped vs Q3c2b2 handoff

Q3c2b1 (this slice) shipped the lifecycle and cutover:

- **Real lifecycle**: build (metadata + `vec_<8hex>` provisioning), bounded
  backfill through the ordinary writer, physical+coverage activation,
  previous-active retirement, typed retire/drop with the 7-day grace.
- **Real cutover**: `VECTOR_CUTOVER` backfills, refuses a non-`pass`
  coverage gate, activates, retires the previous space and keeps the legacy
  compatibility store until an explicit drop. `quality="not_sampled"` is
  reported everywhere instead of a fake quality pass.
- **Two coexisting spaces**: `vector_records.chunk_id` (migration `0014`)
  gives every space-local record a chunk hydration handle; the record id is
  deterministic per `(space, chunk)`, and the rowid is the sqlite-vec rule
  over that id.
- **Space identity**: rollups, coverage snapshots, run DTOs and query health
  all carry the active real space id. The 30/90-day TTL remains the prune
  owner; old-space rows are not rewritten into the new space's history.
- **Search/legacy**: search reads the active space through the backend and
  hydrates `record_id -> chunk_id`; a non-legacy space never falls back to
  the legacy store, and FTS/RRF semantics are unchanged.
- **Tools**: the Indexing card lists spaces and exposes build/cutover/
  retire/drop with typed names and the quality-not-sampled note.

**Q3c2b2 still owns** (explicitly not built here):

1. **Golden-query quality compare** — versioned sets, recall/precision@k,
   before/after space compare, the bad-match drawer, and the HTTP
   `quality/compare` runner. The endpoint answers `quality_not_sampled`
   today.
2. **Full quality activation gate** — activation here requires physical
   health + coverage only. Wiring the quality compare into activation (and
   the `vector.gate.failed` reason vocabulary for quality) is Q3c2b2.
3. **Full family parity runner** — fixture-level status/cold/degraded parity
   and the backend parity tests exist; the cross-repo runner and sha gate
   are Q3c2b2.
4. **Alerts** (`retrieval.*`) and `ai_generations`-style metadata tagging
   remain Q3c3/Q4; no second ledger was invented.
