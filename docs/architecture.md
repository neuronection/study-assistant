# Architecture

One local process. The frontend talks only REST + WebSocket, which keeps the window
shell replaceable (pywebview today; browser dev mode daily; Tauri a future option)
without touching app code.

```
┌─ Desktop app (python -m studyassistant) ─────────────────────────────┐
│  pywebview window (WebKitGTK/WebView2/WKWebView)                     │
│      │ React SPA (TanStack Router/Query, Tailwind, shadcn-style UI)  │
│      ▼                                                                │
│  FastAPI (uvicorn thread, 127.0.0.1:<free port>)                     │
│      REST /api/v1/*   ·   WebSocket /ws                              │
│      ├─ services/    grouped packages (54-D): content/ (materials,    │
│      │               folders, sources, drawings, course_bundle),      │
│      │               study/ (grading, tutor, exercise_*, patterns),   │
│      │               knowledge/ (courses, tree, concepts, context),   │
│      │               platform/ (chat, skills, backup, trash, …),      │
│      │               search/ (hybrid FTS⊕vec engine)                  │
│      ├─ pipelines/   ingest, postprocess, drawing_ocr, image_ocr,   │
│      │   quizgen, convert/                                          │
│      │               compose (AI-composed material)                  │
│      ├─ ai/          gateway (LangChain chat models behind LLMGateway),   │
│      │              providers/tasks, chat_models, types,                  │
│      │               embeddings, tools, contracts registry,          │
│      │               task runner + shared parsing helpers            │
│      ├─ math/        equivalence chain, hint-leak guard              │
│      ├─ ocr/         OcrEngine interface + task-routed implementation│
│      ├─ jobs/        durable runner (jobs table, worker thread)      │
│      └─ storage/     SQLite engine (+FTS5 +sqlite-vec), blobs, fts   │
└──────────────────────────────────────────────────────────────────────┘
         │ (only AI calls leave the machine)
         ▼
   LLM / vision providers (Google, OpenAI-compatible, Anthropic, Ollama…)
```

## Backend layout (`backend/app/`)

| Module | Responsibility |
|---|---|
| `main.py` | App factory: runs Alembic migrations on startup, seeds default profile + task registry, wires gateway/OCR/embedder/describer/jobs |
| `shell.py` | Entrypoint `python -m studyassistant [app\|web]`: `app` sanitizes snap-polluted env (VS Code terminals), starts uvicorn thread + pywebview window with localStorage enabled; `web` runs uvicorn in the foreground (`SA_PORT`, default 8000) and opens the default browser. Launch scripts: `scripts/{webapp,dev,app}.sh` / `pnpm {webapp,dev,app}` |
| `mcp_resources.py` | **MCP resource server (9E) + shared resource-tool registry (plan 36, ADR-080)**: `python -m studyassistant mcp` runs a read-only **stdio** MCP server (official SDK 2.0) exposing eight node-scoped tools (`list_courses`, `get_node_overview/materials/concepts/exercises/quizzes/notes`, `get_node_context`) over the same services as the REST API — for external AI agents. Plan 36 lifts each tool's execution into a module-level function + a `RESOURCE_TOOLS` registry so the chat can call a curated subset (`COURSES`/`NODE_OVERVIEW`/`NODE_QUIZZES`/`NODE_EXERCISES`/`NODE_NOTES`) with zero drift; `get_node_context` runs the shared `ContextResolver` (FTS-only, no embeddings) and returns the same budgeted manifest as `POST /ai/context/preview` (plan 17 F). No write tools; logs forced to stderr (stdio purity); the mcp launch path never imports `app.main` |
| `api/` | Routers (health, materials, blobs, search, folders, courses, chat, quiz, exercises, ai-settings, ai context preview), `/ws` endpoint, Pydantic DTOs |
| `agui/` | **AG-UI agent↔UI contract (plan 34, ADR-071)**: typed event models (`events.py`) + JSON-Patch state reducer (`state.py`) + chat-stream→AG-UI adapter (`mapping.py`) — the foundation for interactive widgets and their bidirectional state channel |
| `core/` | `Settings` (pydantic-settings, `SA_*` env), structlog logging, keyring secrets, in-process EventBus with threadsafe publish |
| `domain/` | SQLAlchemy 2 models in a package (54-C): `models/core.py` (profiles/courses/tree), `models/content.py`, `models/study.py`, `models/chat.py`, `models/ops.py` (jobs/analytics/trash/skills) — `models/__init__` re-exports everything; single source of truth for Alembic autogen |
| `services/` | Business logic over the models, grouped by domain (54-D): `content/`, `study/`, `knowledge/`, `platform/`, `search/` (see ai.md / features.md for behavior) |
| `core/vocab.py` | StrEnum vocabularies (55-A, ADR-128): JobStatus/JobType/MaterialKind/MaterialStatus/AttemptMode/ComposeKind/Capability/ProvenanceKind + `WsTopic` factories — closed sets never appear as bare literals; DB columns stay strings |
| `pipelines/` | Multi-step flows: ingest (PDF text / OCR / native / office-web conversion via `convert/` / AV transcription, plan 47 ADR-103/104), postprocess (embed + index cards), drawing_ocr + image_ocr (background transcription of drawings and extracted document images, ADR-102/103), quizgen (blueprint → LLM → validate → repair) |
| `ai/` | Model layer — see [ai.md](ai.md) |
| `math/` | Deterministic math trust layer — see [math-verification.md](math-verification.md) |
| `ocr/` | `OcrEngine` interface; `GatewayOcr` routes page images through the `ocr` task (any assigned vision model); `imaging.py` caps the long edge and re-encodes payloads (WebP q85) before any vision call (ADR-102) |
| `storage/` | Engine with WAL/foreign-key/busy-timeout pragmas + sqlite-vec extension load; content-addressed blob store; FTS sync; vector store |
| `jobs/` | Claim-based worker **pool** over the `jobs` table (default 4 workers) — durable, crash-safe: failed jobs are recorded + **logged** (structlog `job_failed`), the worker pool continues, **`running` jobs left by a restart are reclaimed as `failed`/interrupted on startup**, and an optional per-job timeout (`job_timeout_sec`) is available; progress via EventBus → WS. **Retry surface (2026-08-27): `api/jobs.py` exposes `GET /jobs` (+`/summary`), `POST /jobs/{id}/retry` and `POST /jobs/retry-failed`; a failed job is retriable iff its type has a registered handler and isn't a chat turn — retry resets status→queued, clears error/stage, wakes the pool**. **Cancellation (54-A, ADR-126): `cancellation.py` + terminal `cancelled` status — cancel-on-purge, cooperative checkpoints, commit-time stale re-checks; `payloads.py` TypedDicts type every enqueue/handler payload (55-C)** |

## Frontend layout (`frontend/src/`)

| Directory | Contents |
|---|---|
| `app/` | TanStack router (all routes), providers in `main.tsx` (Query, MotionConfig with `reducedMotion="user"`) |
| `features/` | home, library (Nemo-style navigator: breadcrumbs/grid-list/context menu + material detail page), courses (tree, outline, NodeWorkspace), ai (uniform generate dialog, AI-hint card), chat (sidebar, streaming, **turn-trace timeline + `tools/` per-tool registry**, plan 35), quiz (generator, runner, import/export), scores (history, mistakes), exercises (player, hints), settings (providers/models/tasks), spike (WebKitGTK check) |
| `components/` | Block renderers (text+KaTeX / math / mermaid / table / code / drawing / **chart via Plotly.js / geo via JSXGraph — both lazy-loaded**, plan 34), **`widgets/` interactive-widget registry** (checklist/choice/slider/equation_input/numberline + chart/geo, `getWidgetComponent` dispatch, plan 34), `MathInput` (MathLive), `DrawCanvas` (pen/eraser/pressure handwriting), ui primitives, layout shell |
| `features/library/` | Nemo-style navigator, material detail, **`SplitStudyPane`** (material ⇄ note split study, plan 22 G) |
| `lib/` | **`api/` package (54-B): the typed API client split by domain** (client core, materials, courses, chat, quiz, exercises, notes, flashcards, analytics, jobs, settings, system, ai, sources, folders) — request/response types come from **`api-schema.d.ts`, generated from `openapi.json` by `pnpm api:types` (55-B, ADR-129; CI drift-guards both artifacts)**; WS client; `constants.ts` (55-D: `WsTopic` builders + `storageKeys`, mirroring the backend's `core/vocab.py`); i18n (react-i18next, `en` catalog, hardcoded-string lint error), `ui-overlays` (zustand signal: full-screen overlays call `useCloseFloatings()` on mount so the shared `Popover` closes any open floating panel instead of painting above the overlay) |

## Runtime behavior

- **Startup**: migrate to head → **boot integrity check** (corrupt `app.db`
  quarantined as `corrupt-<ts>.db`, newest valid backup restored automatically,
  event recorded in `last-recovery.json`) → seed default profile + task
  assignment rows + purge expired trash → start job runner + scan scheduler +
  **backup scheduler** threads → serve built SPA from `frontend/dist` (or hint
  to build it).
- **Jobs**: upload → `ingest` job → extraction + chunks + FTS (+ `postprocess` job for
  embeddings & LLM index cards, best-effort). Chat turns and tutor hints run as jobs
  too, streaming progress over WS topics `chat:{id}` / `jobs:{id}`.
- **Automatic backups (plan 22 C)**: `BackupScheduler` writes a validated full
  archive (snapshot DB + blobs + manifest) to `backups/` shortly after startup
  and every `SA_BACKUP_INTERVAL_HOURS` (default 24); retention 14 dailies + 8
  weeklies; optional `SA_BACKUP_SYNC_DIR` copy (atomic rename) for off-machine
  redundancy; runtime overrides in `backup-settings.json`; manual download
  export + upload/stored-by-name restore stay available.
- **WebSocket**: `/ws` with subscribe/unsubscribe/publish/ping frames; the backend
  EventBus bridges worker threads to subscribers via `publish_threadsafe`.
- **Storage**: SQLite in WAL mode, FTS5 full-text, sqlite-vec vectors (runtime-created
  `chunk_vecs`, rebuilt automatically when the embedding model/dimension changes),
  originals in a content-addressed blob store (`blobs/ab/cd/<sha256>`) — dedup by
  content hash, never modified.
- **Data dir**: `~/.local/share/StudyAssistant/` (`app.db`, `blobs/`, `cache/`,
  `thumbnails/`, `backups/`, `backup-settings.json`, `last-recovery.json`). Config
  via `SA_*` env vars; API keys only in the OS keyring
  (`StudyAssistant/provider:{id}`). A pre-rename `CourseAssistant` data dir is
  renamed automatically on first launch (when the new one doesn't exist yet);
  keyring entries under the legacy `CourseAssistant` service are copied to
  `StudyAssistant` on first read (legacy entries stay in place as a backup).

## Security posture

- Server binds loopback only; no external exposure.
- API keys never touch the DB, logs, or files — keyring only, masked in every API
  response (`••••1234`).
- Parameterized SQL only (SQLAlchemy core/ORM).
- Upload size cap (200 MB); blob ids validated (strict sha256 pattern) before serving.
- `eval`-based math calculator runs with an empty builtins namespace, a math-function
  allowlist, and dunder/charset guards.
