# Retrieval operations (plan 50 P3a / plan 51 Q3a/Q3b/Q3c2a/Q3c2b1/Q3c2b2/Q3c3a/Q3c3b)

Status: **Q3b shipped, plan 50 P3a storage foundation, Q3c1 PostgreSQL
baseline repair, Q3c2a vector backend/provisioning, Q3c2b1
lifecycle/cutover, Q3c2b2 golden-query quality + gate, Q3c3a
alerts/generation tagging/canonical adoption and Q3c3b read-only retrieval
observation shipped** (2026-11-04). The
family contracts, the `VECTOR_*` job slot, the two bounded aggregates, the
admin read surface, the management/action seam (idempotency,
single-active-run lock, stale reaper, audit), the Tools → Indexing controls,
the versioned golden-query quality compare, the ten boot-seeded alerts, the
caller-supplied embedding tags, the read-only observation card inside
Tools → Indexing and the cross-repo parity runner are shipped.
Activation and cutover require physical health, coverage **and** the
pre-cutover quality compare. The family closeout remains Q5.

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

- `vector_spaces` — one `content` space (`id = v1-chunk-vecs`, the id
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
| space | one `content` space, id `v1-chunk-vecs` |
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
characters; study's string id `v1-chunk-vecs` uses four BLAKE2b bytes
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
- **Activate** verifies the physical table/dim/ANN index, the latest
  coverage snapshot **and** the pre-cutover golden-query compare, retires
  every previous `active` row, then flips the one active pointer in one
  transaction. Missing/blocked quality is a structured refusal
  (`quality_state="not_sampled"`/`"blocked"`); a below-floor compare is
  `quality="fail"`. There is no `quality=not_sampled` success path.
- **Retire** accepts a non-active space (building or already retired).
  **Drop** requires a retired space, the typed space name, and the 7-day grace
  period unless `force` is set together with the typed name. The active space
  can never be dropped.
- **Cutover** (`VECTOR_CUTOVER`) runs the same backfill, refuses a
  non-`pass` coverage gate, runs the golden-query compare, refuses below the
  floor, then activates and retires the previous space. The run result
  carries the compare DTO, bad matches and the activation gate. Reindex,
  maintenance and cutover keep the Q3b idempotency key, one-active-run lock,
  cancel and retry; build/activate/retire/drop execute as a real job row under
  the same lock and replay semantics.

**One active row.** Study's historical partial unique index is per name;
activation therefore retires *all* other active rows before flipping, so the
database can never expose two searchable spaces. Readers resolve that one
active row (then fall back to `vec_meta` only for a pre-metadata store).

**Compatibility boundary (`chunk_vecs` is still the fallback).** Activation
does not drop `chunk_vecs`. It is dual-written only while the legacy
`v1-chunk-vecs` space is active; once another space is active, writes go
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
`content`/`v1-chunk-vecs` space row, the document/record backfill shape,
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
  coverage gate, runs the golden-query quality compare and refuses below the
  floor, then activates and retires the previous active space. The run result
  carries `quality` (the compare DTO), `bad_matches`, `quality_state` and
  `activation_gate`. A partial/limited pass fails explicitly; an
  already-active candidate is an idempotent no-op with
  `quality_state="already_active"` (no re-compare, no quality pass claimed).
  The retired legacy `chunk_vecs` store is retained until an explicit drop.

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
- `GET /quality?space=` (the versioned set + newest sampled compare)
- `GET /usage?window=` (embed calls/tokens by day, space and kind from the
  caller-supplied `ai_interactions.metadata` tags; `errors` and token budget
  are honest gaps, never invented)

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
| `POST /spaces/{id}/activate` | `Idempotency-Key` | Physical + coverage + golden-query quality gate; retires every previous active and flips the pointer. A below-floor compare refuses with `quality_gate_failed` and the persisted `quality`/`activation_gate`; a missing/blocked set refuses with `quality_state="not_sampled"`/`"blocked"`. |
| `POST /spaces/{id}/retire` | `confirm_space_name`, key | Typed non-active retirement; active → 409. |
| `POST /spaces/{id}/drop` | `confirm_space_name`, `force`, key | Typed retired-space drop after the 7-day grace (or forced); active/building → 409. |
| `POST /cutover` | `space_id`, `limit`, `batch_size`, `force`, key | Enqueues `VECTOR_CUTOVER`: backfill, coverage gate, quality gate, activate, retire previous, keep legacy compatibility. The enqueue response reports `quality_state="pending"`; the run result carries the gate evidence. |
| `POST /quality/compare` | `space_id`, `compare_space_id`, `Idempotency-Key` | Runs the versioned golden set against the baseline and candidate through the real backend; returns `quality` (candidate block), `quality_compare` (the contract DTO), `bad_matches` and `gate`. Persists the compare on a `VECTOR_CUTOVER` job result (no new ledger); same-key replay returns it. |
| `GET /quality?space=` | — | The versioned set summary plus the newest persisted compare: `state` is `no_golden_set`/`not_sampled`/`sampled`/`stale_compare`, with recall/precision vs floor, bad matches and the gate. Query text never appears. |

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
- `lock_key = vector_space:v1-chunk-vecs`. The partial unique index over
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
`space:v1-chunk-vecs` or `run:<id>`, and `outcome` is a short token.
No raw document/query/prompt text is written or returned.

## Tools → Indexing and settings map

`RetrievalStatusCard` (inside Settings → Tools → Indexing, admin-only) is the
control surface: reindex (verify/force), recent runs with true
queued/running/succeeded/failed/cancelled states and result counters, cancel
and retry, typed maintenance with the orphan-sweep dry run, and structured
refusal text. It lists spaces with their coverage **and quality gate** state,
builds a candidate from the active space's model/dim, and exposes activate,
cutover, retire and typed drop. `RetrievalQualityPanel` shows the golden set
version/k, recall/precision against the floor, pass/fail, the gate state and a
bad-match drawer (chunk/document ids, view, distance/score — never document or
query text). It can run the compare against the active space. Activation and
cutover refusals render the structured `activation_gate.reasons`. Every
mutation sends a fresh `Idempotency-Key`; a replay shows the original run
instead of a second one.

The study settings map (`contracts/settings-map.json`) marks
`tools.retrieval` **aligned** and hosts it in the `indexing` section;
`tools.indexing` remains the user-scoped semantic-search/OCR domain. The dev
canonical still says `pending (plan 51 Q3)` — re-vendoring it (plus career's
copy) is the sync handoff when this branch is ready for adoption.

## Parity

`tests/test_retrieval_ops_parity.py` pins study's emitted run-status, cold,
degraded, quality and gate tokens to the shared career/study fixture table:
every status maps into the contract `RunStatus`, a cold store reports
`as_of=null`, `coverage=null`, `gate=unknown`, and the quality read reports a
gate token from the fixture set with no query text. `tests/
test_retrieval_ops_family_parity.py` runs `services/retrieval/parity.py` over
the sibling career checkout and the dev canonical: it compares the vendored
contract/fixture bytes, runs every shared quality case through the vendored
scorer, pins the DTO shapes and records the sha plus the sync-gate status. It
does **not** claim the family `--strict` gate: the canonical ledger still
records only career, and the canonical settings map still says
`pending (plan 51 Q3)` for study.

**Parity evidence recorded 2026-11-04** (`run_family_parity()`):
both vendored files match career and the dev canonical byte-for-byte —
`retrieval_ops.py` sha256
`4d3db17c795280a700fc6b39d1ef4383fc67f5e478dce08bae706430ee529551`,
`retrieval-ops.fixtures.json` sha256
`4463cb45ff115ea1fe98838e7b81b46c4bdac9afe3ff865bac7d369c26d8de52` — and
every vocabulary, quality-floor, quality-case and DTO-shape check passes.
At Q3c2b2 `strict=false` with blockers `sync-ledger:study-assistant` (the
ledger had no study row; `ledger:study-assistant=""`) and
`settings-map:canonical-study-pending` (canonical adopter
`pending (plan 51 Q3)`). After the Q3c3a canonical adoption and the
study-main merge, both are green and `strict=true`.

**Q3c3a update.** The `/dev` settings canonical now has both career and study
`tools.retrieval: aligned`; `dev-vector-p0/contracts/retrieval-ops.sync.json`
records study's two vendored sha values (with a branch-adoption note). The
runner reads the settings canonical from `/dev` (contract ledger/bytes stay in
`dev-vector-p0`) and adds a `study-main-adoption` check against
`/study-assistant`. Result now: every vocabulary/quality/DTO/byte/ledger/
settings/adoption check passes, `strict=true` with no blockers. If the main
checkout is absent the runner records `adoption:study-main-unverified` instead
of claiming strict.

Q3c2a adds backend parity assertions on both dialects:
`tests/test_vector_backends.py` (SQLite) and
`tests/test_vector_backends_postgres.py` compare sqlite-vec/pgvector against
the exact `LinearBackend` over the same unit vectors (identical top-k and
distances), pin the rowid map against `chunk_vec_ids`, and exercise
scope/empty-scope/profile isolation. The PostgreSQL test also switches the
scoped threshold to run the exact and ANN branches and asserts they agree.
Q3c2b2 adds the PG quality twin: the golden compare scores the same
recall/precision and the activation gate refuses/passes identically on
pgvector and SQLite-vec. `tests/test_search_vector_backend.py` pins FTS/RRF
invariance across the provisioned and forced-legacy paths.

## Quality set, compare and gate runbook (Q3c2b2)

**Authoring a golden set.** The admin fixture is
`backend/app/data/retrieval/golden_queries.json` (packaged with the app). It
ships **empty** on purpose: a fresh install has no admin-authored set, so
activation/cutover refuse rather than inventing a pass. Record one versioned
set per space:

```json
{
  "schemaVersion": 1,
  "sets": [
    {
      "spaceId": "content",
      "setVersion": 1,
      "k": 5,
      "floor": { "recall": 0.8, "precision": 0.5 },
      "queries": [
        {
          "queryId": "q-vectors-1",
          "query": "cross product definition",
          "expectedDocumentIds": ["<material-uuid>"],
          "k": 5
        }
      ]
    }
  ]
}
```

`spaceId` is the persisted space id (preferred) or its name; the newest
`setVersion` wins. `expectedDocumentIds` are **material ids** for the study
content space (`vector_documents.source_id` where `kind="material"`);
chunk ids appear only in the bad-match evidence. UUID-shaped ids are
normalized, so a hex-form fixture still matches. The floor is validated
through the family contract; the contract defaults are recall `0.80` and
precision `0.50`.

**Running the compare.** `POST /admin/retrieval/quality/compare` with
`{space_id, compare_space_id}` and an `Idempotency-Key`. It embeds each golden
query once, runs the same bounded backend search the live path uses on both
spaces, maps hits to material ids, and scores recall/precision@k through
`storage/retrieval_ops.evaluate_quality_compare`. The compare is deterministic
(hits sort by `(distance, chunk_id)`, ids are de-duplicated in hit order) and
bounded (at most `k × 3`, capped at 300 hits; no full-document work). The
result is persisted on the `VECTOR_CUTOVER` job's `result.quality` (the
contract `QualityCompareDTO`), `result.bad_matches`, and `result.gate`; a
same-key replay returns that response and the `GET /quality` read shows the
newest evidence. No second ledger is created.

**Gate.** Activation and cutover both require physical health, coverage
(`0.995`) and quality. Outcomes:

- compare passes → `quality="pass"`, `quality_state="sampled"`, `gate="pass"`;
- compare runs but misses the floor → 409 `quality_gate_failed`,
  `quality="fail"`, `quality_state="sampled"`, with `bad_matches` and the
  `activation_gate` persisted on the failed job's `result.refusal`;
- no versioned set → 409 `quality_gate_failed`,
  `quality_state="not_sampled"`, `reasons=["quality_no_golden_set"]`;
- embedder unassigned/failed → 409 `quality_gate_failed`,
  `quality_state="blocked"`, `reasons=["quality_blocked"]`.

`quality="not_sampled"` never appears on a success path.

**Cutover runbook.** 1) author/update the set for the candidate space;
2) build the candidate; 3) run `POST /quality/compare` (or let activation/
cutover run it) and inspect `bad_matches`; 4) enqueue `POST /cutover` and watch
the run; 5) the handler backfills, enforces coverage + quality, activates,
retires the previous space and keeps `chunk_vecs` until the retired legacy
space is dropped. A below-floor cutover leaves the candidate `building` and
the evidence on the failed run.

## Alerts and generation tagging (Q3c3a)

### Alerts through the one notification funnel

Study's bell aggregate (`GET /notifications`, ADR-151) remains the only
delivery surface. Q3c3a adds its missing durable side: migration `0015`
creates the boot-seeded `notification_kinds` registry and the deduped
`notifications` event rows. Every emitter goes through
`services/platform/notifications.py::NotificationService.emit`; there is no
second funnel or mail/webhook path. The ten kinds are the closed
`NotificationKind` vocabulary, seeded from the vendored `ALERT_DEFAULTS`
(kind, threshold, window, dedup scope, daily cap) — adopting the real budget
later only fills the remaining evaluator.

`services/retrieval/alerts.py` evaluates the ten conditions over the Q3a/Q3b/
Q3c read model only (latest coverage snapshot, recent `VECTOR_*` runs, the
persisted quality compare, the 15-minute query rollups, the embeddings
assignment, pgvector extension/table state). It runs on the **existing**
`ScanScheduler` periodic seam (`retrieval_alerts=` callback), never in a
request, and is bounded (`RUN_SCAN_LIMIT`, `DEDUP_ROW_LIMIT`,
`ADMIN_FANOUT_LIMIT=20`).

| Kind | Evaluator |
|---|---|
| `retrieval.coverage_low` | latest coverage snapshot < `0.995` and no active run lock for that space |
| `retrieval.reindex_failed` | latest terminal `VECTOR_*` run per `(space, scope kind)` is `failed` |
| `retrieval.reindex_stalled` | `running` row with no heartbeat/progress for `15 min` |
| `retrieval.quality_gate` | newest persisted golden-query compare `passed=false` (the Q3c2b2 sampled result) |
| `retrieval.query_slo` | 15-minute p95 > `1500 ms` |
| `retrieval.degraded_rate` | one degraded reason > `5%` of 15-minute queries |
| `retrieval.provider_unassigned` | no embeddings task/default assignment |
| `retrieval.index_missing` | PostgreSQL only: `vector` extension or the declared `index_table` absent |
| `retrieval.budget_exhausted` | **honest `unavailable`**: study has no token-denominated embed budget yet; its `monthly_cap_usd` is monetary and is not invented as a token budget |
| `retrieval.space_drop_pending` | retired space past the 7-day drop grace |

The 15-minute p95 path also fixes the telemetry histogram's overflow
accounting: every sample used to increment both the last finite `le` bucket
and `inf`, so the total double-counted and p95 always looked like 10000 ms —
`retrieval.query_slo` could never recover. Overflow now counts only samples
above the largest finite bound, so the p95 follows the real cumulative
buckets (the existing telemetry test still pins the 9000 ms case at 10000).

Dedup and recovery are one operation: active keys are the currently true
conditions; a key whose condition cleared (or whose TTL expired) is released
so a later recurrence is a new event, while the history row stays. Events fan
out to at most 20 active admins (the fixture user is admin), respect the
contract daily cap, and carry structured ids/counts/scores/reasons only.
`assert_no_raw_text` runs on every payload. Manage URLs point at the **shipped**
Tools → Indexing controls: `/settings?tab=tools&section=indexing` (run alerts
add `&detail=<run_id>`, which now opens the observation run drawer);
the embeddings-assignment/budget kinds point at
`/settings?tab=ai&section=tasks`. There is no separate Audit → Retrieval
route in study; the read-only observation sits on the same Tools → Indexing
page.

`GET /notifications` gains `alerts` (active, recipient-scoped, still deduped)
and the bell renders them; recovery removes the alert from the bell without
deleting the event history. Migration `0015_retrieval_alerts` runs both
dialects and drops cleanly.

### Generation-ledger tagging and usage

Study's ledger is `ai_interactions`, not `ai_generations`; migration `0015`
adds the same minimal seam to it: `metadata` (JSON, non-null, `{}`) and
`metadata_schema_version` (non-null, `1`). The **caller** supplies
`space_id`/`kind`/`view`/`chunk_index` through the embed call:
`GatewayEmbedder.embed(..., metadata=...)` → `LLMGateway.record_usage` →
the existing ledger row. `embed_with_tags` keeps legacy one-argument test
embedders working; the real writer paths tag indexing (`kind=material`,
`view=body`, `chunk_index` when the batch is one chunk), reindex (the run's
space/kind/view), live search and the golden-query compare (`kind=query`).
The gateway never invents a tag and no text enters `metadata`.

`GET /admin/retrieval/usage?window=` exposes calls/tokens by day, space and
kind from those tags, with `reindex_calls` separated from query embeds. It
never selects `prompt` (or document/query text). Two honest gaps are explicit
instead of fabricated: study's ledger has no status/error column
(`errors_available=false`) and no token-denominated budget (`budget=null`,
notes say so); missing token counts report `tokens_available=false`.
Untagged legacy rows are `unattributed`, never guessed.

## Read-only retrieval observation (Q3c3b)

The admin-only **Retrieval observation** card is rendered inside the existing
`indexing` settings section, below the Tools controls. There is no new
settings domain, top-level tab, audit route or second ledger: the same page
hosts management (`?tab=tools&section=indexing`) and observation.

- **URL state.** The settings route keeps `tab=tools&section=indexing` and
  gains `&obs=` (`overview`, `spaces`, `runs`, `quality`, `query-health`,
  `failures`, `usage`) plus the pinned `&detail=<id>`. A bare run id opens the
  run drawer (the alerts' existing `&detail=<run_id>` links work unchanged);
  `space:<space_id>` and `quality:<space_id>` select the space and quality
  drawers. Switching sections clears `detail`.
- **Reads only.** The card composes the shipped `GET /admin/retrieval/`
  `overview|spaces|runs|quality|query-health|usage` DTOs. It imports no POST
  client and renders no reindex/compare/cancel/retry control; those stay in
  the Tools card above. A test pins the source-level read-only guarantee.
- **Sections.** Overview (active space/backend/model/dim, honest coverage,
  p50/p95, degraded/zero-result, embed calls/tokens), Spaces (model/dim/
  coverage/quality/gate, drawer), Runs (counters and drawer with stage,
  progress, scope, bounded `failed_ids`), Quality (set/scores/gate plus
  bad-match ids/scores in the drawer), Query health (latency, candidates,
  degraded reasons, per-view hits, ANN sample or honest "not sampled"),
  Failures and Usage.
- **Failures.** There is no `/failures` endpoint and no failures table; the
  card groups structured facts client-side — failed runs (reason
  `gate_failed`/`embed_failed`/`run_failed`, by job type), space failed-document
  counts, a sampled below-floor quality gate, and the query-health degraded
  reasons. Only reason codes, ids and counts render; `run.error`, space
  `last_error` and all document/query text are never shown.
- **Window.** The selector drives the overview, query-health and usage reads
  (`24h`/`7d`/`30d`/`90d`, default `24h`); it is local panel state, not a
  second URL contract.
- **Vocabulary.** The card reuses the family state/degraded/cold/run/gate
  tokens; `no_golden_set`, `not_sampled`, `stale_compare`, never-reconciled
  coverage and `tokens_available=false` stay explicit instead of becoming a
  fabricated pass or zero.
- **No backend change** was needed for this slice.

Tests: `RetrievalObservationPanel.test.tsx` (cold/degraded, section switching
and URL state, run/space/quality drawers, structured failures, usage gaps,
admin-only and the read-only/no-raw-text guards) plus the updated
`IndexingSection.test.tsx` and the i18n wall.

## Q3c2b2 shipped vs Q3c3 handoff

Q3c2b2 shipped:

- **Golden-query sets** — a versioned, admin-authored fixture
  (`app/data/retrieval/golden_queries.json`), loader/selector by space id or
  name, id normalization, and a fixture wall that refuses a malformed set.
- **Quality compare** — the bounded real-backend recall/precision@k compare,
  the contract `QualityCompareDTO`, per-query misses and a bad-match detail
  (chunk/document ids, view, distance/score) with no raw text; persisted on
  the job result with idempotent replay.
- **Quality gate** — activation and both cutover paths require coverage,
  physical health and the compare; refusals carry structured
  `quality`/`quality_state`/`activation_gate` evidence on the failed job.
- **Tools** — the Indexing card shows set/version, scores vs floor,
  pass/fail, gate state, a compare action and a bad-match drawer; gate
  reasons render on refusal.
- **Family parity runner** — `services/retrieval/parity.py` plus the
  cross-repo test; shas and the pending ledger/settings-map blockers are
  recorded, and `strict` stays `false` until the family gate records study.
- **Tests** — SQLite + PostgreSQL quality/gate twins, no-raw-text payload
  assertions, replay/persistence, frontend card/panel coverage.

**Q3c3a shipped** (above): the ten boot-seeded alerts with
dedup/recovery/admin fanout/daily caps, the `ai_interactions` metadata seam +
usage read, and the canonical settings-map/ledger adoption. The canonical
`/dev` settings map now marks both career and study `tools.retrieval`
`aligned`; `dev-vector-p0/contracts/retrieval-ops.sync.json` records study's
bytes with the branch note. At the Q3c3a checkpoint `/study-assistant` main
carried the same vendored bytes and the adoption check passed; the plan 52
T5a re-sync above supersedes those bytes, so main adoption follows its merge.

**Q3c3b shipped** (above): the read-only observation card inside Tools →
Indexing, its URL-synced sections and the pinned `detail=` drawers, composed
only from the shipped read DTOs with no write control and no raw text. Study
keeps the alerts in the existing bell and does not add an Audit → Retrieval
route or a second audit stack.

**Remaining** (explicitly not built here):

1. **Q5 — family closeout** — study parity/health gate evidence, the family
   `--strict` claim once main adopts, the no-raw-vector-SQL/no-second-audit/
   settings-map/audit-vocabulary/no-`vector_events`/no-`prompt` checks, and
   the shared UI promotion under the two-app rule.

## Plan 52 T5a — tokenizer accounting (T5b handoff)

T5a is the **accounting-only** study slice. It vendors the family tokenizer
contract and the token-aware `vector_contract`/`retrieval_ops` DTOs, ships a
real offline tokenizer, and removes the character-divisor estimate. It does
**not** write token-aware chunks, change `space_key`, add token columns to
`vector_records`, run a cutover, or add progress UI.

**Contracts (byte-identical, dev canonical → study).**
`app/storage/tokenizer_contract.py` + `tests/fixtures/tokenizer_contract.fixtures.json`;
`app/storage/vector_contract.py` + `tests/fixtures/vector_contract.fixtures.json`
(stored key, v2 space identity, `IndexRecord` token fields);
`app/storage/retrieval_ops.py` + `tests/fixtures/retrieval_ops.fixtures.json`
(`SpaceTokenizerDTO`/`SpaceChunkDTO`, token-aware space/run fields, the
bounded run progress detail). The dev ledgers record study for all three.
The DTOs are accepted but study does not emit token/progress fields yet.

**Tokenizer service.** `app/ai/tokenizers/service.py` bundles
`app/data/tokenizers/cl100k_base.tiktoken.gz` (gzip + uncompressed BPE
checksums pinned) and builds `tiktoken.Encoding` directly. It never calls
`tiktoken.get_encoding`, imports `tiktoken_ext`, or opens a socket. The
bounded LRU is keyed by `TokenizerSpec.cache_key`; `count`, `encode`,
`decode` and `encode_with_offsets` are available for T5b. Missing/corrupt
assets return a structured `TokenizerUnavailable(reason=…)` and degrade to
the labelled heuristic. Hugging Face is an interface only
(`hf_tokenizer_spec`); study has no concrete HF mapping, so that kind
degrades with `unsupported_tokenizer_kind`. `sentencepiece` stays reserved.

**Accounting seam.** `app/ai/tokenizers/accounting.py` resolves **one**
effective tokenizer for the assigned embedding model
(`TaskAssignment`/`DefaultTaskAssignment` → provider type + external id):

- curated OpenAI embedding models (`text-embedding-3-small`,
  `text-embedding-3-large`, `text-embedding-ada-002`) use the bundled exact
  `cl100k_base`;
- everything else uses the conservative UTF-8/codepoint heuristic
  (`ceil(bytes/2) + ceil(codepoints/8)`), always `exact=False`.

No model-name substring ever selects a tokenizer. `TokenCount` carries
`exact` and the tokenizer identity; callers that persist interaction rows put
`tokenizer`/`tokenizer_exact`/`tokenizer_source` in the same
`ai_interactions.metadata` row (no second ledger, no raw text). Ingest,
trash restore, material editing/course import, chat trace/interactions,
tutor/quiz help, note actions and the gateway ledger all use the seam.
`Chunk.token_count` still stores an integer over the **existing**
character-chunked records; it is not a token-aware chunk write.

**T5b handoff (T5b1 landed the stored key + schema; the write switch is T5b2).**
1. Use `TokenizerService.encode_with_offsets` to replace `pipelines/chunking.py`
   character windows with token windows for a v2 space only; keep the v1
   character path intact.
2. Write `token_count/token_start/token_end` on new token-aware records using
   the columns added by T5b1 (the vendored `vector_contract.IndexRecord`
   shape).
3. Stamp a new v2 space's `space_key` from the vendored v2 pre-image and the
   `ChunkConfig`/tokenizer pair; build/backfill a candidate space, compare
   coverage/quality, then cut over (v1 retained).
4. Extend the accounting seam with the study model-profile registry / admin
   override if T5b needs per-model chunk defaults; do not infer a tokenizer
   from a model name.
5. T5c/T5d: progress DTO emission and UI are still out of scope. The contract
   fields are accepted today; nothing writes `progress_detail`.

## Plan 52 T5b1 — stored space key + token schema (T5b2 handoff)

T5b1 is the **compatibility and schema** half of T5b. It persists the vector
space identity and adds the columns T5b2 will write, but it does **not** make
any chunking token-aware, write token offsets, build a v2 space or cut over.
Existing character chunking, chunk counts and write behavior are unchanged.

**Stored key (migration `0016_vector_space_stored_key`).** Adds the non-null
`vector_spaces.space_key` (`String(64)`). Every existing row is stamped once
with the frozen v1 eight-field pre-image (inlined in the migration, like
Career's `0095`) before the column is made non-null. SQLite upgrades through
batch mode; PostgreSQL alters the nullable column in place. Downgrade drops
the column (the v1 value is rebuildable, not audit data).

The stored value wins everywhere: `StudyVectorStore`'s `ContentSpace.key` /
`as_contract().key`, `services/retrieval/lifecycle.space_key_for`, build
idempotency (`building`/active comparison), activation's
`previous_space_key`, status/DTO reads and `legacy.load_store` all return the
row's value instead of recomputing it. `build_space` computes and persists the
v1 key for a new space. A direct ORM insert without `space_key` stamps the v1
key; T5b2 replaced the earlier refusal so a complete tokenizer/chunk pair now
computes the v2 pre-image (a half-configured pair is still refused). This
closes the pre-image boundary: a later tokenizer/chunker change can never make
an existing row look like a different live space during remap/cutover.

**Schema for T5b2 (migration `0017_vector_token_schema`).**
`vector_spaces` gains `tokenizer_kind`, `tokenizer_identifier`,
`tokenizer_revision`, `tokenizer_artifact_sha256`, `tokenizer_exact`,
`max_input_tokens`, `chunk_max_tokens`, `chunk_overlap_tokens` and
`chunk_max_chars` (all NULL on every existing/legacy row).
`vector_records` gains nullable `token_count`, `token_start`, `token_end`
(NULL on every existing character chunk). The CHECKs enforce:

- tokenizer/chunk columns are all-or-none;
- the kind is closed and exact/provenance match it (heuristic is
  `exact=false` with no revision/checksum; HF/sentencepiece need a pinned
  revision + checksum; tiktoken needs a checksum);
- the chunk budget is valid (`>= 32` tokens, `overlap * 2 < max`,
  `max_chunk_tokens <= max_input_tokens`, positive chars);
- a populated tokenizer requires `chunker_version='2'`;
- record token offsets are all-or-none, non-negative, ordered and
  `token_count == token_end - token_start`.

Downgrade drops the tokenizer/chunk/token columns and their checks but keeps
`space_key`: a stored v2 key remains a v2 key even if the columns that explain
it are removed.

**T5b2 handoff (explicit, not built here).**
1. Implement the explicit v2 model default/`build_space` path: a row carrying
   the complete tokenizer/chunk pair computes `space_key_v2` and forces
   `chunker_version='2'` instead of refusing the implicit key.
2. Add the token-aware chunk path (`encode_with_offsets`) for a v2 space only;
   keep the v1 character path byte-identical and do not re-chunk in place.
3. Write `token_count/token_start/token_end` from the tokenizer offsets on new
   v2 records; leave legacy records NULL.
4. Select the tokenizer/chunk from the study model-profile/accounting seam,
   persist it on the space, and expose it on the status/read DTOs
   (`token_aware`, tokenizer, chunk) for the build/cutover UI.
5. Build a candidate v2 space, compare coverage/quality, cut over with the
   stored-key activation path, and retain the v1 space. Progress detail/UI
   stay T5c/T5d.

## Plan 52 T5b2 — token-aware writes and the v2 cutover (T5c handoff)

T5b2 is the **write half**. A token-aware space now chunks and embeds by
tokens while every v1 space stays character-chunked and byte-identical. It
does **not** emit `progress_detail`, change the Tools UI or write rollout
docs; those remain T5c.

**Profile resolution.** `services/retrieval/chunk_profile.py` resolves one
effective pair from the embeddings assignment through the existing accounting
seam: an explicit admin pair when supplied, the curated OpenAI embedding
mapping (bundled exact `cl100k_base`), otherwise the labelled heuristic
fallback. No model-name substring ever selects a tokenizer. The default
budget is 512 tokens / 64 overlap / 2400 chars, clamped to fit
`max_input_tokens` minus the document prefix and a 16-token safety margin.
Request batching is separate: `batch_max_items=64`,
`batch_max_tokens=32_000`, and the reindex payload's own `batch_size` can
only tighten the item bound.

**Identity.** `lifecycle.build_space` takes an optional complete
`tokenizer` + `chunk` pair. With the pair it persists all nine scalars,
forces `chunker_version='2'`, validates the budget and computes
`space_key_v2` explicitly; with neither it keeps the v1 build and the v1 key.
A half pair is refused. The ORM's implicit `space_key` default now computes
the v2 pre-image from a complete pair, still stamps v1 for a legacy row, and
refuses a half pair or `chunker_version='2'` without a tokenizer.
`ContentSpace`/`canonical_space` reconstruct the pair and return the stored
key verbatim. `POST /admin/retrieval/spaces` accepts `token_aware: true` to
resolve and persist the assignment's profile; the space/run read DTOs expose
`token_aware`, tokenizer identity/exactness and the chunk config.

**Chunking.** `pipelines/chunking.py` keeps `chunk_markdown` unchanged and
adds `chunk_tokens`: `encode_with_offsets` windows with exact character
spans, token `start/end/count`, token overlap, a hard `max_chars` ceiling and
no truncation. A window that cannot fit raises the typed `input_too_long`
failure. Ingest, trash restore, material edits and course import all call
`chunk_texts_for_space`, which uses the **active** v2 space's exact profile
and otherwise the v1 character path. `Chunk.token_count` is the exact window
count for a v2-created chunk; existing v1 chunks are never rewritten.

**Writes.** `StudyVectorStore.store_specs` writes one `vector_records` row
per token window with `char_start/char_end` and
`token_count/token_start/token_end`; `IndexRecord` carries the same fields to
the backend. Migration `0018_vector_record_token_windows` widens the record
uniqueness to `(space, chunk, chunk_index)` so one source chunk can own
several windows without losing its `chunk_id` hydration handle. Search
dedupes hits by chunk (best distance). The ordinary `store()` path is
untouched for v1. Reindex windows each source chunk, skips a window whose
`(chunk_id, chunk_index)` content hash is stored unchanged, reports
`input_too_long` once per chunk (never loops or truncates) and keeps coverage
counted in chunks. Postprocess uses the same profile and batching for an
active v2 space.

**Cutover.** Build a v2 space beside the active v1 space (API
`token_aware=true` or `lifecycle.build_space` with a pair), backfill it with
`VECTOR_REINDEX`, pass the existing physical/coverage/golden-query quality
gates, then `activate`/`VECTOR_CUTOVER`. Activation returns the retired
space's **stored** key (`previous_space_key`) as the remap identity, flips
the one active pointer and keeps the v1 space and `chunk_vecs` retained. No
in-place re-chunking: the v1 rows, their keys and their NULL token fields
survive until the explicit drop.

**Operator runbook.** Set the embeddings assignment first; a curated OpenAI
embedding model resolves the exact bundled `cl100k_base`, anything else shows
`exact=false` and must be treated as approximate. Then:

1. `POST /api/v1/admin/retrieval/spaces` with the current provider/model/dim
   and `"token_aware": true` (or an explicit `tokenizer` + `chunk` pair from
   an admin script); capture `space_id`, `space_key`, `tokenizer` and `chunk`.
2. `POST /api/v1/admin/retrieval/reindex` with that `space_id` and an
   `Idempotency-Key`; wait for `GET /runs`, then confirm the space's coverage
   snapshot/gate.
3. Run `POST /quality/compare` (or `POST /cutover`, which runs coverage,
   quality, activation and retirement in one run) and require `pass`.
4. Activate or cut over; confirm the response's `previous_space_key` is the
   old **stored** key, the active space DTO reports `token_aware=true`, and
   the v1 space is `retired` but still present.
5. Drop the retired v1 space only with its typed name after the grace period
   (or `force` + the typed name); the compatibility `chunk_vecs` store
   disappears with that explicit drop.

**T5c handoff (exact, not built here).**
1. Emit the bounded `background_jobs.progress_detail` contract
   (`phase`, processed/total/pending documents and chunks, embedded/skipped/
   failed chunks, tokens, embed calls, `exact_tokenizer`) from the v2 write
   loop, carry it across chained reconcile runs, fold it into the existing
   per-document progress update, prune it when the final `result` lands, and
   keep no id lists or text in it.
2. Render that detail in Tools → Indexing and the Audit/run drawers (bar plus
   counters, exact/fallback label); the space/run DTO fields already exist.
3. Rollout docs/runbook: operator sequence for a v2 build/backfill/quality
   compare/cutover, the tokenizer fallback warning, and the explicit retained-
   v1 drop; no new ledger and no Study-only contract edit.
4. Run the full re-embed/parity benchmark and close the family T5 parity
   evidence once main carries these bytes.

## Plan 52 T5c — bounded live progress and read-only parity (T5d handoff)

T5c is the **visibility** slice. It emits the vendored family
`RunProgressDTO` shape from the Study retrieval pipeline, exposes it on the
run read DTO/API, and renders it in Settings → Indexing plus the read-only
observation drawers. It does **not** change token-aware chunking, writes,
space identity, cutover gates or any T5b2 semantics.

**Column.** Migration `0019_job_progress_detail` adds nullable
`jobs.progress_detail` (`JSON` on SQLite and PostgreSQL). Existing rows read
as NULL; every non-vector job family keeps its old progress semantics.
Downgrade drops the column — the detail is live telemetry, never audit data.

**Write path.** `services/progress.py` owns the closed bounded shape
(`MAX_PROGRESS_DETAIL_BYTES = 2048`, unknown keys dropped, counters clamped,
phase from `RUN_PROGRESS_PHASES`). The job runner writes
`progress`/`stage`/`heartbeat_at` and the bounded detail in **one** UPDATE —
the pipeline never issues a second per-document write. The pipeline's meter
tracks:

- `processed_documents`/`total_documents` — the exact selected chunk count at
  scan start (or the carried total on a continuation);
- `processed_chunks` — the v1 count is one record per chunk; the v2 count is
  the sum of token windows, so `chunks_estimated=true` and
  `pending_chunks` is the running-average estimate (never a fake exact
  corpus total);
- `embedded/skipped/failed` documents and chunks;
- `tokens` from the local tokenizer only (`embedding_accounting` for v1,
  the persisted v2 tokenizer for windows) with `tokens_estimated` and
  `exact_tokenizer`; provider billing remains `ai_interactions`;
- `embed_calls` and the phase (`scanning`/`done`/`writing`).

No document text, chunk/document ids, failed-id lists or query text may enter
the detail; the payload wall and the live-progress tests pin that.

**Carry + prune.** A limited pass returns its counters as `progress_carry`.
`retry_run` seeds the queued continuation from the failed/cancelled run's
stored detail (or its carried payload), so the bar resumes instead of
resetting; counters are cumulative and never rewritten. When the final
`result` commits, the runner writes `progress_detail = NULL`; the result
counters remain authoritative. A malformed stored row reads as absent on the
read surface.

**Read/API.** `services/retrieval/reads.py` validates the stored document
through `RunProgressDTO` and adds it to `RunDTO`/the run list. The API model
`RetrievalRunProgressOut` and the generated OpenAPI/types carry the same
optional field; the token-aware/tokenizer/chunk fields stay as T5b2 shipped,
with `tokenizer.source` derived from the persisted kind
(`heuristic → fallback`, otherwise `curated`). The label is read-only
evidence, not a re-resolution.

**UI.** `RetrievalProgress` renders an accessible `role=progressbar` driven by
processed/total documents with pending/estimated chunk text, embedded/
skipped/failed, approximate tokens (`~`) and embed calls, and an exact/
approximate tokenizer label. `RetrievalTokenizerLabel` renders token-aware vs
legacy v1. Both appear in the Settings run list/space rows and the read-only
observation runs table, run drawer and space drawer; compact mode keeps rows
narrow on mobile. The observation surface still exposes no write control.

**Operator runbook addition.** While a vector run is active, read
`GET /api/v1/admin/retrieval/runs`: `progress_detail.total_documents` is the
exact selected document count, `pending_chunks` is explicitly estimated for a
v2 space, and `exact_tokenizer=false` means the token count is the labelled
fallback. Do not treat the live counters as the audit result — the final
`result` (`scanned/embedded/skipped/failed/failed_ids/gate`) is authoritative
and the live detail disappears when it commits.

**T5d handoff (exact, not built here).**
1. Re-vendor nothing: T5c writes **no** contract bytes. Confirm the dev
   canonical ledgers still name study and that
   `backend/app/storage/retrieval_ops.py` +
   `backend/tests/fixtures/retrieval_ops.fixtures.json` remain byte-identical
   to `dev-vector-p0/contracts` (sha check) before publication.
2. Run the family parity wall with both overrides
   (`STUDY_RETRIEVAL_CAREER_REPO=<career-tokenizer-p52>`,
   `STUDY_RETRIEVAL_ADOPTION_REPO=<study-tokenizer-p52>`) and record the one
   expected `adoption:study-main` blocker separately; the branch bytes are
   not main adoption. Do not claim `strict=True` until main carries them.
3. Rollout docs/publication: add the user-facing live-progress note to the
   release changelog and the operator sequence (v2 build → backfill with the
   live bar → coverage/quality compare → cutover → retain v1 → explicit
   drop), including the exact/fallback warning and the fact that a limited
   run leaves a visible pending remainder.
4. Full re-embed/parity benchmark and the T5 family evidence/closeout. No new
   ledger, no second audit stack, no write/cutover change in T5d.
