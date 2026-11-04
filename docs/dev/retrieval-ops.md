# Retrieval operations (plan 50 P3a / plan 51 Q3a/Q3b/Q3c2a)

Status: **Q3b shipped, plan 50 P3a storage foundation, Q3c1 PostgreSQL
baseline repair and Q3c2a vector backend/provisioning shipped** (2026-11-04).
The family contracts, the `VECTOR_*` job slot, the two bounded aggregates,
the admin read surface, the management/action seam (idempotency,
single-active-run lock, stale reaper, audit) and the Tools → Indexing
controls are shipped. Plan 50 P3a adds the portable vector metadata; Q3c1
repairs the PostgreSQL chain through `0012_vector_spaces`; Q3c2a implements
the family `VectorBackend` protocol over that metadata, provisions the
content space's real `vec_<8hex>` table (pgvector/HNSW or sqlite-vec), and
migrates the legacy vectors onto it. The space lifecycle/cutover, golden-query
quality gates and the full family parity runner remain **Q3c2b**.

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
  `chunk_index`, and the study `rowid`; unique
  `(document, view, chunk_index)`. The record id **is** the chunk id, so a
  search hit maps to the chunk without a second lookup.

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
| record | chunk `body` (`vector_records`, id = chunk id) |
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

### Compatibility boundary (`chunk_vecs` is still the fallback)

Until Q3c2b retires it, `chunk_vecs` is the compatibility store:

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

- identity/read: `content_space()`, `content_space_for()`, `read_meta()`,
  `index_table`, `index_name`, `vector_count()`, `stored_chunk_ids()`,
  `rowid_map()`, `document_count()`, `record_count()`, `documents()`,
  `records()`, `record_for_rowid()`, `metadata_complete()`, `health()`,
  `space_status()`;
- writes: `store()` (model guard + legacy mirror + metadata registration +
  backend upsert), `delete_for_extraction()`, `delete_rowids()`,
  `unregister_records()`, `backfill_metadata()`, `ensure_content_space()`,
  `provision()`, `backfill_physical()`;
- reads: `search()` with optional `course_id` / `material_ids` /
  `profile_id` scope, returning the unchanged `(chunk id, distance)` shape.

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
- **`VECTOR_CUTOVER`** — registered so the closed `JobType` registry stays
  complete, but it **fails honestly**: there is no space lifecycle to cut
  over to. This is Q3c2b work, not a fake success.

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
the original run instead of a second one. The status card still warns that
the build/activate/cutover lifecycle is not shipped, and now says the
`chunk_vecs` compatibility store remains the fallback behind the provisioned
`vec_<8hex>` backend.

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

## Q3c2a shipped vs Q3c2b handoff

Q3c2a (this slice) shipped the backend and provisioning boundary:

- **Backend protocol**: `PgVectorBackend` (filtered HNSW cosine, exact below
  the scoped threshold), `SqliteVecBackend` (vec0 + `vector_records.rowid`
  map, exact/over-fetch post-filter), and `LinearBackend` (exact scan over
  `vector_records.embedding`, honest `ann=False`) implement every method of
  the vendored protocol. The factory probes the extension/driver and never
  fakes ANN.
- **Physical provisioning**: `vec_<8hex>` creation, HNSW/vec0 DDL and the
  atomic `index_table` write live in `storage/vector_provisioning.py`.
  Writes provision off the request path; reads never issue DDL.
- **Content migration**: migration `0013_vector_space_provisioning` copies
  `chunk_vecs` into `vec_dfbcce9b`, verifies counts and switches
  `index_table`; `chunk_vecs` remains the dual-written fallback.
- **Search adoption**: `StudyVectorStore.search()` routes the content space
  through the backend with a hard document scope (`course_id` /
  `material_ids` / `profile_id`), and falls back to the legacy search when
  the backend is unavailable. `retrieve_chunks_hybrid` and the FTS/RRF
  weights are untouched.
- **Truthful status**: `health()`/`space_status()` feed the overview notes
  and `last_error`; `records` is the active backend count; a partial
  backfill says `partial`, a missing table says `ok=false`.

**Q3c2b still owns** (explicitly not built here):

1. **Lifecycle actions** — `POST /spaces` (create a `building` space),
   `/spaces/{id}/{activate,retire,drop}`, with the audited action seam and
   the `vector_spaces` status/timestamp transitions. The metadata unique
   keys (`uq_vector_spaces_name_active`, `uq_vector_spaces_index_table`)
   and the provisioning seam exist; the request handlers currently answer
   the structured `unsupported` 409.
2. **Cutover** — compose the same materials into the building space (new
   per-space document/record ids so the two spaces can coexist), enforce the
   writer guard, move the active pointer, enqueue the app-side
   `POSTING_REMAP`-style invalidation, then retire the legacy `content`
   space. `VECTOR_CUTOVER` still fails honestly.
3. **Legacy retirement** — stop the `chunk_vecs` dual write, drop
   `chunk_vecs`/`chunk_vec_ids` after the purge grace period, and make
   `StudyVectorStore._ensure_physical` a no-op for the provisioned space.
4. **Space identity migration** — rollups/coverage still key
   `legacy-chunk-vecs`; Q3c2b decides whether a cutover re-keys the old
   operational aggregates or lets the 30/90-day TTL expire them.
5. **Quality gates** — versioned golden-query sets, recall/precision@k
   compare and the coverage+quality activation gate (no quality endpoints
   or runner were added).
6. **Full family parity/family gate** — the PG baseline repair landed in
   Q3c1; the cross-repo parity runner and sha gate are Q3c2b.
7. **Alerts** (`retrieval.*` notification kinds) and `ai_generations`-style
   metadata tagging. Study's equivalent ledger is `ai_interactions`, which
   still has no metadata/prompt column; no second ledger was invented.
