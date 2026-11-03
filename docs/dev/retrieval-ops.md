# Retrieval operations (plan 51 Q3a)

Status: **Q3a foundation only** (2026-11-04). The family contract, the
`VECTOR_*` job slot, the two bounded aggregates, the first admin read surface
and a truthful Tools → Indexing status card are shipped. The management UI,
space lifecycle and action API are Q3b.

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
document text or query text. The Tools → Indexing card reads `/overview` and
shows cold/degraded/ready truth plus the backend label; it has no action
buttons and no fake space lifecycle.

## Q3b handoff (explicitly not shipped)

- Vector-space lifecycle: `vector_spaces`/`vector_documents`/`vector_records`
  (build, activate, retire, drop) and a real space id in the rollups. Until
  then `VECTOR_CUTOVER` refuses and the read surface exposes one legacy space.
- Management/action API: reindex/maintenance/cancel/retry actions,
  idempotency keys, one-active-run lock + stale-heartbeat reaper, audit
  `vector.*` events, alerts.
- Coverage/quality gates and the golden-query compare; no quality surface.
- `ai_generations` tagging: study's equivalent ledger is `ai_interactions`,
  which has no metadata column and no `prompt` column. No second ledger was
  invented; caller-supplied retrieval tags need a Q3b schema decision.
- Settings-map `tools.retrieval` stays `pending (plan 51 Q3)` until the
  management surface ships; `tools.indexing` remains user-scoped.
- Family parity test (same status payload semantics on both dialects) is Q5,
  after the lifecycle exists.
