# Background jobs and schedulers

Everything heavy runs off the request path as a durable background job: file
ingestion, OCR, extraction post-processing, chat turns, material composition,
course genesis and URL imports. Jobs live in the `jobs` table, are claimed by a
worker pool, and stream progress to the UI over WebSocket. Separate scheduler
threads enqueue recurring work (source scans, external sources, backups). This
page describes the runner, the job types, retries and cancellation, and the
schedulers. Progress surfaces in the UI on the `/jobs` activity page.

## The runner

`backend/app/jobs/runner.py` implements a **claim-based worker pool**:

- On `start()` it reclaims any `running` jobs left by a previous process
  (marked `failed` with an "interrupted" error) and spawns worker threads
  (default 4). Workers poll the `jobs` table, claim a queued row, run its
  registered handler, and update status.
- Handlers are registered in `app/jobs/registry.py` keyed by **`JobType`
  members** (plan 82 C, ADR-204) — the enum is the single vocabulary, so a
  typo'd key cannot silently drop jobs. `tests/test_job_registry.py` asserts
  every `JobType` member has a registered handler and vice versa. Each
  handler is `(Session, Job, ProgressReporter) -> None`.
- Progress is reported through the `EventBus`, which bridges worker threads to
  WebSocket subscribers via `publish_threadsafe`.
- Failed jobs are recorded and logged (structlog `job_failed`); the pool keeps
  running. An optional per-job timeout is available.
- A `group_key` serializes related jobs: chat turns for one session share a
  group so two turns cannot run at once.

The registered job types are:

| Type | Enqueued when | Handler pipeline |
|---|---|---|
| `ingest` | Upload, linked-source scan, URL import of a file | `pipelines/ingest.py` — extraction, chunks, FTS |
| `postprocess` | After ingest / restore | `pipelines/postprocess.py` — embeddings + LLM index card |
| `chat_turn` | A chat message is sent | `pipelines`/chat handler — the LangGraph turn engine |
| `drawing_ocr` | A drawing is saved or re-OCR'd | `pipelines/drawing_ocr.py` |
| `image_ocr` | A converted document yields images | `pipelines/image_ocr.py` |
| `genesis` | Topic-to-course generation | `pipelines/genesis.py` |
| `compose` | AI-composed material requested | `pipelines/compose.py` |
| `url_import` | A link material is refreshed | `pipelines/url_import.py` |

The closed vocabulary of job statuses is `JobStatus` in `core/vocab.py`:
`queued`, `running`, `failed`, `done`, `cancelled`.

## Retries and cancellation

- **Retry.** `api/jobs.py` exposes `GET /jobs` (plus `/summary`),
  `POST /jobs/{id}/retry` and `POST /jobs/retry-failed`. A failed job is
  retriable iff its type has a registered handler and it is not a chat turn
  (`runner.py` computes the retriable set from the handler map). Retrying resets
  status to `queued` and clears the error/stage.
- **Cancellation** (ADR-126): `jobs/cancellation.py` adds a terminal
  `cancelled` status. Cancel-on-purge, cooperative checkpoints inside handlers,
  and commit-time stale re-checks prevent a cancelled job from writing after
  its target is gone.
- **Payloads** are TypedDicts in `jobs/payloads.py`, so every enqueue and
  handler is type-checked. Use the typed payload for a new job rather than a
  bare dict.

## Schedulers

Three long-lived threads start with the app (`main.py` lifespan):

- **`ScanScheduler`** — re-scans linked folders on
  `SA_SOURCE_SCAN_INTERVAL_SEC` (default 300 s) and enqueues `ingest` for new
  files.
- **`ExternalSourceScheduler`** — polls enabled `external_sources` on per-source
  due times (minimum 15 min). Since plan 86 the same loop dispatches through
  the provider seam: RSS/Atom, YouTube and site search keep their legs, while
  WebDAV/Nextcloud, Google Drive, Dropbox, OneDrive, Zotero and AnkiConnect
  reconcile through the `SourceAdapter` engine. New items land as `suggested`
  suggestions — never materials, never LLM calls; provider failures are typed
  and tracked as `consecutive_failures` (`degraded` then `failing`), isolated
  per source into `last_scan_error` and published on `externalsource:{id}`.
  Anki scans union-merge review events (unique by source + remote card +
  reviewed time) and deterministically recompute the mapped cards' FSRS state;
  RSS media-enclosure acceptance enqueues the existing `url_import`
  `transcribe_audio` path.
- **`BackupScheduler`** — writes a validated full archive shortly after startup
  and every `SA_BACKUP_INTERVAL_HOURS` (default 24), retaining 14 dailies + 8
  weeklies, with an optional `SA_BACKUP_SYNC_DIR` copy.

Job and scheduler state is observable through `GET /jobs`, the `/jobs` UI page,
and the WebSocket topics in [api.md](api.md). The activity/retry user-facing
behavior is described in the [user activity guide](../user/activity.md).

## Adding a job type

1. Define a TypedDict payload in `jobs/payloads.py`.
2. Write the handler pipeline (`pipelines/<name>.py`) exposing a
   `make_<name>_handler(...)` factory.
3. Register it in the `handlers` map in `main.py`.
4. Enqueue it with `JobRunner.enqueue(session, "<name>", payload)`.
5. Add tests with the `client`/`db_session` fixtures (see
   [testing.md](testing.md)) and update `docs/STATUS.md`.
